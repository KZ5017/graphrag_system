from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from graphrag_service.api.app import create_app
from graphrag_service.application.readiness import ReadinessService
from graphrag_service.domain.retrieval import RetrievalChunk, RetrievalResult


class FakeRetrievalService:
    async def retrieve(self, *_: object, **__: object) -> RetrievalResult:
        chunk_id = uuid4()
        chunk = RetrievalChunk(
            chunk_id=chunk_id,
            vault_id=uuid4(),
            document_id=uuid4(),
            document_version_id=uuid4(),
            section_id=uuid4(),
            relative_path="network.md",
            heading_path=("Access",),
            text="The CMTS provisions cable modems.",
            char_start=10,
            char_end=43,
            content_sha256="a" * 64,
            source_uri="vault://test/network.md#chars=10,43",
            obsidian_uri=None,
            keyword_score=0.8,
            semantic_score=0.9,
            fusion_score=0.03,
        )
        return RetrievalResult(
            query_id=uuid4(),
            strategy="hybrid",
            chunks=(chunk,),
            context_chunks=(),
            warnings=(),
            truncated=False,
        )


def test_retrieve_api_returns_structured_provenance(settings_factory) -> None:
    settings = settings_factory()
    app = create_app(
        settings,
        readiness_service=ReadinessService([], timeout_seconds=0.1),
    )
    headers = {"Authorization": f"Bearer {settings.service_token.get_secret_value()}"}
    with TestClient(app) as client:
        app.state.retrieval_service = FakeRetrievalService()
        response = client.post(
            "/v1/retrieve",
            headers=headers,
            json={"query": "CMTS modem", "strategy": "hybrid", "limit": 5},
        )
        disabled_index = client.post("/v1/index-jobs", headers=headers, json={})

    assert response.status_code == 200
    body = response.json()
    assert body["strategy"] == "hybrid"
    assert body["chunks"][0]["source"]["source_uri"].startswith("vault://")
    assert body["chunks"][0]["scores"] == {
        "keyword": 0.8,
        "semantic": 0.9,
        "fusion": 0.03,
    }
    assert body["confidence"] is None
    assert disabled_index.status_code == 503
