from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import Any
from uuid import UUID

from graphrag_service.domain.retrieval import (
    RetrievalChunk,
    RetrievalEntity,
    RetrievalPath,
    RetrievalRelationship,
    RetrievalWarning,
)


@dataclass(frozen=True, slots=True)
class GraphRetrievalExpansion:
    entities: tuple[RetrievalEntity, ...]
    relationships: tuple[RetrievalRelationship, ...]
    paths: tuple[RetrievalPath, ...]
    source_chunks: tuple[RetrievalChunk, ...]
    warnings: tuple[RetrievalWarning, ...]
    truncated: bool


class GraphRetrievalEnricher:
    """Expand bounded entity seeds and accept only current PostgreSQL evidence."""

    def __init__(
        self,
        *,
        store: Any,
        graph: Any,
        entity_limit: int,
        max_hops: int,
        max_paths: int,
    ) -> None:
        self._store = store
        self._graph = graph
        self._entity_limit = entity_limit
        self._max_hops = max_hops
        self._max_paths = max_paths

    async def expand(
        self,
        query: str,
        *,
        seed_chunks: list[RetrievalChunk],
        vault_id: UUID | None,
    ) -> GraphRetrievalExpansion:
        seeds = await self._store.entity_seeds(
            query,
            chunk_ids=[item.chunk_id for item in seed_chunks],
            limit=self._entity_limit,
            vault_id=vault_id,
        )
        seeds = [item for item in seeds if "entity" in item.seed_channels and item.score >= 1.0]
        if not seeds:
            return GraphRetrievalExpansion((), (), (), (), (), False)
        seed_source_ids = _ordered_unique(
            chunk_id for seed in seeds for chunk_id in seed.source_chunk_ids
        )
        seed_chunks = await self._store.hydrate_current(seed_source_ids)

        try:
            raw_paths = await self._graph.expand_from_entities(
                entity_ids=tuple(item.entity_id for item in seeds),
                max_hops=self._max_hops,
                max_paths=self._max_paths + 1,
                include_unreviewed=True,
            )
        except RuntimeError:
            return GraphRetrievalExpansion(
                entities=tuple(seeds),
                relationships=(),
                paths=(),
                source_chunks=tuple(seed_chunks.values()),
                warnings=(
                    RetrievalWarning(
                        code="graph_unavailable",
                        message=(
                            "Graph expansion is unavailable; chunk and entity seeds were retained."
                        ),
                    ),
                ),
                truncated=False,
            )

        truncated = len(raw_paths) > self._max_paths
        raw_paths = raw_paths[: self._max_paths]
        assertion_ids = _ordered_unique(
            assertion_id for row in raw_paths for assertion_id in _assertion_ids(row)
        )
        hydrated = await self._store.hydrate_assertions(assertion_ids)

        relationships: dict[UUID, RetrievalRelationship] = {}
        chunks: dict[UUID, RetrievalChunk] = dict(seed_chunks)
        paths: list[RetrievalPath] = []
        raw_entities: dict[UUID, dict[str, Any]] = {}
        entity_sources: dict[UUID, set[UUID]] = {}
        stale_paths = 0

        for row in raw_paths:
            path_assertions = _assertion_ids(row)
            path_entities = _entity_ids(row)
            if (
                not path_assertions
                or len(path_assertions) != int(row.get("hops", 0))
                or any(assertion_id not in hydrated for assertion_id in path_assertions)
            ):
                stale_paths += 1
                continue
            source_chunk_ids: list[UUID] = []
            for assertion_id in path_assertions:
                relationship, chunk = hydrated[assertion_id]
                relationships[assertion_id] = relationship
                chunks[chunk.chunk_id] = chunk
                if chunk.chunk_id not in source_chunk_ids:
                    source_chunk_ids.append(chunk.chunk_id)
            for node in row.get("entities", []):
                try:
                    entity_id = UUID(str(node["id"]))
                except (KeyError, TypeError, ValueError):
                    continue
                raw_entities[entity_id] = dict(node)
                entity_sources.setdefault(entity_id, set()).update(source_chunk_ids)
            paths.append(
                RetrievalPath(
                    entity_ids=path_entities,
                    assertion_ids=path_assertions,
                    source_chunk_ids=tuple(source_chunk_ids),
                    hops=int(row["hops"]),
                )
            )

        warnings: list[RetrievalWarning] = []
        if stale_paths:
            warnings.append(
                RetrievalWarning(
                    code="stale_graph_filtered",
                    message=f"{stale_paths} graph paths without current evidence were discarded.",
                )
            )

        entities = {item.entity_id: item for item in seeds}
        for entity_id, node in raw_entities.items():
            if entity_id in entities:
                entities[entity_id] = replace(
                    entities[entity_id],
                    source_chunk_ids=tuple(
                        sorted(
                            set(entities[entity_id].source_chunk_ids)
                            | entity_sources.get(entity_id, set()),
                            key=str,
                        )
                    ),
                )
                continue
            try:
                expanded = RetrievalEntity(
                    entity_id=entity_id,
                    vault_id=UUID(str(node["vault_id"])),
                    canonical_name=str(node["canonical_name"]),
                    entity_type=str(node["entity_type"]),
                    entity_subtype=(
                        str(node["entity_subtype"]) if node.get("entity_subtype") else None
                    ),
                    scope=str(node["scope"]),
                    score=0.0,
                    seed_channels=("graph",),
                    source_chunk_ids=tuple(sorted(entity_sources.get(entity_id, set()), key=str)),
                )
            except (KeyError, TypeError, ValueError):
                continue
            entities[entity_id] = expanded

        return GraphRetrievalExpansion(
            entities=tuple(
                sorted(
                    entities.values(),
                    key=lambda item: (
                        -item.score,
                        item.canonical_name.casefold(),
                        str(item.entity_id),
                    ),
                )
            ),
            relationships=tuple(
                relationships[item_id] for item_id in sorted(relationships, key=str)
            ),
            paths=tuple(paths),
            source_chunks=tuple(chunks[item_id] for item_id in chunks),
            warnings=tuple(warnings),
            truncated=truncated,
        )


def _assertion_ids(row: dict[str, Any]) -> tuple[UUID, ...]:
    values: list[UUID] = []
    for assertion in row.get("assertions", []):
        try:
            value = UUID(str(assertion["assertion_id"]))
        except (KeyError, TypeError, ValueError):
            continue
        values.append(value)
    return tuple(values)


def _entity_ids(row: dict[str, Any]) -> tuple[UUID, ...]:
    values: list[UUID] = []
    for entity in row.get("entities", []):
        try:
            value = UUID(str(entity["id"]))
        except (KeyError, TypeError, ValueError):
            continue
        values.append(value)
    return tuple(values)


def _ordered_unique(values: Iterable[UUID]) -> list[UUID]:
    return list(dict.fromkeys(values))
