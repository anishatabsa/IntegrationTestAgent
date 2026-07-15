"""
Graph RAG — traverses Neo4j knowledge graph to find entity relationships.
Optional: only active when NEO4J_ENABLED=true.
"""
from __future__ import annotations

import structlog

logger = structlog.get_logger()


class GraphRAG:
    def __init__(self, neo4j_driver) -> None:
        self._driver = neo4j_driver

    async def search(self, service_name: str, query: str, top_k: int = 5) -> list[str]:
        """
        Queries Neo4j for nodes related to the query terms and returns
        their text properties as context snippets.
        """
        try:
            async with self._driver.session() as session:
                result = await session.run(
                    """
                    CALL db.index.fulltext.queryNodes('knowledgeIndex', $query)
                    YIELD node, score
                    WHERE node.service = $service OR node.service IS NULL
                    RETURN node.text AS text, score
                    ORDER BY score DESC
                    LIMIT $limit
                    """,
                    query=query,
                    service=service_name,
                    limit=top_k,
                )
                records = await result.values()
                return [r[0] for r in records if r[0]]
        except Exception as exc:
            logger.warning("graph_rag_error", error=str(exc))
            return []
