"""Format-specific extractors dispatched by canonical MIME type.

Each extractor is a sync function (the underlying libraries are blocking);
the pipeline offloads them to a worker thread via `asyncio.to_thread`.
"""
from pathlib import Path

from app.ingestion.extractors import csv as csv_extractor
from app.ingestion.extractors import docx as docx_extractor
from app.ingestion.extractors import pdf as pdf_extractor
from app.ingestion.extractors import xlsx as xlsx_extractor
from app.ingestion.models import ExtractedDocument


class ExtractionError(Exception):
    """Raised when a file cannot be parsed; carries a stable error code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


_EXTRACTORS = {
    "application/pdf": pdf_extractor.extract_pdf,
    "application/vnd.openxmlformats-officedocument-wordprocessingml.document": docx_extractor.extract_docx,
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": xlsx_extractor.extract_xlsx,
    "text/csv": csv_extractor.extract_csv,
}


def extract(path: Path, mime_type: str) -> ExtractedDocument:
    extractor = _EXTRACTORS.get(mime_type)
    if extractor is None:
        raise ExtractionError("unsupported_type", f"No extractor for MIME type '{mime_type}'")
    try:
        return extractor(path)
    except ExtractionError:
        raise
    except Exception as exc:
        # Wrap parser-library errors in a stable code so the pipeline can
        # record "corrupt_file" instead of leaking library-specific types.
        raise ExtractionError("corrupt_file", f"Failed to parse {path.name}: {exc}") from exc
