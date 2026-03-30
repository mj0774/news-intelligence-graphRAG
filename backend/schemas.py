from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    """검색 API 요청 모델."""

    query: str = Field(..., min_length=1, description="사용자 질의")


class ArticleItem(BaseModel):
    """프론트에 전달할 기사 요약 모델."""

    article_id: str
    title: str
    url: str
    published_date: str
    category: str
    source: str
    summary: str


class GraphNode(BaseModel):
    """그래프 시각화용 노드 모델."""

    id: str
    label: str
    type: str


class GraphEdge(BaseModel):
    """그래프 시각화용 엣지 모델."""

    source: str
    target: str
    type: str


class SearchResponse(BaseModel):
    """검색 API 응답 모델."""

    answer: str
    used_tool: str
    articles: List[ArticleItem]
    nodes: List[GraphNode]
    edges: List[GraphEdge]
