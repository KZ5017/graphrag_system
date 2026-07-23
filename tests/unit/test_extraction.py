from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from graphrag_service.adapters.postgres.extraction_store import ExtractionSourceChunk
from graphrag_service.application.extraction import (
    KnowledgeExtractionService,
    extraction_json_schema,
)
from graphrag_service.domain.extraction import (
    EvidenceError,
    EvidenceInput,
    locate_exact_evidence,
)
from graphrag_service.domain.generation import (
    GenerationCapabilities,
    GenerationModelInfo,
    GenerationUsage,
    StructuredGeneration,
)
from graphrag_service.domain.ontology import ENTITY_TYPES, PREDICATES


def test_exact_quote_uses_requested_occurrence_and_global_offset() -> None:
    result = locate_exact_evidence(
        chunk_text="ONT and ONT",
        chunk_char_start=100,
        chunk_content_sha256="a" * 64,
        evidence=EvidenceInput(quote="ONT", quote_occurrence=2),
    )
    assert not isinstance(result, EvidenceError)
    assert result.local_char_start == 8
    assert result.global_char_start == 108
    assert result.global_char_end == 111


def test_missing_exact_quote_is_invalid() -> None:
    result = locate_exact_evidence(
        chunk_text="Huawei ONT",
        chunk_char_start=0,
        chunk_content_sha256="a" * 64,
        evidence=EvidenceInput(quote="huawei ont"),
    )
    assert isinstance(result, EvidenceError)
    assert result.code == "missing_quote"


def test_extraction_schema_contains_controlled_enums() -> None:
    schema = extraction_json_schema()
    definitions = schema["$defs"]
    assert definitions["ExtractedEntity"]["properties"]["entity_type"]["enum"] == list(ENTITY_TYPES)
    assert definitions["ExtractedRelationship"]["properties"]["predicate"]["enum"] == list(
        PREDICATES
    )


class FakeProvider:
    def __init__(self, data: dict[str, object]) -> None:
        self.data = data

    async def model_info(self) -> GenerationModelInfo:
        return GenerationModelInfo(
            provider="fake",
            model="qwen/qwen3.5-9b",
            capabilities=GenerationCapabilities(
                structured_output=True,
                reasoning_effort=True,
            ),
        )

    async def generate_structured(self, **_: object) -> StructuredGeneration:
        return StructuredGeneration(
            data=self.data,
            model="qwen/qwen3.5-9b",
            finish_reason="stop",
            usage=GenerationUsage(10, 5, 15),
            response_sha256="b" * 64,
        )

    async def healthcheck(self) -> str:
        return "available"

    async def close(self) -> None:
        return None


class FakeStore:
    def __init__(self, source: ExtractionSourceChunk) -> None:
        self.source = source
        self.run_id = uuid4()
        self.success: dict[str, object] | None = None
        self.schema_invalid = False

    async def register_runtime(self, **_: object) -> object:
        return SimpleNamespace()

    async def select_current_chunks(self, **_: object) -> tuple[ExtractionSourceChunk, ...]:
        return (self.source,)

    async def prepare_run(self, **_: object) -> UUID:
        return self.run_id

    async def pending_chunks(self, _: UUID) -> tuple[ExtractionSourceChunk, ...]:
        return (self.source,)

    async def record_success(self, **values: object) -> None:
        self.success = values

    async def record_schema_invalid(self, **_: object) -> None:
        self.schema_invalid = True

    async def finalize(self, _: UUID) -> dict[str, int | str]:
        if self.schema_invalid:
            return {
                "status": "partial",
                "processed_chunks": 1,
                "valid_candidates": 0,
                "invalid_candidates": 0,
                "prompt_tokens": 10,
                "completion_tokens": 5,
            }
        assert self.success is not None
        groups = (
            self.success["entities"],
            self.success["relationships"],
            self.success["claims"],
        )
        items = [item for group in groups for item in group]  # type: ignore[union-attr]
        return {
            "status": "partial" if any(item.errors for item in items) else "succeeded",
            "processed_chunks": 1,
            "valid_candidates": sum(not item.errors for item in items),
            "invalid_candidates": sum(bool(item.errors) for item in items),
            "prompt_tokens": 10,
            "completion_tokens": 5,
        }


