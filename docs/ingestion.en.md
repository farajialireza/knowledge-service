# Document Ingestion — English

How `ai-knowledge-service` turns an uploaded file into searchable embedded
chunks. This document describes the **currently implemented** behavior.

## Overview

```mermaid
flowchart LR
    A[Upload] --> B[Validation]
    B --> C[File-hash dedup]
    C --> D[Extraction]
    D --> E[Normalization]
    E --> F[Content-hash dedup]
    F --> G[Chunking]
    G --> H[Embedding]
    H --> I[Persist + Activate]
```

Steps A–C run inside the HTTP request; D–I run in a **background task**
after the API has already responded. The request is never blocked by
parsing or embedding.

## API

Interactive Swagger UI: `GET /docs`.

### `POST /documents` — upload

- **Request**: `multipart/form-data`, single field `file`.
- **Supported types** (by file extension):

  | Extension | Stored MIME type |
  |-----------|------------------|
  | `.pdf`    | `application/pdf` |
  | `.docx`   | `application/vnd.openxmlformats-officedocument-wordprocessingml.document` |
  | `.xlsx`   | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` |
  | `.csv`    | `text/csv` |

- **Size limit**: `MAX_UPLOAD_MB` (default 50 MB), enforced while streaming.
- **Responses**:
  - `202` — accepted, ingestion started:
    ```json
    { "document_id": "…", "job_id": "…", "status": "processing" }
    ```
  - `200` — exact duplicate file (same SHA-256 `file_hash`); **no new
    ingestion runs**, the existing document is returned:
    ```json
    { "document_id": "…", "status": "active", "deduplicated": true }
    ```
  - `413` — file too large. `415` — unsupported type.
  - `500` — unexpected error (`{"detail": "Internal server error"}`;
    internals are logged server-side only).

### `GET /documents/{document_id}` — status polling

Poll this endpoint (e.g. every 1–2 s) until `status` leaves `processing`.

```json
{
  "id": "…", "name": "report.pdf", "mime_type": "application/pdf",
  "size": 183412, "file_hash": "…", "content_hash": "…",
  "status": "active", "created_at": "…", "updated_at": "…",
  "job_status": "completed", "error_code": null, "error_message": null
}
```

`404` if the ID is unknown.

## Status model

**Document** (`ai_assistant.documents.status`):

| Status | Meaning |
|--------|---------|
| `processing` | Ingestion in progress (not retrievable). |
| `active` | All chunks + embeddings persisted — safe to use. |
| `inactive` | Skipped: another document already has the same normalized content. |
| `failed` | Ingestion failed; see job `error_code`/`error_message`. |

**Job** (`ai_assistant.ingestion_jobs.status`):
`pending → processing → completed | failed`.

Failure codes (job `error_code`): `corrupt_file` (parser rejected the file),
`empty_content` (no usable text extracted), `config_error`
(`OPENAI_API_KEY` missing), `document_missing`, or the exception class name
for unexpected errors. A completed job may carry `duplicate_content` in
`error_code` as a benign note.

**Guarantee**: chunk insertion and the `status → active` flip happen in a
**single database transaction**. A failed or interrupted ingestion can never
leave a document retrievable as `active`.

## Deduplication (two levels)

1. **File level** — SHA-256 of the raw bytes (`file_hash`, unique index).
   Same bytes re-uploaded → `200` dedup response, nothing re-ingested.
2. **Content level** — SHA-256 of the normalized extracted text
   (`content_hash`). Different files with identical content (e.g. a PDF and
   a DOCX export of the same text) → the new document is marked `inactive`
   and its job completes with `duplicate_content`.

## Pipeline details

- **Extraction** (per format, into a common `Block` representation):
  PDF → paragraphs with page numbers (pypdf); DOCX → headings (styles
  `Heading 1–6`, `Title`), paragraphs and tables in document order
  (python-docx); XLSX → one table block per non-empty sheet, section = sheet
  name (openpyxl); CSV → one table block, dialect sniffed (stdlib `csv`).
- **Normalization** — NFC Unicode, control characters stripped, whitespace
  runs collapsed, empty blocks dropped. Runs **before** the content hash so
  trivial whitespace differences cannot defeat dedup.
- **Chunking** — packs blocks up to `CHUNK_SIZE_CHARS` (default 2000,
  ≈4 chars/token) with `CHUNK_OVERLAP_CHARS` (default 200) tail overlap.
  Headings are not chunked; they become the section context of what
  follows. Oversized blocks are split at sentence/line boundaries. Each
  chunk stores `context` (`Document: … | Section: … | Page: …`) separately
  from `content`.
- **Embedding** — OpenAI `text-embedding-3-small` (1536 dimensions, matches
  the `VECTOR(1536)` column), batches of `EMBEDDING_BATCH_SIZE` (default 64).
  The text sent to the model is `context + "\n\n" + content`.
- **Persistence** — direct SQL via psycopg into the existing
  `ai_assistant.documents` / `document_chunks` / `ingestion_jobs` tables.
  Original files are kept content-addressed under `STORAGE_DIR`
  (`{file_hash}{ext}`), enabling future re-chunking/re-embedding.

## Asynchrony & concurrency

Ingestion runs as an in-process background task (no Celery/Redis), capped by
a semaphore at `INGESTION_MAX_CONCURRENT` (default 2) concurrent jobs.
Blocking parser calls run in a worker thread; embedding and database work
are async-native. Note: a process restart mid-ingestion leaves the document
in `processing` (never `active`) — re-upload to retry.

## Configuration reference

| Env var | Default | Purpose |
|---------|---------|---------|
| `MAX_UPLOAD_MB` | 50 | Upload size cap |
| `STORAGE_DIR` | `data/uploads` | Original file storage |
| `CHUNK_SIZE_CHARS` | 2000 | Max characters per chunk |
| `CHUNK_OVERLAP_CHARS` | 200 | Overlap between chunks |
| `OPENAI_API_KEY` | — | Required for embeddings |
| `OPENAI_BASE_URL` | — | Optional proxy/gateway |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model |
| `EMBEDDING_BATCH_SIZE` | 64 | Chunks per embedding API call |
| `INGESTION_MAX_CONCURRENT` | 2 | Concurrent ingestion jobs |
