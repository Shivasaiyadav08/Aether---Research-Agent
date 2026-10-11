from typing import TypedDict

from pydantic import BaseModel, Field


class RelevanceGrade(BaseModel):
    score: float = Field(
        ge=0, le=1, description="How directly this chunk helps answer the question, from 0 to 1"
    )
    reason: str = Field(description="Brief explanation of relevance, based only on the chunk")


class EvidenceAssessment(BaseModel):
    sufficient: bool = Field(
        description="True only if the evidence supports every important part of the question"
    )
    reason: str
    missing_information: str


class RewrittenQuery(BaseModel):
    query: str = Field(
        min_length=1, max_length=500, description="Standalone web search query preserving user intent"
    )


class AnswerValidation(BaseModel):
    grounded: bool = Field(description="Every factual claim is supported by its cited evidence")
    reason: str


class GraphState(TypedDict, total=False):
    question: str
    workspace_id: str
    settings: dict
    history: list[dict]
    retrieved: list[dict]
    sources: list[dict]
    assessment: dict
    rewritten_query: str
    answer: str
    attempts: int
    valid: bool
    feedback: str
    warnings: list[str]
    model_plan: dict
