from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ResolutionJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vault_id: UUID
    extraction_run_ids: list[UUID] = Field(min_length=1, max_length=20)


class ResolutionJobAcceptedResponse(BaseModel):
    job_id: UUID
    job_type: Literal["resolve_and_project_graph"] = "resolve_and_project_graph"
    status: Literal["queued"] = "queued"
