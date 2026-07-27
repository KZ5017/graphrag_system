from __future__ import annotations

from dataclasses import replace
from uuid import UUID, uuid4

from graphrag_service.adapters.postgres.projection_store import ModelProfile
from graphrag_service.application.graph_retrieval import (
    GraphRetrievalEnricher,
    GraphRetrievalExpansion,
)
from graphrag_service.application.phase5_retrieval import Phase5RetrievalService
from graphrag_service.application.query_planner import DeterministicQueryPlanner
from graphrag_service.domain.embedding import (
    EmbeddingBatch,
    EmbeddingModelInfo,
    ProviderCapabilities,
)
from graphrag_service.domain.retrieval import (
    RetrievalChunk,
    RetrievalClaim,
    RetrievalEntity,
    RetrievalPath,
    RetrievalRelationship,
)
from graphrag_service.ports.vector_index import VectorHit


def make_chunk(chunk_id: UUID, text: str = "CMTS provisions modems") -> RetrievalChunk:
    return RetrievalChunk(
        chunk_id=chunk_id,
        vault_id=uuid4(),
        document_id=uuid4(),
        document_version_id=uuid4(),
        section_id=uuid4(),
        relative_path="network.md",
        heading_path=("Access",),
        text=text,
        char_start=10,
        char_end=10 + len(text),
        content_sha256="a" * 64,
        source_uri=f"vault://test/network.md#chunk={chunk_id}",
        obsidian_uri=None,
    )


class FakeGraphStore:
    def __init__(
        self,
        *,
        entity: RetrievalEntity,
        chunks: dict[UUID, RetrievalChunk],
        assertions: dict[UUID, tuple[RetrievalRelationship, RetrievalChunk]],
    ) -> None:
        self.entity = entity
        self.chunks = chunks
        self.assertions = assertions

    async def entity_seeds(self, *_: object, **__: object) -> list[RetrievalEntity]:
        return [self.entity]

    async def hydrate_current(self, _: list[UUID]) -> dict[UUID, RetrievalChunk]:
        return self.chunks

    async def hydrate_assertions(
        self,
        _: list[UUID],
    ) -> dict[UUID, tuple[RetrievalRelationship, RetrievalChunk]]:
        return self.assertions


class FakeGraph:
    def __init__(self, paths: list[dict[str, object]]) -> None:
        self.paths = paths

    async def expand_from_entities(self, **_: object) -> list[dict[str, object]]:
        return self.paths


async def test_graph_expansion_filters_paths_without_current_postgres_evidence() -> None:
    vault_id = uuid4()
    seed_id, neighbor_id = uuid4(), uuid4()
    current_assertion_id, stale_assertion_id = uuid4(), uuid4()
    evidence_id = uuid4()
    source_chunk = replace(make_chunk(uuid4()), vault_id=vault_id)
    seed = RetrievalEntity(
        entity_id=seed_id,
        vault_id=vault_id,
        canonical_name="CMTS",
        entity_type="NETWORK_ELEMENT",
        entity_subtype="CMTS",
        scope="type",
        score=1.0,
        seed_channels=("entity",),
        source_chunk_ids=(source_chunk.chunk_id,),
    )
    relationship = RetrievalRelationship(
        assertion_id=current_assertion_id,
        subject_entity_id=seed_id,
        object_entity_id=neighbor_id,
        predicate="CONNECTS_TO",
        assertion_kind="explicit_source",
        review_status="unreviewed",
        evidence_id=evidence_id,
        source_chunk_id=source_chunk.chunk_id,
        quote="The CMTS connects to the access network.",
        char_start=10,
        char_end=50,
    )

    def path(assertion_id: UUID) -> dict[str, object]:
        return {
            "entities": [
                {
                    "id": str(seed_id),
                    "vault_id": str(vault_id),
                    "canonical_name": "CMTS",
                    "entity_type": "NETWORK_ELEMENT",
                    "entity_subtype": "CMTS",
                    "scope": "type",
                },
                {
                    "id": str(neighbor_id),
                    "vault_id": str(vault_id),
                    "canonical_name": "Access network",
                    "entity_type": "NETWORK_SEGMENT",
                    "entity_subtype": None,
                    "scope": "logical",
                },
            ],
            "assertions": [{"assertion_id": str(assertion_id)}],
            "hops": 1,
        }

    expansion = await GraphRetrievalEnricher(
        store=FakeGraphStore(
            entity=seed,
            chunks={source_chunk.chunk_id: source_chunk},
            assertions={current_assertion_id: (relationship, source_chunk)},
        ),
        graph=FakeGraph([path(current_assertion_id), path(stale_assertion_id)]),
        entity_limit=10,
        max_hops=2,
        max_paths=20,
    ).expand("CMTS kapcsolat", seed_chunks=[source_chunk], vault_id=vault_id)

    assert [item.assertion_id for item in expansion.relationships] == [current_assertion_id]
    assert len(expansion.paths) == 1
    assert expansion.paths[0].source_chunk_ids == (source_chunk.chunk_id,)
    assert expansion.warnings[0].code == "stale_graph_filtered"


