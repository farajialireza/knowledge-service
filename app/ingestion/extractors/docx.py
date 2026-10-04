"""DOCX extraction via python-docx.

python-docx exposes paragraphs and tables as separate lists; to preserve the
real reading order we walk the underlying XML body and rebuild both item
types in document order.
"""
import re
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.ingestion.models import Block, ExtractedDocument

_HEADING_STYLE = re.compile(r"^Heading (\d)$")


def _iter_block_items(document: Document):
    for child in document.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, document)
        elif child.tag == qn("w:tbl"):
            yield Table(child, document)


def _table_to_text(table: Table) -> str:
    rows = []
    for row in table.rows:
        cells = [cell.text.strip() for cell in row.cells]
        if any(cells):  # skip fully empty rows
            rows.append("\t".join(cells))
    return "\n".join(rows)


def extract_docx(path: Path) -> ExtractedDocument:
    document = Document(str(path))
    blocks: list[Block] = []
    for item in _iter_block_items(document):
        if isinstance(item, Paragraph):
            text = item.text.strip()
            if not text:
                continue
            style = item.style.name if item.style is not None else ""
            match = _HEADING_STYLE.match(style)
            if match:
                blocks.append(Block(kind="heading", text=text, level=int(match.group(1))))
            elif style == "Title":
                blocks.append(Block(kind="heading", text=text, level=1))
            else:
                blocks.append(Block(kind="paragraph", text=text))
        else:  # Table
            text = _table_to_text(item)
            if text:
                blocks.append(Block(kind="table", text=text))
    return ExtractedDocument(blocks=blocks)
