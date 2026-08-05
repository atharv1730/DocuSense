from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional, List

class DocumentOut(BaseModel):
    id: UUID
    workspace_id: UUID
    filename: str
    page_count: Optional[int]
    size_bytes: Optional[int]
    status: str
    error_message: Optional[str]
    chunking_strategies: List[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RechunkRequest(BaseModel):
    strategy: str