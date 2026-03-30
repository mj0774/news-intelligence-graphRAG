from __future__ import annotations

from typing import Any, Dict, List

import neo4j
from neo4j_graphrag.retrievers import VectorRetriever
from neo4j_graphrag.types import RetrieverResultItem

from backend.retriever.common import enrich_articles_from_graph, items_to_articles


class VectorNewsRetriever:
    """Content 벡터 유사도 기반 retriever."""

    def __init__(self, driver: neo4j.Driver, embedder: Any, index_name: str = "content_vector_index") -> None:
        self.driver = driver
        self.retriever = VectorRetriever(
            driver=driver,
            index_name=index_name,
            embedder=embedder,
            result_formatter=self._result_formatter,
        )

    @staticmethod
    def _result_formatter(record: neo4j.Record) -> RetrieverResultItem:
        node = record.get("node")
        score = record.get("score")
        props = dict(node) if node is not None else {}

        article_id = str(props.get("article_id", ""))
        chunk = str(props.get("chunk", ""))

        return RetrieverResultItem(
            content=chunk,
            metadata={
                "article_id": article_id,
                "summary": chunk[:260],
                "chunks": [chunk] if chunk else [],
                "score": score,
            },
        )

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        result = self.retriever.search(query_text=query, top_k=top_k)
        articles = items_to_articles(result.items)
        return enrich_articles_from_graph(self.driver, articles)

    def to_tool(self):
        """ToolsRetriever에서 사용할 Tool 객체로 변환한다."""
        return self.retriever.convert_to_tool(
            name="vector_retriever",
            description="본문 의미 유사도 기반으로 관련 기사 청크를 검색합니다.",
        )
