from __future__ import annotations

"""VectorCypherRetriever 래퍼 모듈.

벡터 검색으로 관련 Content를 찾은 뒤,
Cypher 확장 조회로 Article/Category/related_articles 정보를 함께 가져온다.
"""

from typing import Any, Dict, List

import neo4j
from neo4j_graphrag.retrievers import VectorCypherRetriever
from neo4j_graphrag.types import RetrieverResultItem

from backend.retriever.common import enrich_articles_from_graph, items_to_articles


class VectorCypherNewsRetriever:
    """Vector + Cypher 결합형 retriever."""

    def __init__(self, driver: neo4j.Driver, embedder: Any, index_name: str = "content_vector_index") -> None:
        self.driver = driver

        # 프로젝트 검색 목적에 맞춘 retrieval_query를 사용한다.
        # 핵심: 유사 Content를 찾은 후 해당 Article과 Category, 연관 Article까지 확장 조회.
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
        """VectorCypher 조회 결과를 공통 기사 포맷으로 정규화한다."""
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
        """벡터+그래프 결합 검색을 수행하고 기사 리스트를 반환한다."""
        result = self.retriever.search(query_text=query, top_k=top_k)
        articles = items_to_articles(result.items)
        return enrich_articles_from_graph(self.driver, articles)

    def to_tool(self):
        """ToolsRetriever에서 사용할 Tool 객체로 변환한다."""
        return self.retriever.convert_to_tool(
            name="vectorcypher_retriever",
            description="기사의 상세 정보/전체 정보/본문을 요청할 때 사용. 특정 주제로 기사를 찾고 제목, URL, 날짜, 카테고리, 관련 기사까지 반환.",
        )

