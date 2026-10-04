"""Embedding generation via the OpenAI embeddings API.

Model defaults to text-embedding-3-small, whose native 1536 dimensions match
the document_chunks.embedding VECTOR(1536) column.
"""
import logging

from openai import AsyncOpenAI

from app.config import Settings
from app.ingestion.models import Chunk

logger = logging.getLogger(__name__)

# Process-wide async client; httpx-based and safe to share across tasks.
_client: AsyncOpenAI | None = None


def _get_client(settings: Settings) -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url or None,
        )
    return _client


def embedding_input(chunk: Chunk) -> str:
    """Text actually sent to the embedding model: context first, then content."""
    if chunk.context:
        return f"{chunk.context}\n\n{chunk.content}"
    return chunk.content


async def embed_chunks(chunks: list[Chunk], settings: Settings) -> list[list[float]]:
    """Embed all chunks in configurable-size batches, preserving order."""
    if not chunks:
        return []
    client = _get_client(settings)
    vectors: list[list[float]] = []
    batch_size = settings.embedding_batch_size
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        logger.info(
            "Embedding batch %d-%d of %d chunks",
            start + 1,
            start + len(batch),
            len(chunks),
        )
        response = await client.embeddings.create(
            model=settings.embedding_model,
            input=[embedding_input(chunk) for chunk in batch],
        )
        # The API preserves input order in practice; sort defensively anyway.
        vectors.extend(item.embedding for item in sorted(response.data, key=lambda d: d.index))
    return vectors
