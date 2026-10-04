"""All SQL for the ingestion pipeline. Direct psycopg, no ORM.

Status model (enforced here and in the pipeline):
- document: processing → active | inactive (content duplicate) | failed
- job:      pending → processing → completed | failed
A document is only ever set to `active` inside the same transaction that
inserts its chunks, so a failed or half-written ingestion can never surface
as retrievable.
"""
import logging
from uuid import UUID

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.ingestion.models import Chunk

logger = logging.getLogger(__name__)

_INSERT_CHUNK_SQL = """
INSERT INTO ai_assistant.document_chunks
    (document_id, chunk_index, content, context, embedding)
VALUES (%(document_id)s, %(chunk_index)s, %(content)s, %(context)s, %(embedding)s::vector)
"""


def _vector_literal(vector: list[float]) -> str:
    """Serialize an embedding to pgvector's text input format: '[v1,v2,...]'.

    Avoids an extra pgvector-python dependency; the ::vector cast in the SQL
    performs the conversion server-side. %.8g keeps full float32 precision.
    """
    return "[" + ",".join(f"{value:.8g}" for value in vector) + "]"


class Repository:
    def __init__(self, pool: AsyncConnectionPool):
        self._pool = pool

    # ---- lookup ----------------------------------------------------------

    async def find_by_file_hash(self, file_hash: str) -> dict | None:
        async with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT id, status FROM ai_assistant.documents WHERE file_hash = %s",
                (file_hash,),
            )
            return await cur.fetchone()

    async def get_document(self, document_id: UUID) -> dict | None:
        async with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT id, name, file_path, mime_type, status "
                "FROM ai_assistant.documents WHERE id = %s",
                (document_id,),
            )
            return await cur.fetchone()

    async def content_hash_exists(self, content_hash: str, *, exclude: UUID) -> bool:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                "SELECT EXISTS(SELECT 1 FROM ai_assistant.documents "
                "WHERE content_hash = %s AND id <> %s)",
                (content_hash, exclude),
            )
            return (await cursor.fetchone())[0]

    async def get_document_with_latest_job(self, document_id: UUID) -> dict | None:
        async with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT d.id, d.name, d.mime_type, d.size, d.file_hash, d.content_hash,
                       d.status, d.created_at, d.updated_at,
                       j.status AS job_status, j.error_code, j.error_message
                FROM ai_assistant.documents d
                LEFT JOIN LATERAL (
                    SELECT status, error_code, error_message
                    FROM ai_assistant.ingestion_jobs
                    WHERE document_id = d.id
                    ORDER BY created_at DESC
                    LIMIT 1
                ) j ON true
                WHERE d.id = %s
                """,
                (document_id,),
            )
            return await cur.fetchone()

    # ---- document + job creation ----------------------------------------

    async def create_document_with_job(
        self, *, name: str, file_path: str, mime_type: str, size: int, file_hash: str
    ) -> tuple[UUID, UUID]:
        """Insert the document (status 'processing') and its pending job atomically."""
        async with self._pool.connection() as conn, conn.transaction(), conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO ai_assistant.documents (name, file_path, mime_type, size, file_hash) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (name, file_path, mime_type, size, file_hash),
            )
            document_id = (await cur.fetchone())[0]
            await cur.execute(
                "INSERT INTO ai_assistant.ingestion_jobs (document_id) VALUES (%s) RETURNING id",
                (document_id,),
            )
            job_id = (await cur.fetchone())[0]
        return document_id, job_id

    # ---- pipeline state transitions --------------------------------------

    async def set_job_processing(self, job_id: UUID) -> None:
        async with self._pool.connection() as conn:
            await conn.execute(
                "UPDATE ai_assistant.ingestion_jobs "
                "SET status = 'processing', started_at = NOW() WHERE id = %s",
                (job_id,),
            )

    async def set_content_hash(self, document_id: UUID, content_hash: str) -> None:
        async with self._pool.connection() as conn:
            await conn.execute(
                "UPDATE ai_assistant.documents "
                "SET content_hash = %s, updated_at = NOW() WHERE id = %s",
                (content_hash, document_id),
            )

    async def persist_chunks_and_activate(
        self, document_id: UUID, chunks: list[Chunk], vectors: list[list[float]]
    ) -> None:
        """Insert all chunks and flip the document to 'active' in ONE transaction.

        Atomicity is the guarantee that an active document always has its
        full chunk set — a crash here rolls back both.
        """
        rows = [
            {
                "document_id": document_id,
                "chunk_index": chunk.index,
                "content": chunk.content,
                "context": chunk.context,
                "embedding": _vector_literal(vector),
            }
            for chunk, vector in zip(chunks, vectors)
        ]
        async with self._pool.connection() as conn, conn.transaction(), conn.cursor() as cur:
            await cur.executemany(_INSERT_CHUNK_SQL, rows)
            await cur.execute(
                "UPDATE ai_assistant.documents "
                "SET status = 'active', updated_at = NOW() WHERE id = %s",
                (document_id,),
            )

    async def complete_job(self, job_id: UUID, *, note: str | None = None) -> None:
        # `note` reuses the nullable error_code column for benign outcomes
        # (e.g. 'duplicate_content') without touching the schema.
        async with self._pool.connection() as conn:
            await conn.execute(
                "UPDATE ai_assistant.ingestion_jobs "
                "SET status = 'completed', finished_at = NOW(), error_code = %s WHERE id = %s",
                (note, job_id),
            )

    async def deactivate_document(self, document_id: UUID) -> None:
        async with self._pool.connection() as conn:
            await conn.execute(
                "UPDATE ai_assistant.documents "
                "SET status = 'inactive', updated_at = NOW() WHERE id = %s",
                (document_id,),
            )

    async def fail_document(self, document_id: UUID) -> None:
        async with self._pool.connection() as conn:
            await conn.execute(
                "UPDATE ai_assistant.documents "
                "SET status = 'failed', updated_at = NOW() WHERE id = %s",
                (document_id,),
            )

    async def fail_job(self, job_id: UUID, code: str, message: str) -> None:
        async with self._pool.connection() as conn:
            await conn.execute(
                "UPDATE ai_assistant.ingestion_jobs "
                "SET status = 'failed', error_code = %s, error_message = %s, "
                "finished_at = NOW() WHERE id = %s",
                (code, message, job_id),
            )
