from __future__ import annotations

from fastapi import FastAPI

from graphrag_service.adapters.postgres.ingest_store import PostgresIngestStore
from graphrag_service.adapters.postgres.operator_store import PostgresOperatorStore
from graphrag_service.adapters.vault_fs.factory import build_vault_reader
from graphrag_service.application.ingest import VaultIngestService
from graphrag_service.application.operator import OperatorPreviewService
from graphrag_service.config import Settings


def configure_ingest(app: FastAPI, settings: Settings) -> None:
    store = PostgresIngestStore(app.state.session_factory)
    app.state.ingest_store = store
    app.state.ingest_service = VaultIngestService(
        store=store,
        reader_factory=lambda vault: build_vault_reader(settings, vault),
    )
    app.state.operator_store = PostgresOperatorStore(app.state.session_factory)
    app.state.operator_preview = OperatorPreviewService(
        store=store,
        reader_factory=lambda vault: build_vault_reader(settings, vault),
    )
