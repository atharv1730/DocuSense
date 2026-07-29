import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.db import get_db
from app.auth import get_current_user
from app.storage import storage
from app.pipeline.process import process_document
from app.schemas.document import DocumentOut
from app.config import settings
from typing import List

router = APIRouter(prefix="/workspaces/{workspace_id}/documents", tags=["documents"])

MAX_BYTES = settings.MAX_UPLOAD_MB * 1024 * 1024


async def verify_workspace(workspace_id: str, user: dict, db: AsyncSession):
    result = await db.execute(
        text("SELECT id FROM workspaces WHERE id = :id AND user_id = :uid"),
        {"id": workspace_id, "uid": str(user["id"])},
    )
    if not result.mappings().first():
        raise HTTPException(status_code=404, detail="Workspace not found")


@router.get("", response_model=List[DocumentOut])
async def list_documents(
    workspace_id: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await verify_workspace(workspace_id, user, db)
    result = await db.execute(
        text("SELECT * FROM documents WHERE workspace_id = :wid ORDER BY created_at DESC"),
        {"wid": workspace_id},
    )
    return [dict(r) for r in result.mappings().all()]


@router.post("", response_model=DocumentOut, status_code=201)
async def upload_document(
    workspace_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await verify_workspace(workspace_id, user, db)

    # Validate file type
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    # Read and validate size
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"File exceeds {settings.MAX_UPLOAD_MB}MB limit"
        )

    # Save file
    file_id = f"{uuid.uuid4()}.pdf"
    import io
    storage_path = storage.save(file_id, io.BytesIO(data))

    # Create document record
    doc_id = str(uuid.uuid4())
    await db.execute(
        text("""
            INSERT INTO documents
                (id, workspace_id, filename, storage_path, size_bytes, status)
            VALUES
                (:id, :wid, :filename, :path, :size, 'uploaded')
        """),
        {
            "id": doc_id,
            "wid": workspace_id,
            "filename": file.filename,
            "path": storage_path,
            "size": len(data),
        },
    )
    await db.commit()

    # Fire background processing
    background_tasks.add_task(process_document, doc_id, db)

    result = await db.execute(
        text("SELECT * FROM documents WHERE id = :id"),
        {"id": doc_id},
    )
    return dict(result.mappings().one())


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    workspace_id: str,
    document_id: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await verify_workspace(workspace_id, user, db)

    result = await db.execute(
        text("SELECT storage_path FROM documents WHERE id = :id AND workspace_id = :wid"),
        {"id": document_id, "wid": workspace_id},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")

    storage.delete(row["storage_path"])

    await db.execute(
        text("DELETE FROM documents WHERE id = :id"),
        {"id": document_id},
    )
    await db.commit()