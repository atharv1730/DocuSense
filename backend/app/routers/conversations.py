import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.db import get_db
from app.auth import get_current_user
from app.routers.documents import verify_workspace
from app.schemas.conversation import ConversationOut, CreateConversationRequest, MessageOut

router = APIRouter(prefix="/workspaces/{workspace_id}/conversations", tags=["conversations"])


async def _verify_conversation(workspace_id: str, conversation_id: str, db: AsyncSession):
    result = await db.execute(
        text("SELECT id FROM conversations WHERE id = :id AND workspace_id = :wid"),
        {"id": conversation_id, "wid": workspace_id},
    )
    if not result.mappings().first():
        raise HTTPException(status_code=404, detail="Conversation not found")


@router.get("", response_model=List[ConversationOut])
async def list_conversations(
    workspace_id: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await verify_workspace(workspace_id, user, db)
    result = await db.execute(
        text("SELECT * FROM conversations WHERE workspace_id = :wid ORDER BY updated_at DESC"),
        {"wid": workspace_id},
    )
    return [dict(r) for r in result.mappings().all()]


@router.post("", response_model=ConversationOut, status_code=201)
async def create_conversation(
    workspace_id: str,
    body: CreateConversationRequest,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await verify_workspace(workspace_id, user, db)
    conv_id = str(uuid.uuid4())
    await db.execute(
        text("INSERT INTO conversations (id, workspace_id, title) VALUES (:id, :wid, :title)"),
        {"id": conv_id, "wid": workspace_id, "title": body.title},
    )
    await db.commit()
    result = await db.execute(text("SELECT * FROM conversations WHERE id = :id"), {"id": conv_id})
    return dict(result.mappings().one())


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(
    workspace_id: str,
    conversation_id: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await verify_workspace(workspace_id, user, db)
    await _verify_conversation(workspace_id, conversation_id, db)

    # messages cascade via ON DELETE CASCADE on messages.conversation_id
    await db.execute(text("DELETE FROM conversations WHERE id = :id"), {"id": conversation_id})
    await db.commit()
    return Response(status_code=204)


@router.get("/{conversation_id}/messages", response_model=List[MessageOut])
async def list_messages(
    workspace_id: str,
    conversation_id: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await verify_workspace(workspace_id, user, db)
    await _verify_conversation(workspace_id, conversation_id, db)

    result = await db.execute(
        text("""
            SELECT id, conversation_id, role, content, citations, retrieval_log_id, created_at
            FROM messages
            WHERE conversation_id = :cid
            ORDER BY created_at ASC
        """),
        {"cid": conversation_id},
    )
    return [dict(r) for r in result.mappings().all()]
