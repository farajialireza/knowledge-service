# ai-knowledge-service

Standalone FastAPI service providing the AI knowledge base backend. PostgreSQL
only, accessed directly via `psycopg` 3 — no ORM, no migrations tool. The
database schema (`ai_assistant.*`) is managed externally (see `../db.sql`);
this service never creates or alters tables.

## Stack

- FastAPI + uvicorn (ASGI)
- psycopg 3 with `psycopg_pool.AsyncConnectionPool`
- pydantic-settings for `.env` configuration

## Structure

```
app/
├── main.py            # App factory + lifespan (pool startup/shutdown)
├── config.py          # Settings loaded from .env
├── logging_config.py  # Console logging setup
├── exceptions.py      # Global error handler (no internals leaked to clients)
├── api/
│   ├── router.py      # Router aggregation
│   └── routes/
│       ├── health.py      # GET /health
│       └── documents.py   # POST /documents (upload), GET /documents/{id} (status)
├── db/
│   ├── pool.py        # AsyncConnectionPool creation
│   └── health.py      # SELECT 1 liveness probe
└── ingestion/
    ├── runner.py      # Background task + concurrency semaphore
    ├── pipeline.py    # Orchestrates the flow, records job/document status
    ├── repository.py  # All SQL (documents, chunks, jobs)
    ├── validation.py  # File-type allowlist
    ├── hashing.py     # SHA-256 file hash + normalized content hash
    ├── normalize.py   # Unicode/whitespace normalization
    ├── chunking.py    # Configurable, format-independent chunker
    ├── embeddings.py  # OpenAI text-embedding-3-small, batched
    ├── models.py      # Block / ExtractedDocument / Chunk
    └── extractors/    # pdf.py, docx.py, xlsx.py, csv.py → ExtractedDocument
```

## Ingestion flow

`POST /documents` (multipart `file`) → 202 `{document_id, job_id}`:

1. Validate extension against the allowlist (PDF, DOCX, XLSX, CSV) and cap size.
2. Stream to disk while computing SHA-256 → exact-file dedup by `file_hash`.
3. Insert document (`processing`) + job (`pending`) atomically; return 202.
4. Background task: extract → normalize → content-hash dedup (duplicate
   content → document `inactive`) → chunk → embed → insert chunks + flip
   document to `active` in ONE transaction.
5. Any failure → document `failed`, job `failed` with `error_code`/`error_message`.
   A document is never retrievable as `active` unless its chunks were fully written.

Poll `GET /documents/{id}` for document + latest job status.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then edit credentials
```

## Run

```bash
uvicorn app.main:app --reload
```

## Health check

`GET /health`

- `200 {"status": "ok", "database": "up"}` — PostgreSQL reachable
- `503 {"status": "degraded", "database": "down"}` — PostgreSQL unreachable
  (details are logged server-side, never returned to clients)
