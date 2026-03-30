from __future__ import annotations

"""Retriever 공통 유틸 모듈.

역할:
- 기사 목록을 그래프 시각화 노드/엣지로 변환
- retriever item 결과를 통일된 기사 스키마로 정규화
- Neo4j에서 category/source/chunk를 보강 조회
"""

from typing import Any, Dict, List

import neo4j


def make_edge_id(source: str, target: str, rel_type: str) -> str:
    """엣지 고유 ID를 생성한다.

    프론트에서 엣지 중복 렌더링을 방지하려면
    관계의 방향(source -> target)과 타입까지 포함된 키가 필요하다.
    """
    return f"{source}|{rel_type}|{target}"


def build_graph_from_articles(articles: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, str]]]:
    """기사 리스트를 프론트 시각화용 그래프 구조로 변환한다.

    설계 포인트:
    - Article/Category/Media/Content 노드 생성
    - 중복 노드/엣지 제거
    - Content는 기사당 최대 3개만 표시(가독성/성능 균형)
    """
    nodes: List[Dict[str, str]] = []
    edges: List[Dict[str, str]] = []

    seen_nodes = set()
    seen_edges = set()

    def add_node(node_id: str, label: str, node_type: str) -> None:
        """중복 없이 노드를 추가한다."""
        if node_id in seen_nodes:
            return
        seen_nodes.add(node_id)
        nodes.append({"id": node_id, "label": label, "type": node_type})

    def add_edge(source: str, target: str, rel_type: str) -> None:
        """중복 없이 엣지를 추가한다."""
        edge_id = make_edge_id(source, target, rel_type)
        if edge_id in seen_edges:
            return
        seen_edges.add(edge_id)
        edges.append(
            {
                "id": edge_id,
                "source": source,
                "target": target,
                "type": rel_type,
            }
        )

    for article in articles:
        article_id = str(article.get("article_id", ""))
        title = str(article.get("title", "제목 없음"))
        category = str(article.get("category", "미분류"))
        source = str(article.get("source", "출처미상"))

        # article_id가 비어도 노드가 깨지지 않게 제목 기반 fallback 키를 사용한다.
        article_node = f"ARTICLE_{article_id or title}"
        category_node = f"CATEGORY_{category}"
        media_node = f"MEDIA_{source}"

        add_node(article_node, title, "Article")
        add_node(category_node, category, "Category")
        add_node(media_node, source, "Media")

        add_edge(article_node, category_node, "BELONGS_TO")
        add_edge(media_node, article_node, "PUBLISHED")

        # Content 노드는 양이 많아 과밀해지기 쉬우므로 최대 3개만 시각화한다.
        chunks = article.get("chunks", []) or []
        for idx, chunk in enumerate(chunks[:3], start=1):
            content_node = f"CONTENT_{article_id or title}_{idx}"
            chunk_preview = str(chunk)
            if len(chunk_preview) > 42:
                chunk_preview = chunk_preview[:42] + "..."
            add_node(content_node, chunk_preview, "Content")
            add_edge(article_node, content_node, "HAS_CHUNK")

    return {
        "nodes": nodes,
        "edges": edges,
        # 검색 결과 그래프는 생성된 요소 전체를 하이라이트 대상으로 제공한다.
        "highlighted_node_ids": [node["id"] for node in nodes],
        "highlighted_edge_ids": [edge["id"] for edge in edges],
    }


def safe_article(record: Dict[str, Any]) -> Dict[str, Any]:
    """기사 딕셔너리를 API 표준 스키마로 정리한다.

    누락 키를 빈 문자열/기본값으로 채워
    프론트 렌더링 단계의 KeyError를 예방한다.
    """
    return {
        "article_id": str(record.get("article_id", "")),
        "title": str(record.get("title", "")),
        "url": str(record.get("url", "")),
        "published_date": str(record.get("published_date", "")),
        "category": str(record.get("category", "")),
        "source": str(record.get("source", "")),
        "summary": str(record.get("summary", "")),
        "chunks": record.get("chunks", []) or [],
    }


def items_to_articles(items: List[Any]) -> List[Dict[str, Any]]:
    """RetrieverResultItem 리스트를 기사 리스트로 변환한다."""
    articles: List[Dict[str, Any]] = []
    seen = set()

    for item in items:
        metadata = getattr(item, "metadata", None) or {}
        content = getattr(item, "content", "") or ""

        article = safe_article(
            {
                "article_id": metadata.get("article_id", ""),
                "title": metadata.get("title", ""),
                "url": metadata.get("url", ""),
                "published_date": metadata.get("published_date", ""),
                "category": metadata.get("category", ""),
                "source": metadata.get("source", ""),
                "summary": metadata.get("summary", content),
                "chunks": metadata.get("chunks", [content] if content else []),
            }
        )

        # 동일 기사 중복 제거 키: article_id 우선, 없으면 url/title 순 fallback.
        dedup_key = article["article_id"] or article["url"] or article["title"]
        if not dedup_key or dedup_key in seen:
            continue

        seen.add(dedup_key)
        articles.append(article)

    return articles


def enrich_articles_from_graph(driver: neo4j.Driver, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Neo4j 그래프 정보로 기사 메타데이터를 보강한다.

    retriever 결과에는 category/source/chunks가 부족할 수 있으므로,
    article_id를 기준으로 그래프에서 재조회해 응답 품질을 높인다.
    """
    article_ids = [a.get("article_id", "") for a in articles if a.get("article_id", "")]
    if not article_ids:
        return articles

    cypher = """
    UNWIND $article_ids AS article_id
    MATCH (a:Article {article_id: article_id})
    OPTIONAL MATCH (a)-[:BELONGS_TO]->(cat:Category)
    OPTIONAL MATCH (m:Media)-[:PUBLISHED]->(a)
    OPTIONAL MATCH (a)-[:HAS_CHUNK]->(c:Content)
    RETURN
        a.article_id AS article_id,
        coalesce(a.title, '') AS title,
        coalesce(a.url, '') AS url,
        coalesce(a.published_date, '') AS published_date,
        coalesce(cat.name, '') AS category,
        coalesce(m.name, '') AS source,
        collect(c.chunk)[0..3] AS chunks
    """

    with driver.session() as session:
        rows = session.run(cypher, article_ids=article_ids).data()

    by_id = {str(r.get("article_id", "")): r for r in rows}

    enriched: List[Dict[str, Any]] = []
    for article in articles:
        aid = str(article.get("article_id", ""))
        graph_data = by_id.get(aid)
        if not graph_data:
            enriched.append(article)
            continue

        chunks = graph_data.get("chunks", []) or article.get("chunks", [])
        summary = article.get("summary", "")
        if not summary and chunks:
            summary = str(chunks[0])[:260]

        merged = safe_article(
            {
                "article_id": aid,
                "title": graph_data.get("title", article.get("title", "")),
                "url": graph_data.get("url", article.get("url", "")),
                "published_date": graph_data.get("published_date", article.get("published_date", "")),
                "category": graph_data.get("category", article.get("category", "")),
                "source": graph_data.get("source", article.get("source", "")),
                "summary": summary,
                "chunks": chunks,
            }
        )
        enriched.append(merged)

    return enriched
