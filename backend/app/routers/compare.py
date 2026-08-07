from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.db import get_db
from app.auth import get_current_user
from app.routers.documents import verify_workspace
from app.schemas.compare import CompareRequest, ComparisonResult
from app.pipeline.compare import compare_documents, NoSemanticChunksError

router = APIRouter(prefix="/workspaces/{workspace_id}/compare", tags=["compare"])

SEMANTIC_CHUNKING_REQUIRED_MESSAGE = "Run semantic chunking on both documents first"


@router.post("", response_model=ComparisonResult)
async def compare(
    workspace_id: str,
    body: CompareRequest,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await verify_workspace(workspace_id, user, db)

    if body.document_id_a == body.document_id_b:
        # Comparing a document with itself is explicitly supported (it
        # should come back all-identical), just skip the redundant lookup.
        pass

    result = await db.execute(
        text("""
            SELECT id, status, chunking_strategies
            FROM documents
            WHERE workspace_id = :wid AND id = ANY(:ids)
        """),
        {"wid": workspace_id, "ids": [body.document_id_a, body.document_id_b]},
    )
    rows = {str(r["id"]): r for r in result.mappings().all()}

    for doc_id in (body.document_id_a, body.document_id_b):
        if doc_id not in rows:
            raise HTTPException(status_code=404, detail="Document not found in this workspace")
        if rows[doc_id]["status"] != "ready":
            raise HTTPException(
                status_code=400,
                detail="Both documents must finish processing before comparing",
            )

    missing_semantic = any(
        "semantic" not in (rows[doc_id]["chunking_strategies"] or [])
        for doc_id in (body.document_id_a, body.document_id_b)
    )
    if missing_semantic:
        raise HTTPException(status_code=422, detail=SEMANTIC_CHUNKING_REQUIRED_MESSAGE)

    try:
        return await compare_documents(body.document_id_a, body.document_id_b, db)
    except NoSemanticChunksError:
        # Defensive: the chunking_strategies check above should already
        # catch this, but the chunks table is the source of truth.
        raise HTTPException(status_code=422, detail=SEMANTIC_CHUNKING_REQUIRED_MESSAGE)
