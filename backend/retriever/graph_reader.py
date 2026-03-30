from __future__ import annotations

from typing import Dict, List

import neo4j

from backend.retriever.common import make_edge_id


class GraphReader:
    """Neo4j에서 시각화용 그래프 데이터를 읽어오는 전용 모듈."""

    def __init__(self, driver: neo4j.Driver) -> None:
        self.driver = driver

    def fetch_graph(self, node_limit: int = 600, edge_limit: int = 1200) -> Dict[str, List[Dict[str, str]]]:
        """Article/Category/Media/Content 서브그래프를 조회한다."""
        nodes_query = """
        MATCH (n)
        WHERE n:Article OR n:Category OR n:Media OR n:Content
        WITH n
        ORDER BY
            CASE
                WHEN n:Article THEN 1
                WHEN n:Category THEN 2
                WHEN n:Media THEN 3
                ELSE 4
            END,
            coalesce(n.title, n.name, n.chunk, '')
        LIMIT $node_limit
        RETURN n
        """

        edges_query = """
        MATCH (a)-[r]->(b)
        WHERE
            (a:Article OR a:Category OR a:Media OR a:Content)
            AND (b:Article OR b:Category OR b:Media OR b:Content)
            AND type(r) IN ['HAS_CHUNK', 'BELONGS_TO', 'PUBLISHED']
        LIMIT $edge_limit
        RETURN a, r, b
        """

        with self.driver.session() as session:
            # .data()를 사용하면 Node 객체가 속성 dict로 평탄화되어 labels를 잃는다.
            # 레코드 객체를 그대로 순회해 labels/type 메타데이터를 유지한다.
            node_records = list(session.run(nodes_query, node_limit=node_limit))
            edge_records = list(session.run(edges_query, edge_limit=edge_limit))

        nodes: List[Dict[str, str]] = []
        edges: List[Dict[str, str]] = []

        seen_nodes = set()
        for record in node_records:
            node = record["n"]
            label_set = set(node.labels)

            if "Article" in label_set:
                node_id = f"ARTICLE_{node.get('article_id') or node.get('title', '')}"
                label = str(node.get("title", "제목 없음"))
                node_type = "Article"
            elif "Category" in label_set:
                node_id = f"CATEGORY_{node.get('name', '')}"
                label = str(node.get("name", "미분류"))
                node_type = "Category"
            elif "Media" in label_set:
                node_id = f"MEDIA_{node.get('name', '')}"
                label = str(node.get("name", "출처미상"))
                node_type = "Media"
            else:
                article_id = str(node.get("article_id", ""))
                chunk_idx = str(node.get("chunk_index", "0"))
                node_id = f"CONTENT_{article_id}_{chunk_idx}"
                preview = str(node.get("chunk", ""))
                label = preview[:42] + "..." if len(preview) > 42 else preview
                node_type = "Content"

            if node_id in seen_nodes:
                continue

            seen_nodes.add(node_id)
            nodes.append({"id": node_id, "label": label, "type": node_type})

        seen_edges = set()
        for record in edge_records:
            rel_type = record["r"].type
            source_node = record["a"]
            target_node = record["b"]

            source_id = self._node_to_id(source_node)
            target_id = self._node_to_id(target_node)

            if source_id not in seen_nodes or target_id not in seen_nodes:
                continue

            edge_id = make_edge_id(source_id, target_id, rel_type)
            if edge_id in seen_edges:
                continue

            seen_edges.add(edge_id)
            edges.append(
                {
                    "id": edge_id,
                    "source": source_id,
                    "target": target_id,
                    "type": rel_type,
                }
            )

        return {"nodes": nodes, "edges": edges}

    @staticmethod
    def _node_to_id(node: neo4j.graph.Node) -> str:
        label_set = set(node.labels)
        if "Article" in label_set:
            return f"ARTICLE_{node.get('article_id') or node.get('title', '')}"
        if "Category" in label_set:
            return f"CATEGORY_{node.get('name', '')}"
        if "Media" in label_set:
            return f"MEDIA_{node.get('name', '')}"

        article_id = str(node.get("article_id", ""))
        chunk_idx = str(node.get("chunk_index", "0"))
        return f"CONTENT_{article_id}_{chunk_idx}"