class FakeRetrievalStore:
    def __init__(
        self,
        *,
        keyword: RetrievalChunk | list[RetrievalChunk],
        semantic: RetrievalChunk | list[RetrievalChunk],
        claims: list[tuple[RetrievalClaim, RetrievalChunk]] | None = None,
        document_context: list[RetrievalChunk] | None = None,
        document_context_truncated: bool = False,
    ) -> None:
        self.keyword = keyword if isinstance(keyword, list) else [keyword]
        self.semantic = semantic if isinstance(semantic, list) else [semantic]
        self.claims = claims or []
        self.document_context_items = document_context or []
        self.document_context_truncated = document_context_truncated
        self.document_context_seed_ids: list[UUID] = []
        self.document_context_calls: list[list[UUID]] = []
        self.audit: dict[str, object] | None = None

    async def keyword_search(self, *_: object, **__: object) -> list[RetrievalChunk]:
        return [replace(item, keyword_score=0.8) for item in self.keyword]

    async def hydrate_current(self, chunk_ids: list[UUID]) -> dict[UUID, RetrievalChunk]:
        return {item.chunk_id: item for item in self.semantic if item.chunk_id in chunk_ids}

    async def section_context(self, *_: object, **__: object) -> list[RetrievalChunk]:
        return []

    async def document_context(
        self, seed_ids: list[UUID], **__: object
    ) -> tuple[list[RetrievalChunk], bool]:
        self.document_context_seed_ids = seed_ids
        self.document_context_calls.append(seed_ids)
        if not seed_ids:
            return [], False
        return self.document_context_items, self.document_context_truncated

    async def claim_candidates(
        self, *_: object, **__: object
    ) -> list[tuple[RetrievalClaim, RetrievalChunk]]:
        return self.claims

    async def record_query(self, **values: object) -> UUID:
        self.audit = values
        return uuid4()


class FakeProjectionStore:
    def __init__(self) -> None:
        self.profile = ModelProfile(
            id=uuid4(),
            provider="fake",
            model_name="fake-3",
            vector_dimension=3,
            physical_collection="fake",
        )

    async def active_embedding_profile(self) -> ModelProfile:
        return self.profile


class FakeEmbeddingProvider:
    async def healthcheck(self) -> str:
        return "available"

    async def model_info(self) -> EmbeddingModelInfo:
        return EmbeddingModelInfo(
            provider="fake",
            model="fake-3",
            vector_dimension=3,
            capabilities=ProviderCapabilities(supports_batch=True),
        )

    async def probe_dimension(self) -> int:
        return 3

    async def embed(self, texts: list[str]) -> EmbeddingBatch:
        return EmbeddingBatch(
            vectors=tuple((1.0, 0.0, 0.0) for _ in texts),
            model="fake-3",
            dimension=3,
        )


