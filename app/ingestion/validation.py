"""Upload validation: file-type allowlist and size policy.

MIME types of uploads are client-supplied and unreliable, so validation is
keyed off the file extension, which is then mapped to a canonical MIME type
stored on the document row.
"""

# Canonical MIME type per supported extension.
ALLOWED_TYPES: dict[str, str] = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument-wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".csv": "text/csv",
}


class UnsupportedFileTypeError(Exception):
    pass


def resolve_upload_type(filename: str | None) -> tuple[str, str]:
    """Return (extension, canonical mime type) or raise UnsupportedFileTypeError."""
    if not filename or "." not in filename:
        raise UnsupportedFileTypeError("File name has no extension")
    ext = "." + filename.rsplit(".", 1)[1].lower()
    mime = ALLOWED_TYPES.get(ext)
    if mime is None:
        supported = ", ".join(sorted(ALLOWED_TYPES))
        raise UnsupportedFileTypeError(
            f"Unsupported file type '{ext}'. Supported: {supported}"
        )
    return ext, mime
