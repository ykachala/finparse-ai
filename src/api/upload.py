"""File upload utilities: MIME validation, size enforcement, and SHA-256 hashing."""

import hashlib

from fastapi import HTTPException, UploadFile

ALLOWED_CONTENT_TYPES: frozenset[str] = frozenset(
    {"application/pdf", "image/jpeg", "image/png", "image/tiff"}
)

EXTENSION_MAP: dict[str, str] = {
    "application/pdf": "pdf",
    "image/jpeg": "jpeg",
    "image/png": "png",
    "image/tiff": "tiff",
}


async def read_and_validate_upload(
    file: UploadFile,
    max_size_mb: int,
) -> tuple[bytes, str, str]:
    """
    Read file bytes, validate content type and size.

    Returns (file_bytes, content_type, extension).
    Raises HTTPException on validation failure.
    """
    content_type = file.content_type or ""
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unsupported file type '{content_type}'. "
                f"Allowed: {', '.join(sorted(ALLOWED_CONTENT_TYPES))}"
            ),
        )

    max_bytes = max_size_mb * 1024 * 1024
    file_bytes = await file.read()

    if len(file_bytes) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File size {len(file_bytes)} bytes exceeds maximum of {max_size_mb} MB",
        )

    if len(file_bytes) == 0:
        raise HTTPException(status_code=422, detail="Uploaded file is empty")

    extension = EXTENSION_MAP[content_type]
    return file_bytes, content_type, extension


def compute_sha256(data: bytes) -> str:
    """Return the hex-encoded SHA-256 hash of the given bytes."""
    return hashlib.sha256(data).hexdigest()
