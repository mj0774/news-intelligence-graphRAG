from __future__ import annotations

"""API 요청/응답 스키마 정의 모듈.

Pydantic 모델을 통해 입력값 검증과 응답 형태 고정을 수행한다.
프론트는 이 스키마를 기준으로 안정적으로 렌더링할 수 있다.
"""

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    """검색 API 요청 바디 모델."""

    # 최소 1글자 이상 입력을 강제해 빈 질의를 차단한다.
    query: str = Field(..., min_length=1, description="사용자 질의")


class ArticleItem(BaseModel):
    """검색 결과의 기사 단위 표시 모델."""

    article_id: str
    title: str
    url: str
    published_date: str
    category: str
    source: str
    summary: str


class GraphNode(BaseModel):
    """시각화용 그래프 노드 모델."""

    id: str
    label: str
    type: str
    title: str = ""
    properties: Dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    """시각화용 그래프 엣지 모델."""

    id: str
    source: str
    target: str
    type: str


class GraphResponse(BaseModel):
    """전체 그래프 조회 응답 모델."""

    nodes: List[GraphNode]
    edges: List[GraphEdge]


class SearchResponse(BaseModel):
    """검색 응답 모델.

    프론트 요구사항에 맞춰,
    - 텍스트 답변
    - 사용된 검색 도구
    - 기사 목록
    - 하이라이트 대상 그래프 요소
    를 한 번에 반환한다.
    """

    answer: str
    used_tool: str
    articles: List[ArticleItem]
    nodes: List[GraphNode]
    edges: List[GraphEdge]
    highlighted_node_ids: List[str]
    highlighted_edge_ids: List[str]
