from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class GraphSnapshot:
    vault_id: UUID
    nodes: dict[str, tuple[dict[str, Any], ...]]
    relationships: dict[str, tuple[dict[str, Any], ...]]

    @property
    def object_count(self) -> int:
        return sum(map(len, self.nodes.values())) + sum(map(len, self.relationships.values()))

    @property
    def sha256(self) -> str:
        canonical = json.dumps(
            {"nodes": self.nodes, "relationships": self.relationships},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class GraphProjectionOutcome:
    vault_id: UUID
    snapshot_sha256: str
    generation: int
    object_count: int
    projected: bool


@dataclass(frozen=True, slots=True)
class EntityEvidence:
    evidence_id: UUID
    chunk_id: UUID
    document_id: UUID
    relative_path: str
    quote: str
    char_start: int
    char_end: int


@dataclass(frozen=True, slots=True)
class EntityDetail:
    id: UUID
    vault_id: UUID
    canonical_name: str
    entity_type: str
    entity_subtype: str | None
    scope: str
    status: str
    aliases: tuple[str, ...]
    identifiers: tuple[dict[str, str], ...]
    evidence: tuple[EntityEvidence, ...]
