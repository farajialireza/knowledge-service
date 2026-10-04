"""Ingestion orchestration: one function that runs the full flow for a
single document and records the outcome in document/job status.

Flow: extract → normalize → content-hash dedup → chunk → embed → persist.
Extraction libraries are blocking, so they run in a worker thread; embedding
and persistence are async-native.
"""
import asyncio
import logging
from pathlib import Path
from uuid import UUID

from psycopg_pool import AsyncConnectionPool

from app.config import Settings
from app.ingestion.chunking import chunk_document
from app.ingestion.embeddings import embed_chunks
from app.ingestion.extractors import extract
from app.ingestion.hashing import content_hash_of
from app.ingestion.models import ExtractedDocument
from app.ingestion.normalize import normalize_document
from app.ingestion.repository import Repository

logger = logging.getLogger(__name__)


class IngestionError(Exception):
    """Pipeline failure with a stable machine-readable code for the job row."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


async def run_ingestion(
    pool: AsyncConnectionPool, settings: Settings, document_id: UUID, job_id: UUID
) -> None:
    repo = Repository(pool)
    try:
        if not settings.openai_api_key:
            raise IngestionError("config_error", "OPENAI_API_KEY is not configured")

        await repo.set_job_processing(job_id)
        document = await repo.get_document(document_id)
        if document is None:
            raise IngestionError("document_missing", f"Document {document_id} not found")

        # extract + normalize (blocking parsers → worker thread)
        logger.info("Ingesting document %s (%s)", document_id, document["name"])
        extracted = await asyncio.to_thread(
            extract, Path(document["file_path"]), document["mime_type"]
        )
        normalized: ExtractedDocument = normalize_document(extracted)
        if not normalized.blocks:
            raise IngestionError("empty_content", "Extraction produced no usable text")

        # content-level dedup (file-level dedup already happened at upload)
        content_hash = content_hash_of(normalized)
        await repo.set_content_hash(document_id, content_hash)
        if await repo.content_hash_exists(content_hash, exclude=document_id):
            logger.info("Document %s duplicates existing content; marked inactive", document_id)
            await repo.deactivate_document(document_id)
            await repo.complete_job(job_id, note="duplicate_content")
            return

        # chunk → embed → persist (persist flips status to active atomically)
        chunks = chunk_document(
            normalized,
            document_name=document["name"],
            chunk_size=settings.chunk_size_chars,
            chunk_overlap=settings.chunk_overlap_chars,
        )
        vectors = await embed_chunks(chunks, settings)
        await repo.persist_chunks_and_activate(document_id, chunks, vectors)
        await repo.complete_job(job_id)
        logger.info("Document %s ingested: %d chunks", document_id, len(chunks))

    except Exception as exc:
        logger.exception("Ingestion failed for document %s", document_id)
        await _record_failure(repo, document_id, job_id, exc)


async def _record_failure(
    repo: Repository, document_id: UUID, job_id: UUID, exc: Exception
) -> None:
    """Best-effort failure bookkeeping.

    Guarded so that a secondary database error while recording the failure
    does not mask the original error (both end up in the logs).
    """
    code = getattr(exc, "code", type(exc).__name__)
    try:
        await repo.fail_document(document_id)
        await repo.fail_job(job_id, code, str(exc)[:1000])
    except Exception:
        logger.exception("Could not record failure state for document %s", document_id)
