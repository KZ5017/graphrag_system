from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class VaultCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    root_path: str = Field(min_length=1)
    path_case_mode: Literal["sensitive", "insensitive"] = "sensitive"
    include_globs: list[str] = Field(default_factory=lambda: ["**/*.md"], min_length=1)
    exclude_globs: list[str] = Field(default_factory=lambda: [".obsidian/**", ".trash/**"])
    obsidian_uri_template: str | None = None


class VaultResponse(BaseModel):
    id: UUID
    name: str
    root_path: str
    path_case_mode: Literal["sensitive", "insensitive"]
    include_globs: list[str]
    exclude_globs: list[str]


class ScanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scan_type: Literal["incremental", "full_rehash", "measure"] = "incremental"


class ScanAcceptedResponse(BaseModel):
    job_id: UUID
    job_type: Literal["scan_vault"] = "scan_vault"
    status: Literal["queued"] = "queued"


class JobResponse(BaseModel):
    id: UUID
    job_type: str
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    progress_current: int
    progress_total: int | None
    checkpoint: dict[str, object]
    attempt_count: int
    max_attempts: int
    error_code: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
