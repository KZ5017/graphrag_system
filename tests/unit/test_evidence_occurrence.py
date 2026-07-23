from __future__ import annotations

from graphrag_service.domain.extraction import (
    EvidenceError,
    EvidenceInput,
    locate_exact_evidence,
)


def test_unique_exact_quote_does_not_depend_on_model_occurrence_guess() -> None:
    result = locate_exact_evidence(
        chunk_text="Only one exact quote.",
        chunk_char_start=20,
        chunk_content_sha256="a" * 64,
        evidence=EvidenceInput(quote="exact quote", quote_occurrence=7),
    )
    assert not isinstance(result, EvidenceError)
    assert result.global_char_start == 29


def test_ambiguous_quote_still_requires_existing_occurrence() -> None:
    result = locate_exact_evidence(
        chunk_text="ONT then ONT",
        chunk_char_start=0,
        chunk_content_sha256="a" * 64,
        evidence=EvidenceInput(quote="ONT", quote_occurrence=3),
    )
    assert isinstance(result, EvidenceError)
    assert result.code == "quote_occurrence_missing"
