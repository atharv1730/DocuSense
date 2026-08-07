from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional, List, Any


class ConversationOut(BaseModel):
    id: UUID
    workspace_id: UUID
    title: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CreateConversationRequest(BaseModel):
    title: Optional[str] = None


class MessageOut(BaseModel):
    id: UUID
    conversation_id: UUID
    role: str
    content: str
    citations: Optional[List[Any]] = None
    retrieval_log_id: Optional[UUID] = None
    created_at: datetime

    class Config:
        from_attributes = True
