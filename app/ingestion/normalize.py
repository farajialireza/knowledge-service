"""Text normalization applied uniformly to every extracted block.

Normalization runs BEFORE the content hash and chunking, so trivial
whitespace/encoding differences neither defeat deduplication nor create
noisy chunks.
"""
import re
import unicodedata

from app.ingestion.models import Block, ExtractedDocument

# C0/C1 control characters except \n and \t, which carry layout meaning.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
_RUNS_OF_SPACES = re.compile(r"[ \t]{2,}")
_RUNS_OF_BLANK_LINES = re.compile(r"\n{3,}")


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = _CONTROL_CHARS.sub("", text)
    text = _RUNS_OF_SPACES.sub(" ", text)
    # Normalize line by line so trailing indent doesn't survive stripping.
    lines = (line.strip() for line in text.splitlines())
    text = "\n".join(lines)
    text = _RUNS_OF_BLANK_LINES.sub("\n\n", text)
    return text.strip()


def normalize_document(document: ExtractedDocument) -> ExtractedDocument:
    """Normalize every block in place; blocks that become empty are dropped."""
    kept: list[Block] = []
    for block in document.blocks:
        block.text = normalize_text(block.text)
        if block.text:
            kept.append(block)
    return ExtractedDocument(blocks=kept)
