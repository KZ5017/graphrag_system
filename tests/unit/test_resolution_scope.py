from sqlalchemy import UniqueConstraint

from graphrag_service.adapters.postgres.resolution_models import EntityIdentifierModel


def test_strong_identifier_uniqueness_is_scoped_by_vault_type_and_scope() -> None:
    constraint = next(
        item
        for item in EntityIdentifierModel.__table__.constraints
        if isinstance(item, UniqueConstraint)
        and item.name == "uq_entity_identifiers_strong_identity"
    )
    assert tuple(column.name for column in constraint.columns) == (
        "vault_id",
        "normalization_rule_id",
        "identifier_kind",
        "normalized_value",
        "entity_type_code",
        "entity_scope",
    )
