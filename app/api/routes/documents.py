"""Document management endpoints."""

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import Document
from app.schemas.documents import DocumentResponse, IngestRequest, IngestResponse
from app.services.ingestion import IngestionService

router = APIRouter()


@router.post("/ingest", response_model=IngestResponse)
async def ingest_documents(
    request: IngestRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> IngestResponse:
    """
    Ingest transcript files (.txt) from a directory.

    If directory_path is not provided, uses DOCUMENTS_PATH from environment.
    """
    service = IngestionService(db)

    try:
        result = await service.ingest_directory(request.directory_path)
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {e}")


@router.get("/documents", response_model=list[DocumentResponse])
async def list_documents(
    document_type: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[DocumentResponse]:
    """List all ingested documents with optional filtering."""
    query = select(Document).order_by(Document.ingested_at.desc())

    if document_type:
        query = query.where(Document.document_type == document_type)

    result = await db.execute(query)
    documents = result.scalars().all()

    return [DocumentResponse.model_validate(doc) for doc in documents]


@router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    """Get a specific document by ID."""
    result = await db.execute(select(Document).where(Document.id == document_id))
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    return DocumentResponse.model_validate(document)


@router.delete("/documents/{document_id}")
async def delete_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Delete a document and its chunks."""
    result = await db.execute(select(Document).where(Document.id == document_id))
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    await db.delete(document)
    return {"status": "deleted", "document_id": str(document_id)}