class FakeVectorIndex:
    def __init__(self, hits: UUID | list[UUID | tuple[UUID, float]]) -> None:
        self.hits = hits if isinstance(hits, list) else [hits]

    async def search(self, *_: object, **__: object) -> list[VectorHit]:
        return [
            VectorHit(
                id=item[0] if isinstance(item, tuple) else item,
                score=item[1] if isinstance(item, tuple) else 0.95,
                payload={},
            )
            for item in self.hits
        ]


class FakeEnricher:
    def __init__(self, expansion: GraphRetrievalExpansion) -> None:
        self.expansion = expansion

    async def expand(self, *_: object, **__: object) -> GraphRetrievalExpansion:
        return self.expansion


async def test_phase5_fuses_graph_channel_and_keeps_supporting_source() -> None:
    vault_id = uuid4()
    keyword_chunk = replace(make_chunk(uuid4()), vault_id=vault_id)
    semantic_chunk = replace(make_chunk(uuid4()), vault_id=vault_id)
    graph_chunk = replace(make_chunk(uuid4(), "The CMTS uses DHCP."), vault_id=vault_id)
    source_entity_id, target_entity_id = uuid4(), uuid4()
    assertion_id = uuid4()
    entity = RetrievalEntity(
        entity_id=source_entity_id,
        vault_id=vault_id,
        canonical_name="CMTS",
        entity_type="NETWORK_ELEMENT",
        entity_subtype="CMTS",
        scope="type",
        score=1.0,
        seed_channels=("entity",),
        source_chunk_ids=(graph_chunk.chunk_id,),
    )
    relationship = RetrievalRelationship(
        assertion_id=assertion_id,
        subject_entity_id=source_entity_id,
        object_entity_id=target_entity_id,
        predicate="USES",
        assertion_kind="explicit_source",
        review_status="unreviewed",
        evidence_id=uuid4(),
        source_chunk_id=graph_chunk.chunk_id,
        quote="The CMTS uses DHCP.",
        char_start=10,
        char_end=29,
    )
    expansion = GraphRetrievalExpansion(
        entities=(entity,),
        relationships=(relationship,),
        paths=(
            RetrievalPath(
                entity_ids=(source_entity_id, target_entity_id),
                assertion_ids=(assertion_id,),
                source_chunk_ids=(graph_chunk.chunk_id,),
                hops=1,
            ),
        ),
        source_chunks=(graph_chunk,),
        warnings=(),
        truncated=False,
    )
    claim = RetrievalClaim(
        claim_id=uuid4(),
        text="The CMTS uses DHCP.",
        assertion_kind="explicit_source",
        review_status="unreviewed",
        evidence_id=uuid4(),
        source_chunk_id=graph_chunk.chunk_id,
        quote="The CMTS uses DHCP.",
        char_start=10,
        char_end=29,
        score=1.0,
        seed_channels=("chunk", "claim_text"),
    )
    store = FakeRetrievalStore(
        keyword=keyword_chunk,
        semantic=semantic_chunk,
        claims=[(claim, graph_chunk)],
    )
    service = Phase5RetrievalService(
        store=store,  # type: ignore[arg-type]
        projection_store=FakeProjectionStore(),  # type: ignore[arg-type]
        vector_index=FakeVectorIndex(semantic_chunk.chunk_id),  # type: ignore[arg-type]
        embedding_provider=FakeEmbeddingProvider(),
        query_planner=DeterministicQueryPlanner(),
        graph_enricher=FakeEnricher(expansion),  # type: ignore[arg-type]
        candidate_limit=10,
        claim_limit=20,
        max_limit=20,
        rrf_k=60,
        chunks_alias="active",
    )

    result = await service.retrieve(
        "Mivel kommunikál a CMTS?",
        strategy="hybrid",
        limit=2,
        vault_id=vault_id,
    )

    assert result.query_type == "graph"
    assert result.planner_reason_code == "relationship_or_path_cue"
    assert result.retrieval_plan == ("keyword", "semantic", "entity", "graph", "claim")
    assert result.relationships == (relationship,)
    assert result.claims == (claim,)
    returned_source_ids = {item.chunk_id for item in [*result.chunks, *result.context_chunks]}
    assert graph_chunk.chunk_id in returned_source_ids
    assert all(item.fusion_score is not None for item in result.chunks)
    assert any(item.claim_score is not None for item in result.chunks)
    assert store.audit is not None
    assert store.audit["request"] == {
        "limit": 2,
        "vault_id": str(vault_id),
        "query_type": "graph",
        "channels": ["keyword", "semantic", "entity", "graph", "claim"],
        "planner_reason_code": "relationship_or_path_cue",
    }


