"""CSV extraction using the standard library csv module.

The whole file becomes one "table" block (tab-separated lines). The dialect
(delimiter, quoting) is sniffed from a sample, falling back to standard
comma-separated parsing. utf-8-sig strips the BOM that Excel adds to CSV
exports.
"""
import csv
from pathlib import Path

from app.ingestion.models import Block, ExtractedDocument


def extract_csv(path: Path) -> ExtractedDocument:
    with open(path, newline="", encoding="utf-8-sig") as handle:
        sample = handle.read(8192)
        handle.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        rows = [
            "\t".join(cell.strip() for cell in row)
            for row in csv.reader(handle, dialect)
        ]
    rows = [row for row in rows if row.strip()]
    blocks = [Block(kind="table", text="\n".join(rows))] if rows else []
    return ExtractedDocument(blocks=blocks)
