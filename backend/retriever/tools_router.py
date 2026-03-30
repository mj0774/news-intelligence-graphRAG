from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

import neo4j
from neo4j_graphrag.generation import GraphRAG, RagTemplate
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
    highlighted_node_ids: List[str]
    highlighted_edge_ids: List[str]


class ToolsRouter:
    """참고자료1/2 흐름을 결합한 ToolsRetriever 기반 검색 라우터."""

    def __init__(self, driver: neo4j.Driver, llm: Any, embedder: Any) -> None:
        self.driver = driver

        # Text2Cypher는 인덱스 유무와 무관하게 항상 사용 가능하다.
        self.text2cypher = Text2CypherNewsRetriever(driver=driver, llm=llm)

        tools = [self.text2cypher.to_tool()]
        self.vector = None

        # 벡터 인덱스가 존재하면 참고자료1처럼 Vector 계열 도구를 함께 등록한다.
        if self._vector_index_exists("content_vector_index"):
            vector = VectorNewsRetriever(driver=driver, embedder=embedder)
            vector_cypher = VectorCypherNewsRetriever(driver=driver, embedder=embedder)

            self.vector = vector
            tools = [vector.to_tool(), vector_cypher.to_tool(), self.text2cypher.to_tool()]
        else:
            print("[WARN] content_vector_index가 없어 Text2Cypher만 활성화합니다.")

        self.tools_retriever = ToolsRetriever(
            driver=driver,
            llm=llm,
            tools=tools,
        )

        # 참고자료2와 동일하게 Retriever + LLM 조합으로 최종 답변을 생성한다.
        self.graphrag = GraphRAG(
            llm=llm,
            retriever=self.tools_retriever,
            prompt_template=RagTemplate(
                template="""
당신은 뉴스 기사 검색 결과를 설명하는 도우미입니다.

질문:
{query_text}

검색 컨텍스트:
{context}

규칙:
1. 검색된 기사 범위 안에서만 답변합니다.
2. 기사 제목/핵심 내용을 간결하게 요약합니다.
3. 추측은 하지 않습니다.
4. 마지막에 출처 목록(제목, URL)을 정리합니다.
""",
                expected_inputs=["query_text", "context"],
            ),
        )

    def search(self, query: str, top_k: int = 5) -> ToolSearchResult:
        rag_result = self.graphrag.search(query_text=query, return_context=True)

        retriever_result = getattr(rag_result, "retriever_result", None)
        items = getattr(retriever_result, "items", []) if retriever_result else []
        articles = items_to_articles(items)

        used_tool = self._detect_used_tool(retriever_result)

        # 검색 결과가 비어 있고 벡터 도구가 있으면 한 번 더 fallback 검색한다.
        if not articles and self.vector is not None:
            fallback_articles = self.vector.search(query=query, top_k=top_k)
            if fallback_articles:
                articles = fallback_articles
                used_tool = "vector_retriever(fallback)"

        graph = build_graph_from_articles(articles)

        answer = getattr(rag_result, "answer", "") or ""
        if not answer:
            answer = f"'{query}' 질의에 대해 {used_tool}로 {len(articles)}건을 찾았습니다."

        return ToolSearchResult(
            tool=used_tool,
            answer=answer,
            articles=articles,
            nodes=graph["nodes"],
            edges=graph["edges"],
            highlighted_node_ids=graph["highlighted_node_ids"],
            highlighted_edge_ids=graph["highlighted_edge_ids"],
        )

    def _vector_index_exists(self, index_name: str) -> bool:
        """Neo4j에 지정한 벡터 인덱스가 존재하는지 확인한다."""
        query = """
        SHOW INDEXES YIELD name
        WHERE name = $index_name
        RETURN count(*) AS cnt
        """
        try:
            with self.driver.session() as session:
                row = session.run(query, index_name=index_name).single()
                return bool(row and int(row.get("cnt", 0)) > 0)
        except Exception:
            return False

    @staticmethod
    def _detect_used_tool(retriever_result: Any) -> str:
        """라이브러리 버전별 메타데이터 차이를 흡수해 사용 도구명을 추출한다."""
        if retriever_result is None:
            return "tools_retriever"

        meta = getattr(retriever_result, "metadata", {}) or {}

        tools_selected = meta.get("tools_selected")
        if isinstance(tools_selected, list) and tools_selected:
            return str(tools_selected[0])

        for key in ["tool", "used_tool", "selected_tool"]:
            if meta.get(key):
                return str(meta[key])

        items = getattr(retriever_result, "items", []) or []
        for item in items:
            item_meta = getattr(item, "metadata", {}) or {}
            if item_meta.get("tool"):
                return str(item_meta["tool"])
            if item_meta.get("retriever_name"):
                return str(item_meta["retriever_name"])

        return "tools_retriever"
