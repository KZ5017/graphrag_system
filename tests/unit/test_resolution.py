from graphrag_service.domain.resolution import (
    extract_strong_identifiers,
    normalize_entity_name,
    normalize_identifier,
)


def test_strong_identifier_normalization_is_deterministic() -> None:
    assert normalize_identifier("ip_address", "2001:0db8::1") == "2001:db8::1"
    assert normalize_identifier("mac_address", "aa-bb-cc-dd-ee-ff") == "AA:BB:CC:DD:EE:FF"
    assert normalize_identifier("fqdn", "OLT-01.Example.COM.") == "olt-01.example.com"
    assert normalize_entity_name("  Huawei   ONT ") == "huawei ont"


def test_labeled_serial_requires_candidate_name_to_equal_exact_value() -> None:
    identifiers = extract_strong_identifiers(
        "ONT-ABC-001",
        "The device serial number: ONT-ABC-001 is installed.",
    )
    assert [(item.kind, item.normalized_value) for item in identifiers] == [
        ("serial_number", "ONT-ABC-001")
    ]
    assert (
        extract_strong_identifiers(
            "the device",
            "The device serial number: ONT-ABC-001 is installed.",
        )
        == ()
    )


def test_names_and_abbreviations_are_never_treated_as_strong_identifiers() -> None:
    assert extract_strong_identifiers("ONT", "ONT is an optical network terminal.") == ()
    assert extract_strong_identifiers("Customer Portal", "Use Customer Portal.") == ()


def test_intrinsically_strong_surface_forms_are_detected() -> None:
    identifiers = extract_strong_identifiers(
        "192.0.2.10",
        "The management endpoint is 192.0.2.10.",
    )
    assert identifiers[0].kind == "ip_address"
    assert identifiers[0].normalized_value == "192.0.2.10"