async def test_phase5_filters_generic_entity_smtp_branch_from_consensus_evidence() -> None:
    vault_id = uuid4()
    relevant = replace(
        make_chunk(uuid4(), "Kiskőrös éjszaka a készenlét 2 területhez tartozik."),
        vault_id=vault_id,
        relative_path="night-duty.md",
    )
    smtp = replace(
        make_chunk(uuid4(), "Az ügyfél e-mail tiltásáról SPAM ticketet kell felvenni."),
        vault_id=vault_id,
        relative_path="smtp-blocking.md",
    )
    generic_entity_id, target_entity_id = uuid4(), uuid4()
    generic_entity = RetrievalEntity(
        entity_id=generic_entity_id,
        vault_id=vault_id,
        canonical_name="ügyfél értesítése",
        entity_type="PROCESS",
        entity_subtype=None,
        scope="process",
        score=0.8,
        seed_channels=("entity",),
        source_chunk_ids=(smtp.chunk_id,),
    )
    relationship = RetrievalRelationship(
        assertion_id=uuid4(),
        subject_entity_id=generic_entity_id,
        object_entity_id=target_entity_id,
        predicate="APPLIES_TO",
        assertion_kind="explicit_source",
        review_status="unreviewed",
        evidence_id=uuid4(),
        source_chunk_id=smtp.chunk_id,
        quote=smtp.text,
        char_start=smtp.char_start,
        char_end=smtp.char_end,
    )
    claim = RetrievalClaim(
        claim_id=uuid4(),
        text="Az ügyfél e-mail tiltásáról SPAM ticketet kell felvenni.",
        assertion_kind="explicit_source",
        review_status="unreviewed",
        evidence_id=uuid4(),
        source_chunk_id=smtp.chunk_id,
        quote=smtp.text,
        char_start=smtp.char_start,
        char_end=smtp.char_end,
        score=0.1,
        seed_channels=("claim_text",),
    )
    expansion = GraphRetrievalExpansion(
        entities=(generic_entity,),
        relationships=(relationship,),
        paths=(
            RetrievalPath(
                entity_ids=(generic_entity_id, target_entity_id),
                assertion_ids=(relationship.assertion_id,),
                source_chunk_ids=(smtp.chunk_id,),
                hops=1,
            ),
        ),
        source_chunks=(smtp,),
        warnings=(),
        truncated=False,
    )
    service = Phase5RetrievalService(
        store=FakeRetrievalStore(
            keyword=[relevant, smtp],
            semantic=[relevant, smtp],
            claims=[(claim, smtp)],
        ),  # type: ignore[arg-type]
        projection_store=FakeProjectionStore(),  # type: ignore[arg-type]
        vector_index=FakeVectorIndex([(relevant.chunk_id, 0.95), (smtp.chunk_id, 0.75)]),  # type: ignore[arg-type]
        embedding_provider=FakeEmbeddingProvider(),
        query_planner=DeterministicQueryPlanner(),
        graph_enricher=FakeEnricher(expansion),  # type: ignore[arg-type]
        candidate_limit=10,
        claim_limit=20,
        max_limit=20,
        rrf_k=60,
        chunks_alias="active",
    )

    result = await service.retrieve(
        "167 ügyfél modeme Kiskőrös területhez tartozik. Mi a teendő?",
        strategy="hybrid",
        limit=10,
        vault_id=vault_id,
    )

    assert [item.chunk_id for item in result.chunks] == [relevant.chunk_id]
    assert result.context_chunks == ()
    assert result.entities == ()
    assert result.relationships == ()
    assert result.claims == ()
    assert result.retrieval_paths == ()
    assert result.truncated is True


