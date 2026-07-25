from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from graphrag_service.adapters.postgres.operator_store import (
    OperatorDocument,
    OperatorJob,
    OperatorPendingDocument,
    OperatorPendingRefresh,
    OperatorVaultState,
)
from graphrag_service.api.app import create_app
from graphrag_service.application.readiness import ReadinessService
from graphrag_service.domain.vault import ScanChange, ScanChangeKind, ScanResult


class FakeOperatorStore:
    def __init__(self, vault_id):
        self.vault_id = vault_id

    async def vault_states(self):
        return [
            OperatorVaultState(
                id=self.vault_id,
                name="test-vault",
                document_count=2,
                chunk_count=5,
                entity_count=3,
                relationship_count=2,
                claim_count=1,
                latest_scan_status="succeeded",
                latest_scan_finished_at=datetime.now(UTC),
                latest_graph_status="succeeded",
                latest_graph_finished_at=datetime.now(UTC),
                qdrant_pending=0,
                qdrant_failed=0,
            )
        ]

    async def recent_jobs(self):
        return [
            OperatorJob(
                id=uuid4(),
                job_type="project_chunks",
                status="succeeded",
                checkpoint={"projected_upserts": 2},
                error_code=None,
                error_message=None,
                created_at=datetime.now(UTC),
                started_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),
            )
        ]

    async def pending_refresh(self, vault_id):
        assert vault_id == self.vault_id
        return OperatorPendingRefresh(
            scan_id=uuid4(),
            scan_finished_at=datetime.now(UTC),
            graph_refresh_required=True,
            documents=(
                OperatorPendingDocument(
                    id=uuid4(),
                    relative_path="changed.md",
                    extraction_run_id=None,
                ),
            ),
        )

    async def documents(self, vault_id):
        assert vault_id == self.vault_id
        return [
            OperatorDocument(
                id=uuid4(),
                relative_path="changed.md",
                lifecycle_status="active",
                processing_status="ready",
            )
        ]


class FakeIngestStore:
    async def get_vault(self, _):
        return object()


class FakeOperatorPreview:
    async def preview(self, vault_id):
        return ScanResult(
            files=(),
            changes=(
                ScanChange(
                    kind=ScanChangeKind.MODIFIED,
                    old_relative_path="changed.md",
                    new_relative_path="changed.md",
                    content_sha256="a" * 64,
                    document_id=uuid4(),
                ),
            ),
            discovered_count=2,
            hashed_count=1,
            new_count=0,
            modified_count=1,
            renamed_count=0,
            deleted_count=0,
            unchanged_count=1,
            failed_count=0,
            markdown_bytes=42,
            warnings=(),
        )


def test_operator_page_is_local_shell_and_api_is_token_protected(
    settings_factory,
) -> None:
    settings = settings_factory()
    vault_id = uuid4()
    app = create_app(
        settings,
        readiness_service=ReadinessService([], timeout_seconds=0.1),
    )
    headers = {"Authorization": f"Bearer {settings.service_token.get_secret_value()}"}

    with TestClient(app) as client:
        app.state.operator_store = FakeOperatorStore(vault_id)
        app.state.operator_preview = FakeOperatorPreview()
        app.state.ingest_store = FakeIngestStore()

        page = client.get("/operator")
        unauthorized = client.get("/v1/operator/overview")
        overview = client.get("/v1/operator/overview", headers=headers)
        pending = client.get(
            f"/v1/operator/vaults/{vault_id}/pending-refresh",
            headers=headers,
        )
        preview = client.get(
            f"/v1/operator/vaults/{vault_id}/preview",
            headers=headers,
        )

    assert page.status_code == 200
    assert "GraphRAG kezelő" in page.text
    assert "Gráfépítésre váró kivonatolások" in page.text
    assert "Legutóbbi tartós jobok" in page.text
    assert settings.service_token.get_secret_value() not in page.text
    assert unauthorized.status_code == 401
    assert overview.status_code == 200
    assert overview.json()["vaults"][0]["entity_count"] == 3
    assert pending.status_code == 200
    assert pending.json()["graph_refresh_required"] is True
    assert pending.json()["documents"][0]["relative_path"] == "changed.md"
    assert preview.status_code == 200
    assert preview.json()["needs_refresh"] is True
    assert preview.json()["changes"][0]["kind"] == "modified"
