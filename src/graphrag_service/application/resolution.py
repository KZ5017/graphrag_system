from __future__ import annotations

from uuid import UUID

from graphrag_service.adapters.postgres.resolution_store import ResolutionStore
from graphrag_service.domain.resolution import ResolutionOutcome, extract_strong_identifiers


class EntityResolutionService:
    def __init__(self, store: ResolutionStore) -> None:
        self._store = store

    async def resolve_run(self, run_id: UUID) -> ResolutionOutcome:
        candidates = await self._store.load_unresolved_candidates(run_id)
        created = merged = deferred = reviews = 0
        for candidate in candidates:
            identifiers = extract_strong_identifiers(
                candidate.name,
                candidate.evidence_quote,
            )
            result = await self._store.resolve_candidate(candidate, identifiers)
            created += int(result.decision == "create")
            merged += int(result.decision == "merge")
            deferred += int(result.decision == "defer")
            reviews += result.review_candidates
        relationships, claims = await self._store.materialize_assertions(run_id)
        return ResolutionOutcome(
            run_id=run_id,
            created_entities=created,
            merged_mentions=merged,
            deferred_candidates=deferred,
            review_candidates=reviews,
            relationship_assertions=relationships,
            claims=claims,
        )
