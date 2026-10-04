"""Response schemas for the HTTP API (documentation + serialization only).

These models describe what the API returns; they add no behavior.
"""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

DocumentStatus = Literal["processing", "active", "inactive", "failed"]
JobStatus = Literal["pending", "processing", "completed", "failed"]


class DocumentAcceptedResponse(BaseModel):
    """202 — upload accepted; ingestion runs in the background."""

    document_id: UUID = Field(examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"])
    job_id: UUID = Field(examples=["9b2f8c1e-4a5d-4e6f-8c7b-1a2b3c4d5e6f"])
    status: Literal["processing"] = Field(
        description="Initial document status. Poll GET /documents/{document_id}."
    )


class DocumentDeduplicatedResponse(BaseModel):
    """200 — the exact same file bytes were uploaded before (SHA-256 match)."""

    document_id: UUID = Field(description="ID of the pre-existing document row.")
    status: DocumentStatus = Field(description="Current status of that existing document.")
    deduplicated: Literal[True] = True


class DocumentStatusResponse(BaseModel):
    """Current document state plus its most recent ingestion job."""

    id: UUID
    name: str = Field(description="Original uploaded file name.")
    mime_type: str
    size: int = Field(description="File size in bytes.")
    file_hash: str = Field(description="SHA-256 of the raw file bytes.")
    content_hash: str | None = Field(
        description="SHA-256 of the normalized extracted content; null until extraction runs."
    )
    status: DocumentStatus = Field(
        description=(
            "processing → active (retrievable) | inactive (content duplicate) | failed. "
            "A document is only active after its chunks were fully written."
        )
    )
    created_at: datetime
    updated_at: datetime
    job_status: JobStatus | None = Field(description="Status of the latest ingestion job.")
    error_code: str | None = Field(
        description="Stable machine-readable failure code (e.g. corrupt_file, empty_content, "
        "config_error, document_missing), or 'duplicate_content' on a completed duplicate job."
    )
    error_message: str | None = Field(description="Human-readable failure detail, if any.")


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["up", "down"]


class DocumentListItem(BaseModel):
    """One row of the admin document list."""

    id: UUID
    name: str
    mime_type: str
    size: int = Field(description="File size in bytes.")
    status: DocumentStatus
    usage_count: int
    last_used_at: datetime | None
    created_at: datetime
    updated_at: datetime
    chunk_count: int = Field(description="Number of stored chunks (0 until ingestion finishes).")


class DocumentListResponse(BaseModel):
    items: list[DocumentListItem]
    total: int = Field(description="Total number of documents (ignores pagination).")
    limit: int
    offset: int


class IngestionJobResponse(BaseModel):
    """One ingestion job from a document's history."""

    id: UUID
    document_id: UUID
    status: JobStatus
    error_code: str | None
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class DocumentStatusUpdateRequest(BaseModel):
    """Allowed admin status transitions. `processing` and `failed` are owned by
    the ingestion pipeline and cannot be set manually."""

    status: Literal["active", "inactive"]
