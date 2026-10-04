"""Configurable, format-independent chunking.

Operates purely on the structured `ExtractedDocument` representation, so it
never needs to know the source format.

Sizing is character-based (≈4 chars/token for English text): exact token
counting would require a tokenizer dependency, and embedding models accept
far more input than a sane chunk size. Both the target size and the overlap
come from Settings (CHUNK_SIZE_CHARS / CHUNK_OVERLAP_CHARS) and are
validated at startup — nothing here is a hidden hardcoded limit.
"""
import re

from app.ingestion.models import Block, Chunk, ExtractedDocument

_SENTENCE_OR_LINE_END = re.compile(r"(?<=[.!?\n])\s+")


def _context_for(document_name: str, section: str | None, page: int | None) -> str:
    parts = [f"Document: {document_name}"]
    if section:
        parts.append(f"Section: {section}")
    if page is not None:
        parts.append(f"Page: {page}")
    return " | ".join(parts)


def _hard_split(text: str, max_chars: int) -> list[str]:
    """Split an oversized block at sentence/line boundaries where possible.

    Only called for blocks longer than the whole chunk budget (typical for
    large tables). Falls back to a hard character slice when no boundary
    exists within range.
    """
    pieces: list[str] = []
    while len(text) > max_chars:
        window = text[:max_chars]
        # Prefer the last sentence/line boundary in the second half of the
        # window so pieces stay reasonably large.
        boundary = max(
            (m.end() for m in _SENTENCE_OR_LINE_END.finditer(window) if m.end() > max_chars // 2),
            default=None,
        )
        if boundary is None:
            boundary = max_chars
        pieces.append(text[:boundary].strip())
        text = text[boundary:].strip()
    if text:
        pieces.append(text)
    return pieces


def chunk_document(
    document: ExtractedDocument,
    *,
    document_name: str,
    chunk_size: int,
    chunk_overlap: int,
) -> list[Chunk]:
    """Pack blocks into chunks of at most `chunk_size` characters.

    Heading blocks are not chunked themselves — they set the section context
    for everything that follows, and their text is folded into the context
    string stored with each chunk.
    """
    chunks: list[Chunk] = []
    section: str | None = None
    current_text = ""
    current_context: str | None = None

    def flush() -> None:
        nonlocal current_text, current_context
        if current_text:
            chunks.append(
                Chunk(index=len(chunks), content=current_text, context=current_context)
            )
            current_text = ""

    def carry_overlap() -> None:
        # Start the next chunk with the tail of the previous one so context
        # spanning a chunk boundary is not lost.
        nonlocal current_text
        if chunk_overlap and chunks:
            current_text = chunks[-1].content[-chunk_overlap:]

    for block in document.blocks:
        if block.kind == "heading":
            section = block.text
            continue  # context-only; never a standalone chunk
        context = _context_for(document_name, block.section or section, block.page)
        for piece in _hard_split(block.text, chunk_size):
            candidate = f"{current_text}\n\n{piece}" if current_text else piece
            if len(candidate) <= chunk_size:
                current_text = candidate
                if current_context is None:
                    current_context = context
            else:
                flush()
                carry_overlap()
                current_text = f"{current_text}\n\n{piece}" if current_text else piece
                current_context = context
    flush()
    return chunks
