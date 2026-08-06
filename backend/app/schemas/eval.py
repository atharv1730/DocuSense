from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class ChunkRatingIn(BaseModel):
    chunk_id: str
    rating: int  # 0 = not relevant, 1 = relevant


class SubmitRatingsRequest(BaseModel):
    retrieval_log_id: str
    ratings: List[ChunkRatingIn]


class ConfigMetrics(BaseModel):
    chunking_strategy: str
    rerank_enabled: bool
    precision_at_1: Optional[float]
    precision_at_3: Optional[float]
    precision_at_5: Optional[float]
    mrr: Optional[float]
    query_count: int
    rated_query_count: int
    coverage: float


class MetricsResponse(BaseModel):
    configs: List[ConfigMetrics]
    overall_coverage: float


class ChunkRatingOut(BaseModel):
    chunk_id: str
    rating: int


class RetrievalLogOut(BaseModel):
    id: str
    conversation_id: Optional[str]
    query: str
    chunking_strategy: Optional[str]
    rerank_enabled: bool
    is_replay: bool
    stage1_chunk_ids: Optional[List[str]]
    stage2_chunk_ids: Optional[List[str]]
    final_chunk_ids: Optional[List[str]]
    answer: Optional[str]
    abstained: Optional[bool]
    created_at: datetime
    ratings: List[ChunkRatingOut]


class ChunkPreviewOut(BaseModel):
    id: str
    filename: str
    page_number: Optional[int]
    text: str


class RetrievalLogsResponse(BaseModel):
    logs: List[RetrievalLogOut]
    total: int
    page: int
    page_size: int
    chunk_previews: dict[str, ChunkPreviewOut]


class ReplayRequest(BaseModel):
    log_ids: List[str]
    chunking_strategy: str
    rerank_enabled: bool


class ReplayResponse(BaseModel):
    log_ids: List[str]
