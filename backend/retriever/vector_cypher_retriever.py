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

        # 참고자료1의 수정 쿼리를 그대로 반영한다.
        retrieval_query = """
        WITH node AS content, score
        MATCH (content)<-[:HAS_CHUNK]-(article:Article)
        OPTIONAL MATCH (article)-[:BELONGS_TO]->(category:Category)
        OPTIONAL MATCH (category)<-[:BELONGS_TO]-(related_article:Article)
        WHERE related_article <> article

        RETURN
            content.content_id AS content_id,
            content.chunk AS chunk,
            content.title AS content_title,
            article.article_id AS article_id,
            article.title AS article_title,
            article.url AS article_url,
            article.published_date AS article_date,
            category.name AS category_name,
            score AS similarity_score,
            collect(DISTINCT {
                article_id: related_article.article_id,
                title: related_article.title,
                url: related_article.url,
                published_date: related_article.published_date
            })[0..5] AS related_articles
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
        chunk = str(record.get("chunk", ""))
        return RetrieverResultItem(
            content=chunk,
            metadata={
                "article_id": str(record.get("article_id", "")),
                "title": str(record.get("article_title", "")),
                "url": str(record.get("article_url", "")),
                "published_date": str(record.get("article_date", "")),
                "category": str(record.get("category_name", "")),
                "source": "",
                "summary": chunk[:260],
                "chunks": [chunk] if chunk else [],
                "score": record.get("similarity_score"),
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
