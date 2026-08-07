from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID


class CompareRequest(BaseModel):
    document_id_a: str
    document_id_b: str


class DocumentRef(BaseModel):
    id: UUID
    filename: str


class AlignedSection(BaseModel):
    section_title: str
    identical: bool
    differences: List[str]
    changed_clauses: List[str]
    match_type: str
    similarity: float
    page_a: Optional[int]
    page_b: Optional[int]


class SectionSummary(BaseModel):
    section_title: str
    page_number: Optional[int]


class ComparisonResult(BaseModel):
    document_a: DocumentRef
    document_b: DocumentRef
    aligned_sections: List[AlignedSection]
    only_in_a: List[SectionSummary]
    only_in_b: List[SectionSummary]
    identical_count: int
    diff_count: int
