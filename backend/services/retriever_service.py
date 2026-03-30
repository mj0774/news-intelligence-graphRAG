from __future__ import annotations

"""API와 Retriever 모듈 사이를 연결하는 서비스 계층.

핵심 목적:
- API 라우트가 retriever 구현 세부를 몰라도 되게 분리
- 검색/그래프 조회 결과를 응답 스키마 형태로 정리
"""

from typing import Any, Dict, Protocol


class SearchRouter(Protocol):
    """검색 라우터 인터페이스.

    RetrieverService는 이 인터페이스만 의존한다.
    즉, 실제 구현체가 ToolsRouter이든 다른 라우터든
    `search()` 시그니처만 맞으면 교체 가능하다.
    """

    def search(self, query: str, top_k: int = 5):
        ...


class GraphProvider(Protocol):
    """그래프 데이터 제공 인터페이스.

    서비스는 `fetch_graph()` 결과만 사용하므로,
    Neo4j 직접 조회 구현을 별도 모듈로 분리할 수 있다.
    """

    def fetch_graph(self, node_limit: int = 600, edge_limit: int = 1200):
        ...


class RetrieverService:
    """검색/그래프 조회 유스케이스를 묶는 애플리케이션 서비스."""

    def __init__(self, router: SearchRouter, graph_provider: GraphProvider) -> None:
        self.router = router
        self.graph_provider = graph_provider

    def search(self, query: str) -> Dict[str, Any]:
        """사용자 질의를 검색하고 API 응답 페이로드로 변환한다."""
        # top_k 정책은 서비스에서 통일 관리한다.
        result = self.router.search(query=query, top_k=10)

        # 반환 키는 Pydantic SearchResponse와 동일하게 맞춘다.
        return {
            "answer": result.answer,
            "used_tool": result.tool,
            "articles": result.articles,
            "nodes": result.nodes,
            "edges": result.edges,
            "highlighted_node_ids": result.highlighted_node_ids,
            "highlighted_edge_ids": result.highlighted_edge_ids,
        }

    def graph(self) -> Dict[str, Any]:
        """초기 화면에 사용할 전체 그래프를 조회한다."""
        graph = self.graph_provider.fetch_graph()
        return {
            "nodes": graph["nodes"],
            "edges": graph["edges"],
        }
