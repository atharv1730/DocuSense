"""
Authenticated CRUD routes for workspaces under /workspaces.

Lists, creates, renames, and deletes workspaces for the current user,
using get_current_user and the workspace request/response schemas.
"""

"""
Notice every query filters by both workspace_id AND user_id. 
This is what enforces ownership — a user cannot read, rename, or delete another user's workspace 
even if they know the ID.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.db import get_db
from app.auth import get_current_user
from app.schemas.workspace import WorkspaceCreate, WorkspaceUpdate, WorkspaceOut
from typing import List
import uuid

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.get("", response_model=List[WorkspaceOut])
async def list_workspaces(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        text("SELECT id, name, created_at, updated_at FROM workspaces WHERE user_id = :uid ORDER BY created_at DESC"),
        {"uid": str(user["id"])},
    )
    return [dict(r) for r in result.mappings().all()]


@router.post("", response_model=WorkspaceOut, status_code=201)
async def create_workspace(
    body: WorkspaceCreate,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    wid = str(uuid.uuid4())
    await db.execute(
        text("INSERT INTO workspaces (id, user_id, name) VALUES (:id, :uid, :name)"),
        {"id": wid, "uid": str(user["id"]), "name": body.name},
    )
    await db.commit()
    result = await db.execute(
        text("SELECT id, name, created_at, updated_at FROM workspaces WHERE id = :id"),
        {"id": wid},
    )
    return dict(result.mappings().one())


@router.patch("/{workspace_id}", response_model=WorkspaceOut)
async def rename_workspace(
    workspace_id: str,
    body: WorkspaceUpdate,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        text("SELECT id FROM workspaces WHERE id = :id AND user_id = :uid"),
        {"id": workspace_id, "uid": str(user["id"])},
    )
    if not result.mappings().first():
        raise HTTPException(status_code=404, detail="Workspace not found")

    await db.execute(
        text("UPDATE workspaces SET name = :name, updated_at = now() WHERE id = :id"),
        {"name": body.name, "id": workspace_id},
    )
    await db.commit()
    result = await db.execute(
        text("SELECT id, name, created_at, updated_at FROM workspaces WHERE id = :id"),
        {"id": workspace_id},
    )
    return dict(result.mappings().one())


@router.delete("/{workspace_id}", status_code=204)
async def delete_workspace(
    workspace_id: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        text("SELECT id FROM workspaces WHERE id = :id AND user_id = :uid"),
        {"id": workspace_id, "uid": str(user["id"])},
    )
    if not result.mappings().first():
        raise HTTPException(status_code=404, detail="Workspace not found")

    await db.execute(
        text("DELETE FROM workspaces WHERE id = :id"),
        {"id": workspace_id},
    )
    await db.commit()