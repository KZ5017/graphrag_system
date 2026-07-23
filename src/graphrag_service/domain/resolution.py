from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from ipaddress import ip_address
from uuid import UUID

NORMALIZATION_RULE_CODE = "strong-identifier"
NORMALIZATION_RULE_VERSION = "1.0"

_MAC_RE = re.compile(r"^(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_FQDN_RE = re.compile(
    r"^(?=.{4,253}\.?$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"[A-Za-z]{2,63}\.?$"
)
_LABELED_IDENTIFIER_RE = re.compile(
    r"(?i)\b(?P<label>serial(?:\s+number)?|s/n|system\s+(?:id|identifier)|asset\s+id)"
    r"\s*[:#=]\s*(?P<value>[A-Z0-9][A-Z0-9._:/-]{2,127})"
)


@dataclass(frozen=True, slots=True)
class StrongIdentifier:
    kind: str
    value: str
    normalized_value: str


@dataclass(frozen=True, slots=True)
class ResolutionCandidate:
    candidate_id: UUID
    extraction_run_id: UUID
    vault_id: UUID
    ontology_version_id: UUID
    chunk_id: UUID
    evidence_span_id: UUID
    name: str
    entity_type: str
    entity_subtype: str | None
    scope: str
    assertion_kind: str
    evidence_quote: str


@dataclass(frozen=True, slots=True)
class ResolutionOutcome:
    run_id: UUID
    created_entities: int
    merged_mentions: int
    deferred_candidates: int
    review_candidates: int
    relationship_assertions: int
    claims: int


def normalize_entity_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(normalized.split())


def normalize_identifier(kind: str, value: str) -> str:
    stripped = unicodedata.normalize("NFKC", value).strip()
    if kind == "ip_address":
        return ip_address(stripped).compressed
    if kind == "mac_address":
        hexadecimal = re.sub(r"[:-]", "", stripped).upper()
        return ":".join(hexadecimal[index : index + 2] for index in range(0, 12, 2))
    if kind == "fqdn":
        return stripped.rstrip(".").lower()
    if kind == "email_address":
        local, domain = stripped.rsplit("@", 1)
        return f"{local.casefold()}@{domain.lower()}"
    if kind in {"serial_number", "system_id", "asset_id"}:
        return stripped.upper()
    raise ValueError(f"unsupported strong identifier kind: {kind}")


def extract_strong_identifiers(name: str, evidence_quote: str) -> tuple[StrongIdentifier, ...]:
    """Return only identifiers whose complete value is the entity surface name.

    Labeled identifiers are accepted only when the exact evidence contains a
    label/value pair and the candidate name equals that value. This deliberately
    excludes fuzzy names, abbreviations, model families, and inferred identifiers.
    """
    candidate = unicodedata.normalize("NFKC", name).strip()
    detected: list[tuple[str, str]] = []
    try:
        ip_address(candidate)
    except ValueError:
        pass
    else:
        detected.append(("ip_address", candidate))
    if _MAC_RE.fullmatch(candidate):
        detected.append(("mac_address", candidate))
    if _EMAIL_RE.fullmatch(candidate):
        detected.append(("email_address", candidate))
    if _FQDN_RE.fullmatch(candidate):
        detected.append(("fqdn", candidate))

    for match in _LABELED_IDENTIFIER_RE.finditer(evidence_quote):
        value = match.group("value")
        if normalize_entity_name(value) != normalize_entity_name(candidate):
            continue
        label = " ".join(match.group("label").lower().split())
        if label in {"serial", "serial number", "s/n"}:
            kind = "serial_number"
        elif label.startswith("system"):
            kind = "system_id"
        else:
            kind = "asset_id"
        detected.append((kind, value))

    unique: dict[tuple[str, str], StrongIdentifier] = {}
    for kind, value in detected:
        normalized_value = normalize_identifier(kind, value)
        unique[(kind, normalized_value)] = StrongIdentifier(kind, value, normalized_value)
    return tuple(unique[key] for key in sorted(unique))


def exact_name_score(left: str, right: str) -> Decimal | None:
    if normalize_entity_name(left) == normalize_entity_name(right):
        return Decimal("1.0000")
    return None