@pytest.mark.asyncio
async def test_service_keeps_invalid_candidates_out_of_exact_evidence() -> None:
    source = ExtractionSourceChunk(
        id=uuid4(),
        vault_id=uuid4(),
        document_id=uuid4(),
        document_version_id=uuid4(),
        section_id=uuid4(),
        relative_path="ONT.md",
        heading_path=("ONT",),
        ordinal=0,
        char_start=50,
        text="Huawei EG8145V5 uses ACS.",
        content_sha256="a" * 64,
    )
    data = {
        "entities": [
            {
                "local_id": "e1",
                "name": "Huawei EG8145V5",
                "entity_type": "DEVICE_MODEL",
                "entity_subtype": "ONT",
                "proposed_subtype": None,
                "scope": "model",
                "assertion_kind": "explicit",
                "evidence": {"quote": "Huawei EG8145V5", "quote_occurrence": 1},
            },
            {
                "local_id": "e2",
                "name": "ACS",
                "entity_type": "SYSTEM",
                "entity_subtype": None,
                "proposed_subtype": None,
                "scope": "logical",
                "assertion_kind": "explicit",
                "evidence": {"quote": "missing ACS quote", "quote_occurrence": 1},
            },
        ],
        "relationships": [
            {
                "subject_local_id": "e1",
                "predicate": "USES",
                "object_local_id": "e2",
                "assertion_kind": "explicit",
                "network_layer": None,
                "evidence": {"quote": "uses", "quote_occurrence": 1},
            }
        ],
        "claims": [
            {
                "text": "The Huawei model uses ACS.",
                "assertion_kind": "normalized",
                "evidence": {
                    "quote": "Huawei EG8145V5 uses ACS.",
                    "quote_occurrence": 1,
                },
            }
        ],
    }
    store = FakeStore(source)
    service = KnowledgeExtractionService(
        store=store,  # type: ignore[arg-type]
        provider=FakeProvider(data),
        max_chunks_per_job=6,
    )
    outcome = await service.run_pilot(
        job_id=uuid4(),
        vault_id=source.vault_id,
        document_ids=(source.document_id,),
        max_chunks=1,
    )
    assert outcome.valid_candidates == 2
    assert outcome.invalid_candidates == 2
    assert store.success is not None
    entities = store.success["entities"]
    relationships = store.success["relationships"]
    assert entities[0].evidence is not None  # type: ignore[index]
    assert entities[1].evidence is None  # type: ignore[index]
    assert "invalid_object_entity" in relationships[0].errors  # type: ignore[index]


@pytest.mark.asyncio
async def test_schema_invalid_response_is_not_partially_stored() -> None:
    source = ExtractionSourceChunk(
        id=uuid4(),
        vault_id=uuid4(),
        document_id=uuid4(),
        document_version_id=uuid4(),
        section_id=uuid4(),
        relative_path="test.md",
        heading_path=(),
        ordinal=0,
        char_start=0,
        text="source",
        content_sha256="a" * 64,
    )
    store = FakeStore(source)
    service = KnowledgeExtractionService(
        store=store,  # type: ignore[arg-type]
        provider=FakeProvider({"entities": [], "relationships": [], "claims": [], "extra": 1}),
        max_chunks_per_job=6,
    )
    outcome = await service.run_pilot(
        job_id=uuid4(),
        vault_id=source.vault_id,
        document_ids=(source.document_id,),
        max_chunks=1,
    )
    assert outcome.status == "partial"
    assert store.schema_invalid is True
    assert store.success is None
