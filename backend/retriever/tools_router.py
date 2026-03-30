from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

import neo4j
from neo4j_graphrag.retrievers import ToolsRetriever

from backend.retriever.common import build_graph_from_articles, items_to_articles
from backend.retriever.text2cypher_retriever import Text2CypherNewsRetriever
from backend.retriever.vector_cypher_retriever import VectorCypherNewsRetriever
from backend.retriever.vector_retriever import VectorNewsRetriever


@dataclass
class ToolSearchResult:
    tool: str
    answer: str
    articles: List[Dict[str, Any]]
    nodes: List[Dict[str, str]]
    edges: List[Dict[str, str]]


class ToolsRouter:
    """ToolsRetriever 기반 검색 라우터.

    참고자료와 동일하게 retriever를 tool로 등록하고,
    질의마다 LLM이 적절한 tool을 선택해 실행하도록 구성한다.
    """

    def __init__(self, driver: neo4j.Driver, llm: Any, embedder: Any) -> None:
        self.vector = VectorNewsRetriever(driver=driver, embedder=embedder)
        self.vector_cypher = VectorCypherNewsRetriever(driver=driver, embedder=embedder)
        self.text2cypher = Text2CypherNewsRetriever(driver=driver, llm=llm)

        self.tools_retriever = ToolsRetriever(
            driver=driver,
            llm=llm,
            tools=[
                self.vector.to_tool(),
                self.vector_cypher.to_tool(),
                self.text2cypher.to_tool(),
            ],
        )

    def search(self, query: str, top_k: int = 5) -> ToolSearchResult:
        result = self.tools_retriever.search(query_text=query)

        articles = items_to_articles(result.items)

        # Tool metadata는 도구 선택 로그를 담는다.
        # 라이브러리 버전에 따라 키 이름이 다를 수 있어 여러 키를 순차 확인한다.
        meta = getattr(result, "metadata", {}) or {}
        used_tool = (
            meta.get("tool")
            or meta.get("used_tool")
            or meta.get("selected_tool")
            or "tools_retriever"
        )

        # 결과가 비면 vector retriever를 fallback으로 호출해 빈 응답을 줄인다.
        if not articles:
            fallback_articles = self.vector.search(query=query, top_k=top_k)
            if fallback_articles:
                articles = fallback_articles
                used_tool = "vector_retriever(fallback)"

        graph = build_graph_from_articles(articles)
        answer = f"'{query}' 질의에 대해 {used_tool}로 {len(articles)}건을 찾았습니다."

        return ToolSearchResult(
            tool=used_tool,
            answer=answer,
            articles=articles,
            nodes=graph["nodes"],
            edges=graph["edges"],
        )
