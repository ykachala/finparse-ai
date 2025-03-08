from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_api_key
from src.storage.database import ApiKey, get_db
from src.storage.repositories import get_document_by_id, query_documents

router = APIRouter(tags=["documents"])


@router.get("/documents")
async def list_documents(
    vendor: str | None = Query(None),
    doc_type: str | None = Query(None),
    date_from: str | None = Query(None, description="ISO 8601 date, inclusive lower bound"),
    date_to: str | None = Query(None, description="ISO 8601 date, inclusive upper bound"),
    amount_min: float | None = Query(None),
    amount_max: float | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    api_key: ApiKey = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Query extracted document records with optional filters.

    All results are scoped to the authenticated API key.
    """
    documents, total = await query_documents(
        db,
        api_key_id=api_key.id,
        vendor=vendor,
        doc_type=doc_type,
        date_from=date_from,
        date_to=date_to,
        amount_min=amount_min,
        amount_max=amount_max,
        limit=limit,
        offset=offset,
    )

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "id": doc.id,
                "filename": doc.filename,
                "document_type": doc.document_type,
                "confidence": doc.confidence,
                "has_validation_errors": doc.has_validation_errors,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
            }
            for doc in documents
        ],
    }


@router.get("/documents/{document_id}")
async def get_document(
    document_id: str,
    api_key: ApiKey = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Retrieve full extracted data for a single document."""
    doc = await get_document_by_id(db, document_id)
    if not doc or doc.api_key_id != api_key.id:
        raise HTTPException(status_code=404, detail="Document not found")

    return {
        "id": doc.id,
        "filename": doc.filename,
        "file_type": doc.file_type,
        "document_type": doc.document_type,
        "confidence": doc.confidence,
        "has_validation_errors": doc.has_validation_errors,
        "validation_flags": doc.validation_flags,
        "extracted_data": doc.extracted_data,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
    }