async def test_phase5_expands_only_consensus_document_context_and_skips_index() -> None:
    vault_id = uuid4()
    document_id = uuid4()
    document_version_id = uuid4()
    guide_root = replace(
        make_chunk(uuid4(), "Hívásátirányítás beállítása Android telefonon"),
        vault_id=vault_id,
        document_id=document_id,
        document_version_id=document_version_id,
        relative_path="helpdesk/hivas_atiranyitas_android.md",
        heading_path=("Hívásátirányítás beállítása Android telefonon",),
    )
    guide_step = replace(
        make_chunk(uuid4(), "A HOS APN típusa xcap."),
        vault_id=vault_id,
        document_id=document_id,
        document_version_id=document_version_id,
        relative_path=guide_root.relative_path,
        heading_path=(
            "Hívásátirányítás beállítása Android telefonon",
            "Előkészületek",
        ),
    )
    index = replace(
        make_chunk(uuid4(), "Android hívásátirányítás útmutató"),
        vault_id=vault_id,
        relative_path="00-INDEX.md",
        heading_path=("Tudásbázis", "Android"),
    )
    unrelated = replace(
        make_chunk(uuid4(), "SPAM ticket és e-mail tiltás"),
        vault_id=vault_id,
        relative_path="smtp-blocking.md",
    )
    store = FakeRetrievalStore(
        keyword=[guide_root, index],
        semantic=[guide_root, index, unrelated],
        document_context=[guide_step],
    )
    service = Phase5RetrievalService(
        store=store,  # type: ignore[arg-type]
        projection_store=FakeProjectionStore(),  # type: ignore[arg-type]
        vector_index=FakeVectorIndex(
            [
                (guide_root.chunk_id, 0.95),
                (index.chunk_id, 0.94),
                (unrelated.chunk_id, 0.70),
            ]
        ),  # type: ignore[arg-type]
        embedding_provider=FakeEmbeddingProvider(),
        query_planner=DeterministicQueryPlanner(),
        graph_enricher=FakeEnricher(GraphRetrievalExpansion((), (), (), (), (), False)),  # type: ignore[arg-type]
        candidate_limit=10,
        claim_limit=20,
        max_limit=20,
        rrf_k=60,
        chunks_alias="active",
    )

    result = await service.retrieve(
        "Segíts hívásátirányítást beállítani Android mobilon",
        strategy="hybrid",
        limit=10,
        vault_id=vault_id,
    )

    assert [item.chunk_id for item in result.chunks] == [
        guide_root.chunk_id,
        index.chunk_id,
    ]
    assert store.document_context_seed_ids == [guide_root.chunk_id]
    assert result.context_chunks == (guide_step,)
    assert unrelated.chunk_id not in {
        item.chunk_id for item in [*result.chunks, *result.context_chunks]
    }


async def test_phase5_does_not_expand_ambiguous_multiple_documents() -> None:
    vault_id = uuid4()
    first = replace(
        make_chunk(uuid4(), "Android hívásátirányítás"),
        vault_id=vault_id,
        relative_path="android-guide.md",
    )
    second = replace(
        make_chunk(uuid4(), "Android mobiltelefon beállítása"),
        vault_id=vault_id,
        relative_path="other-guide.md",
    )
    context = replace(
        make_chunk(uuid4(), "Részletes beállítási lépések"),
        vault_id=vault_id,
        document_id=first.document_id,
        document_version_id=first.document_version_id,
        relative_path=first.relative_path,
    )
    store = FakeRetrievalStore(
        keyword=[first, second],
        semantic=[first, second],
        document_context=[context],
    )
    service = Phase5RetrievalService(
        store=store,  # type: ignore[arg-type]
        projection_store=FakeProjectionStore(),  # type: ignore[arg-type]
        vector_index=FakeVectorIndex([(first.chunk_id, 0.95), (second.chunk_id, 0.94)]),  # type: ignore[arg-type]
        embedding_provider=FakeEmbeddingProvider(),
        query_planner=DeterministicQueryPlanner(),
        graph_enricher=FakeEnricher(GraphRetrievalExpansion((), (), (), (), (), False)),  # type: ignore[arg-type]
        candidate_limit=10,
        claim_limit=20,
        max_limit=20,
        rrf_k=60,
        chunks_alias="active",
    )

    result = await service.retrieve(
        "Android mobiltelefon beállítása",
        strategy="hybrid",
        limit=10,
        vault_id=vault_id,
    )

    assert store.document_context_seed_ids == []
    assert result.context_chunks == ()


