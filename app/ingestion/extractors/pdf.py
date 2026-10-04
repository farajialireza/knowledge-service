"""PDF extraction via pypdf.

pypdf does not expose semantic headings, so structure is preserved as
blank-line-separated paragraphs with their 1-based page number. Page numbers
give chunks useful provenance even without heading context.
"""
import re
from pathlib import Path

from pypdf import PdfReader

from app.ingestion.models import Block, ExtractedDocument

_BLANK_RUN = re.compile(r"\n\s*\n")


def extract_pdf(path: Path) -> ExtractedDocument:
    reader = PdfReader(str(path))
    blocks: list[Block] = []
    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        for paragraph in _BLANK_RUN.split(text):
            paragraph = paragraph.strip()
            if paragraph:
                blocks.append(Block(kind="paragraph", text=paragraph, page=page_number))
    return ExtractedDocument(blocks=blocks)
