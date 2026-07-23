from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ExtractionJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vault_id: UUID
    document_ids: list[UUID] = Field(min_length=1, max_length=10)
    max_chunks: int = Field(default=6, ge=1, le=100)


class ExtractionJobAcceptedResponse(BaseModel):
    job_id: UUID
    job_type: Literal["extract_knowledge_pilot"] = "extract_knowledge_pilot"
    status: Literal["queued"] = "queued"
