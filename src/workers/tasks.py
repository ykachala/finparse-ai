"""Celery tasks for async document parsing pipeline."""

import asyncio
import logging

import httpx

from src.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="src.workers.tasks.parse_document_task", bind=True, max_retries=2)
def parse_document_task(self, job_id: str) -> dict:
    """Celery task: run the full parse pipeline for a queued job."""
    from src.config import get_settings
    settings = get_settings()
    try:
        return asyncio.run(_run_parse_pipeline(job_id, settings))
    except Exception as exc:
        logger.exception("Parse pipeline failed for job %s", job_id)
        asyncio.run(_mark_job_failed(job_id, str(exc)))
        raise self.retry(exc=exc, countdown=30)


async def _run_parse_pipeline(job_id: str, settings) -> dict:
    """
    Async implementation of the full parse pipeline.

    Steps:
    1. Load ParseJob and linked Document from DB
    2. Download original file from S3
    3. Preprocess (PDF->images, normalise)
    4. Extract with Claude Vision
    5. Validate with DocumentValidator
    6. Update Document with results
    7. Mark ParseJob complete
    8. Fire webhook if configured
    """
    from src.storage.database import get_db, init_db
    from src.storage.repositories import (
        get_document_by_id,
        get_parse_job,
        update_document,
        update_parse_job,
    )

    init_db(settings.database_url)

    async for db in get_db():
        job = await get_parse_job(db, job_id)
        if not job:
            return {"status": "failed", "error": "job not found"}

        await update_parse_job(db, job_id, status="processing")

        doc = await get_document_by_id(db, job.document_id)
        if not doc:
            await update_parse_job(db, job_id, status="failed", error="document not found")
            return {"status": "failed", "error": "document not found"}

        # Download file from S3
        from src.storage.s3_client import get_s3_client
        s3 = get_s3_client()
        file_data = s3.download_file(doc.s3_key)

        # Preprocess
        from src.preprocessor.processor import DocumentPreprocessor
        preprocessor = DocumentPreprocessor()
        pages = preprocessor.process(file_data, doc.file_type)

        # Extract
        from src.extractor.claude_client import ClaudeVisionClient
        from src.extractor.extractor import DocumentExtractor
        claude = ClaudeVisionClient(api_key=settings.anthropic_api_key)
        extractor = DocumentExtractor(claude)
        raw = extractor.extract(pages, doc.document_hint)

        # Validate
        from src.validators.validator import DocumentValidator
        validator = DocumentValidator()
        try:
            parsed_doc, flags = validator.validate(raw)
            extracted_data = parsed_doc.model_dump()
            confidence = float(extracted_data.get("confidence", 0.0))
            doc_type = extracted_data.get("document_type", doc.document_hint)
            has_errors = any("mismatch" in f or "balance" in f.lower() for f in flags)
        except Exception as exc:
            flags = [f"validation_error: {exc}"]
            extracted_data = raw
            confidence = 0.0
            doc_type = raw.get("document_type", doc.document_hint)
            has_errors = True

        # Update document
        await update_document(
            db,
            doc.id,
            extracted_data=extracted_data,
            confidence=confidence,
            validation_flags=flags,
            has_validation_errors=has_errors,
            document_type=doc_type,
        )

        await update_parse_job(db, job_id, status="complete")

        # Fire webhook
        if job.webhook_url:
            await _fire_webhook(job.webhook_url, job_id, extracted_data, flags)

        # Update batch job if this parse belongs to one
        await _update_batch_for_job(db, job_id, failed=False)

        return {"status": "complete", "job_id": job_id}


async def _mark_job_failed(job_id: str, error: str) -> None:
    from src.config import get_settings
    from src.storage.database import get_db, init_db
    from src.storage.repositories import get_parse_job, update_parse_job

    settings = get_settings()
    init_db(settings.database_url)

    async for db in get_db():
        await update_parse_job(db, job_id, status="failed", error=error)
        await _update_batch_for_job(db, job_id, failed=True)


async def _fire_webhook(webhook_url: str, job_id: str, result: dict, flags: list) -> None:
    payload = {"job_id": job_id, "status": "complete", "result": result, "validation_flags": flags}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(webhook_url, json=payload)
    except Exception as exc:
        logger.warning("Webhook delivery failed for job %s: %s", job_id, exc)


async def _update_batch_for_job(db, job_id: str, failed: bool) -> None:
    """If this parse_job belongs to a batch, update the batch counters."""
    from sqlalchemy import select
    from src.storage.database import BatchJob

    result = await db.execute(
        select(BatchJob).where(BatchJob.parse_job_ids.contains([job_id]))
    )
    batch = result.scalar_one_or_none()
    if not batch:
        return

    if failed:
        batch.failed += 1
    else:
        batch.completed += 1

    total_done = batch.completed + batch.failed
    if total_done >= batch.total:
        batch.status = "failed" if batch.failed == batch.total else "complete"
    else:
        batch.status = "processing"

    await db.commit()
