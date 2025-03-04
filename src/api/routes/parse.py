import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_api_key
from src.api.upload import compute_sha256, read_and_validate_upload
from src.config import get_settings
from src.storage.database import ApiKey, get_db
from src.storage.repositories import (
    create_document,
    create_parse_job,
    get_document_by_hash,
    get_document_by_id,
    get_parse_job,
)
from src.storage.s3_client import get_s3_client

router = APIRouter(tags=["parse"])


@router.post("/parse", status_code=202)
async def submit_parse(
    file: UploadFile,
    document_hint: str | None = Form(None),
    webhook_url: str | None = Form(None),
    api_key: ApiKey = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Submit a financial document for async parsing.

    Validates file type and size, computes SHA-256 for idempotency, uploads to S3,
    creates Document and ParseJob records, and enqueues Celery task.

    Returns 202 with job_id immediately. Poll GET /parse/{job_id} for results.
    """
    settings = get_settings()

    # Validate content type and size
    file_bytes, content_type, extension = await read_and_validate_upload(
        file, settings.max_file_size_mb
    )

    # Compute SHA-256 for idempotency check
    file_hash = compute_sha256(file_bytes)

    # Idempotency: return existing result if same document already processed
    existing_doc = await get_document_by_hash(db, file_hash)
    if existing_doc and existing_doc.api_key_id == api_key.id:
        # Find the latest parse job for this document
        for job in existing_doc.parse_jobs:
            if job.status == "complete":
                return {"job_id": job.id, "status": "complete", "idempotent": True}
        # Document exists but may still be processing
        for job in existing_doc.parse_jobs:
            if job.status in ("queued", "processing"):
                return {"job_id": job.id, "status": job.status, "idempotent": True}

    # Upload to S3
    s3 = get_s3_client()
    s3_key = f"documents/{api_key.id}/{file_hash}.{extension}"
    s3.upload_file(key=s3_key, data=file_bytes, content_type=content_type)

    # Create Document record
    filename = file.filename or f"{file_hash}.{extension}"
    doc = await create_document(
        db,
        hash=file_hash,
        filename=filename,
        file_type=extension,
        document_hint=document_hint,
        s3_key=s3_key,
        s3_bucket=s3.bucket,
        api_key_id=api_key.id,
        extracted_data={},
        validation_flags=[],
    )

    # Create ParseJob record
    job_id = f"parse_{uuid.uuid4().hex}"
    job = await create_parse_job(db, job_id=job_id, webhook_url=webhook_url)

    # Link job to document
    from src.storage.repositories import update_parse_job

    await update_parse_job(db, job_id, document_id=doc.id)

    # Enqueue Celery task
    from src.workers.tasks import parse_document_task

    celery_result = parse_document_task.delay(job_id)
    await update_parse_job(db, job_id, celery_task_id=celery_result.id)

    return {"job_id": job_id, "status": "queued"}


@router.get("/parse/{job_id}")
async def get_parse_status(
    job_id: str,
    api_key: ApiKey = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Poll for parse job status and result."""
    job = await get_parse_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    response: dict = {"job_id": job.id, "status": job.status}

    if job.status == "complete" and job.document_id:
        doc = await get_document_by_id(db, job.document_id)
        if doc:
            response["result"] = doc.extracted_data
            response["confidence"] = doc.confidence
            response["validation_flags"] = doc.validation_flags
    elif job.status == "failed":
        response["error"] = job.error

    return response


@router.post("/parse/sync")
async def parse_sync(
    file: UploadFile,
    document_hint: str | None = Form(None),
    api_key: ApiKey = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Synchronous parse endpoint for small documents (< 5 MB).

    Runs the full preprocessing-extraction-validation pipeline inline
    and returns the structured result immediately.
    """
    import asyncio

    from src.workers.tasks import _run_parse_pipeline

    settings = get_settings()
    sync_size_limit_mb = 5

    file_bytes, content_type, extension = await read_and_validate_upload(
        file, sync_size_limit_mb
    )

    file_hash = compute_sha256(file_bytes)

    # Check for existing result
    existing_doc = await get_document_by_hash(db, file_hash)
    if existing_doc and existing_doc.api_key_id == api_key.id:
        for job in existing_doc.parse_jobs:
            if job.status == "complete":
                return {
                    "status": "complete",
                    "idempotent": True,
                    "result": existing_doc.extracted_data,
                    "confidence": existing_doc.confidence,
                    "validation_flags": existing_doc.validation_flags,
                }

    # Upload to S3
    s3 = get_s3_client()
    s3_key = f"documents/{api_key.id}/{file_hash}.{extension}"
    s3.upload_file(key=s3_key, data=file_bytes, content_type=content_type)

    filename = file.filename or f"{file_hash}.{extension}"
    doc = await create_document(
        db,
        hash=file_hash,
        filename=filename,
        file_type=extension,
        document_hint=document_hint,
        s3_key=s3_key,
        s3_bucket=s3.bucket,
        api_key_id=api_key.id,
        extracted_data={},
        validation_flags=[],
    )

    job_id = f"parse_{uuid.uuid4().hex}"
    await create_parse_job(db, job_id=job_id)

    from src.storage.repositories import update_parse_job

    await update_parse_job(db, job_id, document_id=doc.id)

    # Run the pipeline inline
    result = await asyncio.wait_for(
        _run_parse_pipeline(job_id, settings),
        timeout=settings.sync_parse_timeout_seconds,
    )

    # Re-fetch updated document
    updated_doc = await get_document_by_id(db, doc.id)
    if updated_doc:
        return {
            "status": result.get("status", "complete"),
            "result": updated_doc.extracted_data,
            "confidence": updated_doc.confidence,
            "validation_flags": updated_doc.validation_flags,
        }

    return result
