from __future__ import annotations

from dataclasses import dataclass

ONTOLOGY_CODE = "telecom-core"
ONTOLOGY_VERSION = "0.1"

ENTITY_TYPES: dict[str, str] = {
    "ORGANIZATION": "company or organization",
    "ORG_UNIT": "directorate, department, or team",
    "PERSON": "person named in the document",
    "ROLE": "job or functional role",
    "PROCESS": "business or technical process",
    "CAPABILITY": "enterprise capability",
    "POLICY": "rule, policy, or principle",
    "PRODUCT": "sellable product",
    "SERVICE": "customer-facing or internal service",
    "CUSTOMER_SEGMENT": "customer segment",
    "EXTERNAL_PARTY": "partner, supplier, authority, or external party",
    "SYSTEM": "IT or network system",
    "APPLICATION": "application or software",
    "COMPONENT": "system component or subsystem",
    "NETWORK_ELEMENT": "logical or physical network element",
    "DEVICE_MODEL": "device model",
    "DEVICE_INSTANCE": "specific device instance",
    "NETWORK_SEGMENT": "network segment or domain",
    "INTERFACE": "physical or logical interface",
    "PROTOCOL": "network or application protocol",
    "TECHNOLOGY": "technology or standard",
    "SITE": "site, node location, or POP",
    "LOCATION": "geographic or organizational location",
    "INFRASTRUCTURE_ASSET": "cable, route, rack, or infrastructure asset",
    "DOCUMENT": "object referenced as a document",
    "CONCEPT": "concept, method, or abstract category",
    "OTHER": "controlled fallback",
}

ENTITY_SUBTYPES: dict[str, tuple[str, ...]] = {
    "NETWORK_ELEMENT": (
        "CMTS",
        "CBR",
        "ASR_ROUTER",
        "OLT",
        "HFC_NODE",
        "ACCESS_NODE",
        "AGGREGATION_ROUTER",
    ),
    "DEVICE_MODEL": ("ONT", "CABLE_MODEM", "SMART_DEVICE", "ROUTER", "SWITCH", "SET_TOP_BOX"),
    "DEVICE_INSTANCE": (
        "ONT",
        "CABLE_MODEM",
        "SMART_DEVICE",
        "ROUTER",
        "SWITCH",
        "SET_TOP_BOX",
    ),
}

PREDICATES: tuple[str, ...] = (
    "PART_OF",
    "INSTANCE_OF",
    "HAS_COMPONENT",
    "DEPENDS_ON",
    "USES",
    "SUPPORTS",
    "IMPLEMENTS",
    "OWNS",
    "RESPONSIBLE_FOR",
    "OPERATES",
    "MAINTAINS",
    "INPUT_TO",
    "OUTPUT_OF",
    "PRECEDES",
    "TRIGGERS",
    "PROVIDES",
    "SERVES",
    "SUPPLIED_BY",
    "CONNECTS_TO",
    "TERMINATES_AT",
    "ROUTES_VIA",
    "LOCATED_AT",
    "DESCRIBES",
    "APPLIES_TO",
    "REFERENCES",
    "RELATED_TO",
)

ENTITY_SCOPES: tuple[str, ...] = ("category", "type", "model", "instance", "logical")
ASSERTION_KINDS: tuple[str, ...] = ("explicit", "normalized", "inferred")
NETWORK_LAYERS: tuple[str, ...] = (
    "physical",
    "access",
    "layer_2",
    "layer_3",
    "transport",
    "service",
    "business",
)


@dataclass(frozen=True, slots=True)
class OntologySnapshot:
    code: str = ONTOLOGY_CODE
    version: str = ONTOLOGY_VERSION
    entity_types: frozenset[str] = frozenset(ENTITY_TYPES)
    predicates: frozenset[str] = frozenset(PREDICATES)
    entity_scopes: frozenset[str] = frozenset(ENTITY_SCOPES)
    assertion_kinds: frozenset[str] = frozenset(ASSERTION_KINDS)
    network_layers: frozenset[str] = frozenset(NETWORK_LAYERS)

    def valid_subtype(self, entity_type: str, subtype: str | None) -> bool:
        if subtype is None:
            return True
        return subtype in ENTITY_SUBTYPES.get(entity_type, ())
