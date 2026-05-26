import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_api_key
from src.api.upload import compute_sha256, read_and_validate_upload
from src.config import get_settings
from src.storage.database import ApiKey, get_db
from src.storage.repositories import (
    create_batch_job,
    create_document,
    create_parse_job,
    get_batch_job,
    get_document_by_hash,
    update_parse_job,
)
from src.storage.s3_client import get_s3_client

router = APIRouter(tags=["batch"])


@router.post("/batch", status_code=202)
async def submit_batch(
    files: list[UploadFile],
    document_hint: str | None = Form(None),
    webhook_url: str | None = Form(None),
    api_key: ApiKey = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Submit up to 50 documents for async batch parsing.

    Returns a batch_id. Poll GET /batch/{batch_id} for aggregate status.
    Individual results are accessible via GET /parse/{job_id} per document.
    """
    settings = get_settings()

    if len(files) > settings.max_batch_size:
        raise HTTPException(
            status_code=422,
            detail=f"Batch size {len(files)} exceeds maximum of {settings.max_batch_size}",
        )
    if not files:
        raise HTTPException(status_code=422, detail="No files provided")

    s3 = get_s3_client()
    parse_job_ids: list[str] = []

    for file in files:
        file_bytes, content_type, extension = await read_and_validate_upload(
            file, settings.max_file_size_mb
        )
        file_hash = compute_sha256(file_bytes)

        # Idempotency per file
        existing_doc = await get_document_by_hash(db, file_hash)
        if existing_doc and existing_doc.api_key_id == api_key.id:
            reused = False
            for job in existing_doc.parse_jobs:
                if job.status in ("complete", "queued", "processing"):
                    parse_job_ids.append(job.id)
                    reused = True
                    break
            if reused:
                continue

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
        await create_parse_job(db, job_id=job_id, webhook_url=webhook_url)
        await update_parse_job(db, job_id, document_id=doc.id)
        parse_job_ids.append(job_id)

    # Create BatchJob record
    batch_id = f"batch_{uuid.uuid4().hex}"
    await create_batch_job(db, batch_id=batch_id, parse_job_ids=parse_job_ids)

    # Enqueue all parse tasks
    from src.workers.tasks import parse_document_task
    for job_id in parse_job_ids:
        celery_result = parse_document_task.delay(job_id)
        await update_parse_job(db, job_id, celery_task_id=celery_result.id)

    return {
        "batch_id": batch_id,
        "status": "queued",
        "total": len(parse_job_ids),
        "parse_job_ids": parse_job_ids,
    }


@router.get("/batch/{batch_id}")
async def get_batch_status(
    batch_id: str,
    api_key: ApiKey = Depends(get_current_api_key),  # noqa: ARG001
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Poll for batch job aggregate status."""
    batch = await get_batch_job(db, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch job not found")

    return {
        "batch_id": batch.id,
        "status": batch.status,
        "total": batch.total,
        "completed": batch.completed,
        "failed": batch.failed,
        "parse_job_ids": batch.parse_job_ids,
        "created_at": batch.created_at.isoformat() if batch.created_at else None,
    }
