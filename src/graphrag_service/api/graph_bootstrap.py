from __future__ import annotations

from fastapi import FastAPI

from graphrag_service.adapters.neo4j.client import Neo4jGraphAdapter
from graphrag_service.adapters.postgres.graph_store import GraphStore
from graphrag_service.application.graph_projection import GraphProjectionService
from graphrag_service.config import Settings


def configure_graph(app: FastAPI, settings: Settings) -> None:
    store = GraphStore(app.state.session_factory)
    graph = Neo4jGraphAdapter(
        uri=settings.neo4j_uri,
        username=settings.neo4j_username,
        password=settings.neo4j_password.get_secret_value(),
        database=settings.neo4j_database,
    )
    app.state.graph_store = store
    app.state.graph_adapter = graph
    app.state.graph_projection_service = GraphProjectionService(
        store=store,
        graph=graph,
        max_objects=settings.graph_projection_max_objects,
    )
