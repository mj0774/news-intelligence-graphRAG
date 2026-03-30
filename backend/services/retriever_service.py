from __future__ import annotations

from typing import Any, Dict, Protocol


class SearchRouter(Protocol):
    """RetrieverService가 의존하는 라우터 인터페이스."""

    def search(self, query: str, top_k: int = 5):
        ...


class RetrieverService:
    """API 레이어에서 사용하는 검색 서비스.

    서비스는 의존성(라우터)을 생성하지 않고 주입받아 사용한다.
    즉, 설정/인프라 생성 책임은 container 계층에 있다.
    """

    def __init__(self, router: SearchRouter) -> None:
        self.router = router

    def search(self, query: str) -> Dict[str, Any]:
        """질의를 라우팅해 검색하고 API 응답 페이로드를 만든다."""
        result = self.router.search(query=query, top_k=5)

        return {
            "answer": result.answer,
            "used_tool": result.tool,
            "articles": result.articles,
            "nodes": result.nodes,
            "edges": result.edges,
        }
