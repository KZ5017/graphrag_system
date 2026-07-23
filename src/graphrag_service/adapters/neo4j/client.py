from __future__ import annotations

from typing import Any
from uuid import UUID

from neo4j import AsyncDriver, AsyncGraphDatabase

from graphrag_service.domain.graph import GraphSnapshot

NODE_LABELS = (
    "Vault",
    "Document",
    "DocumentVersion",
    "Section",
    "Chunk",
    "Entity",
    "RelationshipAssertion",
    "Claim",
    "Evidence",
)

RELATIONSHIP_ENDPOINTS = {
    "CONTAINS": ("Vault", "Document"),
    "HAS_VERSION": ("Document", "DocumentVersion"),
    "HAS_SECTION": ("DocumentVersion", "Section"),
    "HAS_CHILD": ("Section", "Section"),
    "HAS_CHUNK": ("Section", "Chunk"),
    "LINKS_TO": ("Document", "Document"),
    "MENTIONS": ("Chunk", "Entity"),
    "SUBJECT": ("RelationshipAssertion", "Entity"),
    "OBJECT": ("RelationshipAssertion", "Entity"),
    "ENTITY_LINK": ("Entity", "Entity"),
    "ASSERTION_SUPPORTED_BY": ("RelationshipAssertion", "Evidence"),
    "CLAIM_SUPPORTED_BY": ("Claim", "Evidence"),
    "LOCATED_IN": ("Evidence", "Chunk"),
}


class Neo4jGraphAdapter:
    def __init__(
        self,
        *,
        uri: str,
        username: str,
        password: str,
        database: str,
    ) -> None:
        self._driver: AsyncDriver = AsyncGraphDatabase.driver(
            uri,
            auth=(username, password),
        )
        self._database = database

    async def close(self) -> None:
        await self._driver.close()

    async def ensure_schema(self) -> None:
        async with self._driver.session(database=self._database) as session:
            for label in NODE_LABELS:
                await session.run(
                    f"CREATE CONSTRAINT gks_{label.lower()}_id IF NOT EXISTS "
                    f"FOR (n:{label}) REQUIRE n.id IS UNIQUE"
                )
            await session.run(
                "CREATE INDEX gks_entity_type_name IF NOT EXISTS "
                "FOR (n:Entity) ON (n.entity_type, n.normalized_name)"
            )
            await session.run(
                "CREATE INDEX gks_document_vault_path IF NOT EXISTS "
                "FOR (n:Document) ON (n.vault_id, n.relative_path)"
            )
            await session.run(
                "CREATE INDEX gks_assertion_predicate_status IF NOT EXISTS "
                "FOR (n:RelationshipAssertion) ON (n.predicate, n.status)"
            )
            await session.run(
                "CREATE INDEX gks_evidence_chunk IF NOT EXISTS FOR (n:Evidence) ON (n.chunk_id)"
            )

    async def replace_vault_snapshot(self, snapshot: GraphSnapshot) -> None:
        async with self._driver.session(database=self._database) as session:
            await session.execute_write(self._replace_transaction, snapshot)

    @staticmethod
    async def _replace_transaction(transaction: Any, snapshot: GraphSnapshot) -> None:
        vault_id = str(snapshot.vault_id)
        await transaction.run(
            "MATCH (n {gks_managed: true, vault_id: $vault_id}) DETACH DELETE n",
            vault_id=vault_id,
        )
        for label in NODE_LABELS:
            rows = list(snapshot.nodes.get(label, ()))
            if not rows:
                continue
            await transaction.run(
                f"UNWIND $rows AS row CREATE (n:{label}) SET n = row",
                rows=rows,
            )
        for relationship_type, (source_label, target_label) in RELATIONSHIP_ENDPOINTS.items():
            rows = list(snapshot.relationships.get(relationship_type, ()))
            if not rows:
                continue
            stored_type = (
                "SUPPORTED_BY"
                if relationship_type in {"ASSERTION_SUPPORTED_BY", "CLAIM_SUPPORTED_BY"}
                else relationship_type
            )
            await transaction.run(
                f"UNWIND $rows AS row "
                f"MATCH (source:{source_label} {{id: row.source_id}}) "
                f"MATCH (target:{target_label} {{id: row.target_id}}) "
                f"CREATE (source)-[r:{stored_type}]->(target) "
                "SET r = coalesce(row.properties, {})",
                rows=rows,
            )

    async def neighbors(
        self,
        *,
        entity_id: UUID,
        predicate: str | None,
        entity_type: str | None,
        max_results: int,
        include_unreviewed: bool,
    ) -> list[dict[str, Any]]:
        query = """
        MATCH (source:Entity {id: $entity_id})
        MATCH (assertion:RelationshipAssertion)-[:SUBJECT]->(subject:Entity)
        MATCH (assertion)-[:OBJECT]->(object:Entity)
        WHERE assertion.status = 'active'
          AND (subject = source OR object = source)
          AND ($predicate IS NULL OR assertion.predicate = $predicate)
          AND ($include_unreviewed OR assertion.review_status <> 'unreviewed')
        WITH assertion, CASE WHEN subject = source THEN object ELSE subject END AS neighbor,
             CASE WHEN subject = source THEN 'outgoing' ELSE 'incoming' END AS direction
        WHERE $entity_type IS NULL OR neighbor.entity_type = $entity_type
        RETURN neighbor, assertion, direction
        ORDER BY assertion.predicate, neighbor.canonical_name, assertion.id
        LIMIT $max_results
        """
        async with self._driver.session(database=self._database) as session:
            result = await session.run(
                query,
                entity_id=str(entity_id),
                predicate=predicate,
                entity_type=entity_type,
                max_results=max_results,
                include_unreviewed=include_unreviewed,
            )
            return [
                {
                    "entity": dict(record["neighbor"]),
                    "assertion": dict(record["assertion"]),
                    "direction": record["direction"],
                }
                async for record in result
            ]

    async def bounded_paths(
        self,
        *,
        from_entity_id: UUID,
        to_entity_id: UUID,
        max_hops: int,
        max_paths: int,
        predicate_allowlist: tuple[str, ...],
        include_unreviewed: bool,
    ) -> list[dict[str, Any]]:
        # Cypher requires the relationship length bound to be literal. max_hops is
        # validated to 1..4 by the API before it reaches this fixed-format query.
        query = f"""
        MATCH (start:Entity {{id: $from_id}}), (target:Entity {{id: $to_id}})
        MATCH path = (start)-[:ENTITY_LINK*1..{max_hops}]-(target)
        WHERE ALL(rel IN relationships(path)
          WHERE (size($predicates) = 0 OR rel.predicate IN $predicates)
            AND ($include_unreviewed OR rel.review_status <> 'unreviewed'))
        RETURN [node IN nodes(path) | node {{.*}}] AS entities,
               [rel IN relationships(path) | rel {{.*}}] AS assertions,
               length(path) AS hops
        ORDER BY hops
        LIMIT $max_paths
        """
        async with self._driver.session(database=self._database) as session:
            result = await session.run(
                query,
                from_id=str(from_entity_id),
                to_id=str(to_entity_id),
                predicates=list(predicate_allowlist),
                include_unreviewed=include_unreviewed,
                max_paths=max_paths,
            )
            return [
                {
                    "entities": record["entities"],
                    "assertions": record["assertions"],
                    "hops": record["hops"],
                }
                async for record in result
            ]
