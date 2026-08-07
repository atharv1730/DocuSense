from pydantic import BaseModel
from typing import Optional


class ChatRequest(BaseModel):
    query: str
    document_id: Optional[str] = None
    chunking_strategy: str = "fixed"
    rerank_enabled: bool = False
    conversation_id: Optional[str] = None


class CitationOut(BaseModel):
    index: int
    filename: str
    page_number: int
    text: str
