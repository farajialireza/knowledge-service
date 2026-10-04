"""Shared data structures for the ingestion pipeline.

Every format extractor produces an `ExtractedDocument` — a flat list of typed
`Block`s — so that normalization, chunking and embedding never need to know
which file format the content came from.
"""
from dataclasses import dataclass, field
from typing import Literal

BlockKind = Literal["heading", "paragraph", "table"]


@dataclass
class Block:
    """One structural unit of extracted content.

    `section` holds the nearest preceding heading text (or a sheet name for
    spreadsheets); `page` holds the 1-based page number when the format
    provides one. Both feed the chunk context used for embedding.
    """

    kind: BlockKind
    text: str
    level: int | None = None  # heading level (1-6), only for kind="heading"
    page: int | None = None
    section: str | None = None


@dataclass
class ExtractedDocument:
    blocks: list[Block] = field(default_factory=list)


@dataclass
class Chunk:
    """A unit ready for embedding and persistence.

    `context` carries document/section/page provenance; `content` is the
    actual text. Both map directly onto the document_chunks columns.
    """

    index: int
    content: str
    context: str | None
