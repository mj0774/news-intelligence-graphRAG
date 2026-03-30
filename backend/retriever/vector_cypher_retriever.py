from __future__ import annotations

from typing import Any, Dict, List

import neo4j
from neo4j_graphrag.retrievers import VectorCypherRetriever
from neo4j_graphrag.types import RetrieverResultItem

from backend.retriever.common import enrich_articles_from_graph, items_to_articles


class VectorCypherNewsRetriever:
    """Vector + Cypher 확장 검색 retriever."""

    def __init__(self, driver: neo4j.Driver, embedder: Any, index_name: str = "content_vector_index") -> None:
        self.driver = driver
        retrieval_query = """
        OPTIONAL MATCH (node)<-[:HAS_CHUNK]-(a:Article)
        OPTIONAL MATCH (a)-[:BELONGS_TO]->(cat:Category)
        OPTIONAL MATCH (m:Media)-[:PUBLISHED]->(a)
        RETURN
            a.article_id AS article_id,
            a.title AS title,
            a.url AS url,
            a.published_date AS published_date,
            coalesce(cat.name, '') AS category,
            coalesce(m.name, '') AS source,
            coalesce(node.chunk, '') AS summary,
            [coalesce(node.chunk, '')] AS chunks,
            score
        """

        self.retriever = VectorCypherRetriever(
            driver=driver,
            index_name=index_name,
            embedder=embedder,
            retrieval_query=retrieval_query,
            result_formatter=self._result_formatter,
        )

    @staticmethod
    def _result_formatter(record: neo4j.Record) -> RetrieverResultItem:
        return RetrieverResultItem(
            content=str(record.get("summary", "")),
            metadata={
                "article_id": str(record.get("article_id", "")),
                "title": str(record.get("title", "")),
                "url": str(record.get("url", "")),
                "published_date": str(record.get("published_date", "")),
                "category": str(record.get("category", "")),
                "source": str(record.get("source", "")),
                "summary": str(record.get("summary", ""))[:260],
                "chunks": record.get("chunks", []),
                "score": record.get("score"),
            },
        )

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        result = self.retriever.search(query_text=query, top_k=top_k)
        articles = items_to_articles(result.items)
        return enrich_articles_from_graph(self.driver, articles)

    def to_tool(self):
        return self.retriever.convert_to_tool(
            name="vectorcypher_retriever",
            description="벡터 검색 후 그래프 관계(Category/Media)를 함께 확장해 검색합니다.",
        )