async def test_phase5_uses_single_document_anchor_for_content_but_not_as_evidence() -> None:
    vault_id = uuid4()
    document_id = uuid4()
    version_id = uuid4()
    anchor = replace(
        make_chunk(uuid4(), "Éjszakás Vezénylés - ÉRTESÍTENI KELL, HA"),
        vault_id=vault_id,
        document_id=document_id,
        document_version_id=version_id,
        relative_path="noc/ejszakas_vezenyles.md",
        heading_path=("Éjszakás Vezénylés", "ÉRTESÍTENI KELL, HA"),
        retrieval_role="structural_anchor",
    )
    content = replace(
        make_chunk(uuid4(), "04:00 előtt minimum 150 végpont esetén értesíteni kell."),
        vault_id=vault_id,
        document_id=document_id,
        document_version_id=version_id,
        relative_path=anchor.relative_path,
        heading_path=(
            "Éjszakás Vezénylés",
            "ÉRTESÍTENI KELL, HA",
            "Súlyos üzemzavar 04:00 előtt",
        ),
    )
    store = FakeRetrievalStore(
        keyword=anchor,
        semantic=anchor,
        document_context=[content],
    )
    service = Phase5RetrievalService(
        store=store,  # type: ignore[arg-type]
        projection_store=FakeProjectionStore(),  # type: ignore[arg-type]
        vector_index=FakeVectorIndex([(anchor.chunk_id, 0.95)]),  # type: ignore[arg-type]
        embedding_provider=FakeEmbeddingProvider(),
        query_planner=DeterministicQueryPlanner(),
        graph_enricher=FakeEnricher(GraphRetrievalExpansion((), (), (), (), (), False)),  # type: ignore[arg-type]
        candidate_limit=10,
        claim_limit=20,
        max_limit=20,
        rrf_k=60,
        chunks_alias="active",
    )

    result = await service.retrieve(
        "167 modem állt le 02:12-kor. Mi a teendő?",
        strategy="hybrid",
        limit=10,
        vault_id=vault_id,
    )

    assert result.chunks == ()
    assert result.context_chunks == (content,)
    assert store.document_context_calls[0] == [anchor.chunk_id]
    assert all(
        item.retrieval_role == "content_evidence"
        for item in [*result.chunks, *result.context_chunks]
    )
    assert result.truncated is False


def test_deterministic_planner_is_small_model_independent() -> None:
    planner = DeterministicQueryPlanner()

    keyword = planner.plan("bármi", strategy="keyword")
    semantic = planner.plan("fogalmilag hasonló", strategy="semantic")
    graph = planner.plan("Mivel kommunikál a CMTS?", strategy="hybrid")
    entity = planner.plan("OTRS", strategy="hybrid")
    general = planner.plan("Mikor kell értesíteni az ügyeletet?", strategy="hybrid")

    assert (keyword.query_type, keyword.reason_code) == (
        "keyword",
        "explicit_keyword_strategy",
    )
    assert (semantic.query_type, semantic.reason_code) == (
        "semantic",
        "explicit_semantic_strategy",
    )
    assert (graph.query_type, graph.reason_code) == ("graph", "relationship_or_path_cue")
    assert (entity.query_type, entity.reason_code) == (
        "entity",
        "short_identifier_or_acronym",
    )
    assert (general.query_type, general.reason_code) == ("hybrid", "general_hybrid")
    assert graph.channels == ("keyword", "semantic", "entity", "graph", "claim")
