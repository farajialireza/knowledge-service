"""SHA-256 hashing helpers for file-level and content-level deduplication."""
import hashlib

from app.ingestion.models import ExtractedDocument


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def content_hash_of(document: ExtractedDocument) -> str:
    """Hash the normalized text of a whole document.

    Two different source files (e.g. a PDF and a DOCX export of the same
    text) produce the same hash, enabling content-based deduplication that
    the raw file hash cannot catch. Block boundaries are marked with a NUL
    separator so "ab"+"c" and "a"+"bc" cannot collide.
    """
    h = hashlib.sha256()
    for block in document.blocks:
        h.update(block.text.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()
