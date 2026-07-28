"""
Pydantic models for workspace API request and response bodies.

WorkspaceCreate / WorkspaceUpdate validate the name on write;
WorkspaceOut shapes the id, name, and timestamps returned to clients.
"""

from pydantic import BaseModel
from uuid import UUID
from datetime import datetime

class WorkspaceCreate(BaseModel):
    name: str

class WorkspaceUpdate(BaseModel):
    name: str

class WorkspaceOut(BaseModel):
    id: UUID
    name: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True