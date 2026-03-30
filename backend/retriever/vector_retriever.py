from __future__ import annotations

"""VectorRetriever 래퍼 모듈.

의미 기반(임베딩 유사도) 검색으로 Content 청크를 찾고,
기사 단위 응답 형태로 정리한다.
"""

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
        """VectorRetriever 원시 레코드를 표준 결과 아이템으로 변환한다.

        기본 VectorRetriever는 `node`와 `score`를 반환하므로,
        여기서 Content 노드의 핵심 속성만 추출해 metadata에 담는다.
        """
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
        """질의 임베딩 기반으로 유사 청크를 찾고 기사 목록으로 반환한다."""
        result = self.retriever.search(query_text=query, top_k=top_k)
        articles = items_to_articles(result.items)

        # category/source/chunks 등 보조 정보를 그래프에서 보강한다.
        return enrich_articles_from_graph(self.driver, articles)

    def to_tool(self):
        """ToolsRetriever에서 사용할 Tool 객체로 변환한다."""
        return self.retriever.convert_to_tool(
            name="vector_retriever",
            description="키워드나 개념으로 유사한 기사를 빠르게 찾을 때 사용. 단순 검색용.",
        )
