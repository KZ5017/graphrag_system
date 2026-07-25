from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class OperatorChangeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str
    old_relative_path: str | None
    new_relative_path: str | None
    document_id: UUID | None
    detail: dict[str, Any]


class OperatorPreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vault_id: UUID
    discovered: int
    hashed: int
    created: int
    modified: int
    renamed: int
    deleted: int
    failed: int
    needs_refresh: bool
    changes: list[OperatorChangeResponse]
    warnings: list[dict[str, Any]]


class OperatorDocumentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    relative_path: str
    lifecycle_status: str
    processing_status: str | None


class OperatorPendingDocumentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    relative_path: str
    extraction_run_id: UUID | None


class OperatorPendingRefreshResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scan_id: UUID | None
    scan_finished_at: datetime | None
    graph_refresh_required: bool
    documents: list[OperatorPendingDocumentResponse]


class OperatorJobResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    job_type: str
    status: str
    checkpoint: dict[str, Any]
    error_code: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class OperatorVaultResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    name: str
    document_count: int
    chunk_count: int
    entity_count: int
    relationship_count: int
    claim_count: int
    latest_scan_status: str | None
    latest_scan_finished_at: datetime | None
    latest_graph_status: str | None
    latest_graph_finished_at: datetime | None
    qdrant_pending: int
    qdrant_failed: int


class OperatorJobAcceptedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: UUID
    job_type: Literal["rebuild_graph_projection"] = "rebuild_graph_projection"
    status: Literal["queued"] = "queued"


class OperatorOverviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    readiness: Literal["ready", "degraded", "not_ready"]
    components: dict[str, dict[str, Any]]
    vaults: list[OperatorVaultResponse]
    recent_jobs: list[OperatorJobResponse]
