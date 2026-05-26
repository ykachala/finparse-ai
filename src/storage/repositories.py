from sqlalchemy import Float as SAFloat
from sqlalchemy import cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.database import ApiKey, BatchJob, Document, ParseJob


async def get_document_by_hash(db: AsyncSession, file_hash: str) -> Document | None:
    """Retrieve a document by its SHA-256 hash."""
    result = await db.execute(select(Document).where(Document.hash == file_hash))
    return result.scalar_one_or_none()


async def get_document_by_id(db: AsyncSession, doc_id: str) -> Document | None:
    """Retrieve a document by its UUID."""
    result = await db.execute(select(Document).where(Document.id == doc_id))
    return result.scalar_one_or_none()


async def create_document(db: AsyncSession, **kwargs: object) -> Document:
    """Create and persist a new Document record."""
    doc = Document(**kwargs)
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return doc


async def update_document(db: AsyncSession, doc_id: str, **kwargs: object) -> Document:
    """Update fields on an existing Document and return the updated record."""
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one()
    for key, value in kwargs.items():
        setattr(doc, key, value)
    await db.commit()
    await db.refresh(doc)
    return doc


async def get_parse_job(db: AsyncSession, job_id: str) -> ParseJob | None:
    """Retrieve a ParseJob by its ID."""
    result = await db.execute(select(ParseJob).where(ParseJob.id == job_id))
    return result.scalar_one_or_none()


async def create_parse_job(
    db: AsyncSession,
    job_id: str,
    webhook_url: str | None = None,
) -> ParseJob:
    """Create and persist a new ParseJob record."""
    job = ParseJob(id=job_id, webhook_url=webhook_url)
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


async def update_parse_job(db: AsyncSession, job_id: str, **kwargs: object) -> ParseJob:
    """Update fields on an existing ParseJob and return the updated record."""
    result = await db.execute(select(ParseJob).where(ParseJob.id == job_id))
    job = result.scalar_one()
    for key, value in kwargs.items():
        setattr(job, key, value)
    await db.commit()
    await db.refresh(job)
    return job


async def get_batch_job(db: AsyncSession, batch_id: str) -> BatchJob | None:
    """Retrieve a BatchJob by its ID."""
    result = await db.execute(select(BatchJob).where(BatchJob.id == batch_id))
    return result.scalar_one_or_none()


async def create_batch_job(
    db: AsyncSession,
    batch_id: str,
    parse_job_ids: list[str],
) -> BatchJob:
    """Create and persist a new BatchJob record."""
    batch = BatchJob(id=batch_id, parse_job_ids=parse_job_ids, total=len(parse_job_ids))
    db.add(batch)
    await db.commit()
    await db.refresh(batch)
    return batch


async def query_documents(
    db: AsyncSession,
    api_key_id: str,
    *,
    vendor: str | None,
    doc_type: str | None,
    date_from: str | None,
    date_to: str | None,
    amount_min: float | None,
    amount_max: float | None,
    limit: int,
    offset: int,
) -> tuple[list[Document], int]:
    """
    Query documents with optional filters, enforcing tenant isolation by api_key_id.

    Vendor filter matches against extracted_data->vendor->name (ILIKE).
    Date filter matches against extracted_data->document_meta->invoice_date.
    Amount filter matches against extracted_data->totals->total cast to float.
    """
    base_filter = Document.api_key_id == api_key_id
    query = select(Document).where(base_filter)
    count_query = select(func.count()).select_from(Document).where(base_filter)

    if doc_type is not None:
        query = query.where(Document.document_type == doc_type)
        count_query = count_query.where(Document.document_type == doc_type)

    if vendor is not None:
        vendor_filter = Document.extracted_data["vendor"]["name"].astext.ilike(
            f"%{vendor}%"
        )
        query = query.where(vendor_filter)
        count_query = count_query.where(vendor_filter)

    if date_from is not None:
        date_filter_from = (
            Document.extracted_data["document_meta"]["invoice_date"].astext >= date_from
        )
        query = query.where(date_filter_from)
        count_query = count_query.where(date_filter_from)

    if date_to is not None:
        date_filter_to = (
            Document.extracted_data["document_meta"]["invoice_date"].astext <= date_to
        )
        query = query.where(date_filter_to)
        count_query = count_query.where(date_filter_to)

    if amount_min is not None:
        amount_filter_min = (
            cast(Document.extracted_data["totals"]["total"].astext, SAFloat) >= amount_min
        )
        query = query.where(amount_filter_min)
        count_query = count_query.where(amount_filter_min)

    if amount_max is not None:
        amount_filter_max = (
            cast(Document.extracted_data["totals"]["total"].astext, SAFloat) <= amount_max
        )
        query = query.where(amount_filter_max)
        count_query = count_query.where(amount_filter_max)

    query = query.order_by(Document.created_at.desc()).limit(limit).offset(offset)

    results = await db.execute(query)
    count_result = await db.execute(count_query)

    documents = list(results.scalars().all())
    total = count_result.scalar_one()

    return documents, total


async def get_api_key_by_hash(db: AsyncSession, key_hash: str) -> ApiKey | None:
    """Retrieve an ApiKey by its SHA-256 hash."""
    result = await db.execute(select(ApiKey).where(ApiKey.key_hash == key_hash))
    return result.scalar_one_or_none()
