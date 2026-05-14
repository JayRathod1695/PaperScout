from typing import Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class AnalyzeRequest(BaseModel):
    text: Optional[str] = Field(None)
    source_url: Optional[str] = None

    @field_validator("source_url")
    @classmethod
    def validate_arxiv_url(cls, v: Optional[str]) -> Optional[str]:
        if v and not (
            v.startswith("https://arxiv.org/") or v.startswith("http://arxiv.org/")
        ):
            raise ValueError("Only arxiv.org URLs are supported")
        return v

    @model_validator(mode="after")
    def at_least_one_input(self) -> "AnalyzeRequest":
        if not self.text and not self.source_url:
            raise ValueError("Either 'text' or 'source_url' must be provided")
        return self


class SearchRelatedRequest(BaseModel):
    analysis_id: str
    user_goal: str = Field(..., min_length=20, max_length=1000)
    email: str = Field(..., pattern=r"^[\w\.\-]+@[\w\.\-]+\.\w+$")
