"""Admin document endpoints: upload (kicks off async ingestion) and status."""
import hashlib
import logging
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from psycopg.errors import UniqueViolation

from app.api.schemas import (
    DocumentAcceptedResponse,
    DocumentDeduplicatedResponse,
    DocumentStatusResponse,
)
from app.config import get_settings
from app.ingestion.repository import Repository
from app.ingestion.runner import run_ingestion_guarded
from app.ingestion.validation import UnsupportedFileTypeError, resolve_upload_type

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])

# Uploads are streamed to disk in 1 MiB pieces so large files never sit in memory.
_UPLOAD_BUFFER = 1024 * 1024

_UPLOAD_DESCRIPTION = """\
Upload a document and start asynchronous ingestion.

**Request**: `multipart/form-data` with a single `file` field.

**Supported types** (by extension): `.pdf`, `.docx`, `.xlsx`, `.csv`.
The maximum file size is set by `MAX_UPLOAD_MB` (default 50 MB).

**What happens next** (in the background):
upload → validation → deduplication → extraction → normalization →
chunking → embedding → persistence → activation.

**Deduplication**: if the exact same file bytes were uploaded before
(SHA-256 `file_hash` match), no ingestion runs and the response is
`200` with the existing document's ID and `deduplicated: true`.

Poll `GET /documents/{document_id}` until `status` becomes
`active` (ready), `inactive` (content duplicate), or `failed`.
"""


@router.post(
    "",
    status_code=202,
    response_model=DocumentAcceptedResponse,
    summary="Upload a document and start ingestion",
    description=_UPLOAD_DESCRIPTION,
    responses={
        200: {
            "model": DocumentDeduplicatedResponse,
            "description": "Exact same file bytes were uploaded before — reusing the existing document.",
        },
        413: {"description": "File exceeds the configured MAX_UPLOAD_MB limit.", "content": {"application/json": {"example": {"detail": "File too large"}}}},
        415: {"description": "Unsupported file type.", "content": {"application/json": {"example": {"detail": "Unsupported file type '.txt'. Supported: .csv, .docx, .pdf, .xlsx"}}}},
        500: {"description": "Unexpected server error (details are logged server-side, never exposed).", "content": {"application/json": {"example": {"detail": "Internal server error"}}}},
    },
)
async def upload_document(
    request: Request, background_tasks: BackgroundTasks, file: UploadFile = File(...)
):
    settings = get_settings()
    repo = Repository(request.app.state.db_pool)

    try:
        extension, mime_type = resolve_upload_type(file.filename)
    except UnsupportedFileTypeError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc

    storage_dir = Path(settings.storage_dir)
    storage_dir.mkdir(parents=True, exist_ok=True)

    # Stream to a temp file while computing SHA-256 and enforcing the size cap.
    sha256 = hashlib.sha256()
    size = 0
    tmp_path = storage_dir / f".upload-{uuid4().hex}"
    try:
        with open(tmp_path, "wb") as out:
            while chunk := await file.read(_UPLOAD_BUFFER):
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise HTTPException(status_code=413, detail="File too large")
                sha256.update(chunk)
                out.write(chunk)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
    file_hash = sha256.hexdigest()

    # Exact-file dedup: same bytes already known → reuse the existing row.
    existing = await repo.find_by_file_hash(file_hash)
    if existing is not None:
        tmp_path.unlink(missing_ok=True)
        return JSONResponse(
            status_code=200,
            content={
                "document_id": str(existing["id"]),
                "status": existing["status"],
                "deduplicated": True,
            },
        )

    # Content-addressed storage: keep the first copy, drop duplicate bytes.
    final_path = storage_dir / f"{file_hash}{extension}"
    if final_path.exists():
        tmp_path.unlink(missing_ok=True)
    else:
        tmp_path.rename(final_path)

    try:
        document_id, job_id = await repo.create_document_with_job(
            name=file.filename or final_path.name,
            file_path=str(final_path),
            mime_type=mime_type,
            size=size,
            file_hash=file_hash,
        )
    except UniqueViolation:
        # A concurrent upload of the same file won the race for the unique
        # file_hash index — treat it as a dedup hit.
        existing = await repo.find_by_file_hash(file_hash)
        return JSONResponse(
            status_code=200,
            content={
                "document_id": str(existing["id"]),
                "status": existing["status"],
                "deduplicated": True,
            },
        )

    # Ingestion runs after the response is sent; the client polls GET below.
    background_tasks.add_task(
        run_ingestion_guarded, request.app.state.db_pool, settings, document_id, job_id
    )
    return {"document_id": str(document_id), "job_id": str(job_id), "status": "processing"}


@router.get(
    "/{document_id}",
    response_model=DocumentStatusResponse,
    summary="Get document and ingestion job status",
    description=(
        "Poll this after uploading. `status` is the document state "
        "(`processing` → `active` | `inactive` | `failed`) and `job_status` "
        "is the latest ingestion job (`pending` → `processing` → `completed` | `failed`). "
        "On failure, `error_code` is a stable machine-readable code "
        "(e.g. `corrupt_file`, `empty_content`, `config_error`) and "
        "`error_message` holds the detail."
    ),
    responses={
        404: {"description": "Unknown document ID.", "content": {"application/json": {"example": {"detail": "Document not found"}}}},
    },
)
async def get_document(request: Request, document_id: UUID):
    repo = Repository(request.app.state.db_pool)
    row = await repo.get_document_with_latest_job(document_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return row
