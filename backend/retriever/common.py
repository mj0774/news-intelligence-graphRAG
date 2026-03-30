from __future__ import annotations

from typing import Any, Dict, List

import neo4j


def make_edge_id(source: str, target: str, rel_type: str) -> str:
    """엣지를 프론트에서 식별할 수 있도록 고유 ID를 만든다."""
    return f"{source}|{rel_type}|{target}"


def build_graph_from_articles(articles: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, str]]]:
    """기사 리스트를 프론트 시각화용 노드/엣지 구조로 변환한다."""
    nodes: List[Dict[str, str]] = []
    edges: List[Dict[str, str]] = []

    seen_nodes = set()
    seen_edges = set()

    def add_node(node_id: str, label: str, node_type: str) -> None:
        if node_id in seen_nodes:
            return
        seen_nodes.add(node_id)
        nodes.append({"id": node_id, "label": label, "type": node_type})

    def add_edge(source: str, target: str, rel_type: str) -> None:
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

        # 기사 고유키가 비어도 UI 노드가 깨지지 않게 title 기반 fallback을 둔다.
        article_node = f"ARTICLE_{article_id or title}"
        category_node = f"CATEGORY_{category}"
        media_node = f"MEDIA_{source}"

        add_node(article_node, title, "Article")
        add_node(category_node, category, "Category")
        add_node(media_node, source, "Media")

        add_edge(article_node, category_node, "BELONGS_TO")
        add_edge(media_node, article_node, "PUBLISHED")

        # Content 노드는 너무 많으면 시각화가 난잡해져 기사당 최대 3개만 노출한다.
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
        "highlighted_node_ids": [node["id"] for node in nodes],
        "highlighted_edge_ids": [edge["id"] for edge in edges],
    }


def safe_article(record: Dict[str, Any]) -> Dict[str, Any]:
    """레코드를 API 응답 스키마에 맞는 기사 딕셔너리로 정규화한다."""
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
    """RetrieverResultItem 목록을 기사 리스트로 변환한다."""
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

        dedup_key = article["article_id"] or article["url"] or article["title"]
        if not dedup_key or dedup_key in seen:
            continue

        seen.add(dedup_key)
        articles.append(article)

    return articles


def enrich_articles_from_graph(driver: neo4j.Driver, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """article_id를 기준으로 그래프의 category/source/chunks를 보강한다."""
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
