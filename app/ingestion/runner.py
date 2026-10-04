"""Background execution of ingestion jobs.

Runs ingestion as an in-process background task (no Celery/Redis by design).
A semaphore caps concurrent ingestions so a burst of uploads cannot exhaust
the database pool or the OpenAI rate budget. Note: tasks live in this
process — a restart mid-ingestion leaves the document in 'processing', which
an operator can re-drive later; it is never retrievable as 'active'.
"""
import asyncio
import logging
from uuid import UUID

from psycopg_pool import AsyncConnectionPool

from app.config import Settings
from app.ingestion.pipeline import run_ingestion

logger = logging.getLogger(__name__)

_semaphore: asyncio.Semaphore | None = None


def _get_semaphore(settings: Settings) -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(settings.ingestion_max_concurrent)
    return _semaphore


async def run_ingestion_guarded(
    pool: AsyncConnectionPool, settings: Settings, document_id: UUID, job_id: UUID
) -> None:
    async with _get_semaphore(settings):
        await run_ingestion(pool, settings, document_id, job_id)
