from __future__ import annotations

from typing import Any, Dict, Protocol


class SearchRouter(Protocol):
    """RetrieverService가 의존하는 검색 라우터 인터페이스."""

    def search(self, query: str, top_k: int = 5):
        ...


class GraphProvider(Protocol):
    """RetrieverService가 의존하는 그래프 조회 인터페이스."""

    def fetch_graph(self, node_limit: int = 600, edge_limit: int = 1200):
        ...


class RetrieverService:
    """API 레이어에서 사용하는 검색/그래프 서비스."""

    def __init__(self, router: SearchRouter, graph_provider: GraphProvider) -> None:
        self.router = router
        self.graph_provider = graph_provider

    def search(self, query: str) -> Dict[str, Any]:
        """질의를 라우팅해 검색하고 API 응답 페이로드를 만든다."""
        result = self.router.search(query=query, top_k=5)

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
        """시각화용 전체 그래프를 조회한다."""
        graph = self.graph_provider.fetch_graph()
        return {
            "nodes": graph["nodes"],
            "edges": graph["edges"],
        }
