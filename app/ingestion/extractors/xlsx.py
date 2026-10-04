"""XLSX extraction via openpyxl.

Each non-empty worksheet becomes one "table" block whose section is the
sheet name. Rows are joined as tab-separated lines. `read_only=True` keeps
memory usage flat for large sheets; `data_only=True` returns cached formula
results instead of formula strings.
"""
from pathlib import Path

from openpyxl import load_workbook

from app.ingestion.models import Block, ExtractedDocument


def extract_xlsx(path: Path) -> ExtractedDocument:
    workbook = load_workbook(filename=str(path), read_only=True, data_only=True)
    blocks: list[Block] = []
    try:
        for sheet in workbook.worksheets:
            rows = []
            for row in sheet.iter_rows(values_only=True):
                cells = ["" if value is None else str(value) for value in row]
                if any(cell.strip() for cell in cells):
                    rows.append("\t".join(cells).rstrip("\t"))
            if rows:
                blocks.append(
                    Block(kind="table", text="\n".join(rows), section=sheet.title)
                )
    finally:
        workbook.close()
    return ExtractedDocument(blocks=blocks)
