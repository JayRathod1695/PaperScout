from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel


class Triage(BaseModel):
    claim: str
    method: str
    catch: str
    verdict: str
    verdict_reason: str
    steal: str


class AnalyzeResponse(BaseModel):
    analysis_id: str
    title: Optional[str]
    triage: Triage


class AnalysisSummary(BaseModel):
    id: str
    title: Optional[str]
    source_url: Optional[str]
    triage: dict
    created_at: datetime
    has_search_job: bool


class AnalysesListResponse(BaseModel):
    analyses: List[AnalysisSummary]
    total: int


class SearchRelatedResponse(BaseModel):
    job_id: str
    status: str


class RelatedPaper(BaseModel):
    id: str
    title: str
    authors: List[str]
    url: Optional[str]
    year: Optional[int]
    triage: Triage
    relevance_score: float
    relevance_reason: Optional[str]


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    error_message: Optional[str]
    papers_found: int
    papers: List[RelatedPaper]
    created_at: datetime
    completed_at: Optional[datetime]
