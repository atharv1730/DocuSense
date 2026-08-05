import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.db import get_db, AsyncSessionLocal
from app.auth import get_current_user
from app.storage import storage
from app.pipeline.process import process_document, run_semantic_chunking
from app.schemas.document import DocumentOut, RechunkRequest
from app.config import settings
from typing import List

SUPPORTED_STRATEGIES = {"semantic"}


async def _run_semantic_chunking_bg(document_id: str) -> None:
    """Opens a dedicated session for the background task, since the
    request-scoped `db` dependency is torn down once the endpoint returns.
    """
    async with AsyncSessionLocal() as session:
        await run_semantic_chunking(document_id, session)

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


@router.post("/{document_id}/rechunk", status_code=202)
async def rechunk_document(
    workspace_id: str,
    document_id: str,
    body: RechunkRequest,
    background_tasks: BackgroundTasks,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await verify_workspace(workspace_id, user, db)

    if body.strategy not in SUPPORTED_STRATEGIES:
        raise HTTPException(status_code=400, detail=f"Unsupported strategy: {body.strategy}")

    result = await db.execute(
        text("SELECT status, chunking_strategies FROM documents WHERE id = :id AND workspace_id = :wid"),
        {"id": document_id, "wid": workspace_id},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")

    if row["status"] != "ready":
        raise HTTPException(status_code=400, detail="Document must be in 'ready' status to rechunk")

    if body.strategy in (row["chunking_strategies"] or []):
        raise HTTPException(status_code=400, detail=f"'{body.strategy}' chunking has already been run for this document")

    background_tasks.add_task(_run_semantic_chunking_bg, document_id)

    return {"status": "accepted"}


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