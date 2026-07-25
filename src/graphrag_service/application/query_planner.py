from __future__ import annotations

import re
from dataclasses import dataclass

from graphrag_service.domain.retrieval import RetrievalQueryType, RetrievalStrategy

_TOKEN_PATTERN = re.compile(r"[0-9A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű_.:/-]+")
_GRAPH_CUES = (
    "kapcsol",
    "kommunik",
    "használ",
    "függ",
    "között",
    "útvonal",
    "keresztül",
    "elér",
    "tartoz",
    "connect",
    "communicat",
    "depend",
    "between",
    "path",
    "through",
    "uses",
)


@dataclass(frozen=True, slots=True)
class DeterministicQueryPlan:
    query_type: RetrievalQueryType
    channels: tuple[str, ...]
    graph_expansion: bool
    claim_retrieval: bool
    reason_code: str


class DeterministicQueryPlanner:
    """Small-model-safe query routing with no provider call or learned threshold."""

    def plan(
        self,
        query: str,
        *,
        strategy: RetrievalStrategy,
    ) -> DeterministicQueryPlan:
        if strategy == "keyword":
            return DeterministicQueryPlan(
                query_type="keyword",
                channels=("keyword",),
                graph_expansion=False,
                claim_retrieval=False,
                reason_code="explicit_keyword_strategy",
            )
        if strategy == "semantic":
            return DeterministicQueryPlan(
                query_type="semantic",
                channels=("semantic",),
                graph_expansion=False,
                claim_retrieval=False,
                reason_code="explicit_semantic_strategy",
            )

        folded = query.casefold()
        if any(cue in folded for cue in _GRAPH_CUES):
            query_type: RetrievalQueryType = "graph"
            reason_code = "relationship_or_path_cue"
        elif _looks_like_entity_lookup(query):
            query_type = "entity"
            reason_code = "short_identifier_or_acronym"
        else:
            query_type = "hybrid"
            reason_code = "general_hybrid"
        return DeterministicQueryPlan(
            query_type=query_type,
            channels=("keyword", "semantic", "entity", "graph", "claim"),
            graph_expansion=True,
            claim_retrieval=True,
            reason_code=reason_code,
        )


def _looks_like_entity_lookup(query: str) -> bool:
    tokens = _TOKEN_PATTERN.findall(query)
    if not tokens or len(tokens) > 4:
        return False
    return any(
        (token.isupper() and any(character.isalpha() for character in token))
        or any(character.isdigit() for character in token)
        or any(character in "_.:/-" for character in token)
        for token in tokens
    )
