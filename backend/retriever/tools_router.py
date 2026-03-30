from __future__ import annotations

"""ToolsRetriever 기반 검색 라우터.

핵심 아이디어:
- 질의 의도에 따라 3개 retriever 도구 중 하나를 LLM이 선택
  1) vector_retriever
  2) vectorcypher_retriever
  3) text2cypher_retriever
- 선택 결과를 후처리해 기사 목록/그래프 하이라이트 정보로 변환
"""

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

import neo4j
from neo4j_graphrag.generation import GraphRAG, RagTemplate
from neo4j_graphrag.retrievers import (
    Text2CypherRetriever,
    ToolsRetriever,
    VectorCypherRetriever,
    VectorRetriever,
)

from backend.retriever.common import build_graph_from_articles


@dataclass
class ToolSearchResult:
    """ToolsRouter 검색 결과 DTO."""

    tool: str
    answer: str
    articles: List[Dict[str, Any]]
    nodes: List[Dict[str, str]]
    edges: List[Dict[str, str]]
    highlighted_node_ids: List[str]
    highlighted_edge_ids: List[str]


class ToolsRouter:
    """ToolsRetriever 기반 검색 라우터 구현체."""

    INDEX_NAME = "content_vector_index"

    def __init__(self, driver: neo4j.Driver, llm: Any, embedder: Any) -> None:
        self.driver = driver
        self.llm = llm
        self.embedder = embedder

        # ------------------------------------------------------------------
        # 1) 개별 retriever 구성
        # ------------------------------------------------------------------
        self.vector_retriever = VectorRetriever(
            driver=driver,
            index_name=self.INDEX_NAME,
            embedder=embedder,
        )

        retrieval_query = """
        WITH node AS content, score
        MATCH (content)<-[:HAS_CHUNK]-(article:Article)
        OPTIONAL MATCH (article)-[:BELONGS_TO]->(category:Category)
        OPTIONAL MATCH (category)<-[:BELONGS_TO]-(related_article:Article)
        WHERE related_article <> article

        RETURN
            content.content_id AS content_id,
            content.chunk AS chunk,
            content.title AS content_title,
            article.article_id AS article_id,
            article.title AS article_title,
            article.url AS article_url,
            article.published_date AS article_date,
            category.name AS category_name,
            score AS similarity_score,
            collect(DISTINCT {
                article_id: related_article.article_id,
                title: related_article.title,
                url: related_article.url,
                published_date: related_article.published_date
            })[0..5] AS related_articles
        """

        self.vector_cypher_retriever = VectorCypherRetriever(
            driver=driver,
            index_name=self.INDEX_NAME,
            retrieval_query=retrieval_query,
            embedder=embedder,
        )

        neo4j_schema = self._get_neo4j_schema()
        examples = [
            """
USER INPUT: 경제 분야의 최신 뉴스 알려주세요
CYPHER QUERY:
MATCH (a:Article)-[:BELONGS_TO]->(c:Category {name: "경제"})
RETURN a.article_id, a.title, a.url, a.published_date
ORDER BY a.published_date DESC
LIMIT 10
""".strip(),
            """
USER INPUT: 정치 카테고리의 최신 기사 5개를 보여주세요
CYPHER QUERY:
MATCH (a:Article)-[:BELONGS_TO]->(c:Category {name: "정치"})
RETURN a.article_id, a.title, a.url, a.published_date
ORDER BY a.published_date DESC
LIMIT 5
""".strip(),
            """
USER INPUT: 카테고리별 기사 개수를 알려주세요
CYPHER QUERY:
MATCH (a:Article)-[:BELONGS_TO]->(c:Category)
RETURN c.name as category, count(a) as article_count
ORDER BY article_count DESC
""".strip(),
        ]

        self.text2cypher_retriever = Text2CypherRetriever(
            driver=driver,
            llm=llm,
            neo4j_schema=neo4j_schema,
            examples=examples,
        )

        # ------------------------------------------------------------------
        # 2) ToolsRetriever 구성
        # ------------------------------------------------------------------
        vector_tool = self.vector_retriever.convert_to_tool(
            name="vector_retriever",
            description="키워드나 개념으로 유사한 기사를 빠르게 찾을 때 사용. 단순 검색용.",
        )
        vector_cypher_tool = self.vector_cypher_retriever.convert_to_tool(
            name="vectorcypher_retriever",
            description="기사의 상세 정보/전체 정보/본문을 요청할 때 사용. 제목, URL, 날짜, 카테고리, 관련 기사까지 반환.",
        )
        text2cypher_tool = self.text2cypher_retriever.convert_to_tool(
            name="text2cypher_retriever",
            description="카테고리별 기사 수, 특정 카테고리 기사 목록, 통계/집계 등 그래프 구조 기반 질의에 사용.",
        )

        self.tools_retriever = ToolsRetriever(
            driver=driver,
            llm=llm,
            tools=[vector_tool, vector_cypher_tool, text2cypher_tool],
        )

        # ------------------------------------------------------------------
        # 3) GraphRAG 답변 템플릿 구성
        # ------------------------------------------------------------------
        prompt_template = RagTemplate(
            template="""당신은 뉴스 기사 정보를 제공하는 전문 어시스턴트입니다.

질문: {query_text}

검색된 문서 정보:
{context}

지침:
1. 사용자의 질문에 직접적으로 답변하세요.
2. **검색된 모든 기사**를 빠짐없이 답변에 포함하세요. 일부만 선택하지 마세요.
3. 먼저 검색된 기사들을 종합 분석한 답변을 제공하세요.
4. 답변 마지막에 출처(기사 목록)를 정리하세요.
5. 각 기사의 제목(title), URL(url), 발행일(published_date)을 모두 포함하세요.
6. 검색 결과에 없는 내용은 추측하지 마세요.

기사 목록 답변 형식:

**검색된 기사 목록 (총 N건):**
1. **[기사 제목]** (발행일)
   - URL: [기사 URL]
   - 핵심: [한 줄 요약]

2. **[기사 제목]** (발행일)
   - URL: [기사 URL]
   - 핵심: [한 줄 요약]

답변:""",
            expected_inputs=["context", "query_text"],
        )

        self.graphrag = GraphRAG(
            llm=llm,
            retriever=self.tools_retriever,
            prompt_template=prompt_template,
        )

    def search(self, query: str, top_k: int = 10) -> ToolSearchResult:
        """질의를 실행하고 프론트 렌더링용 결과를 조립한다.

        처리 단계:
        1) GraphRAG 검색 실행
        2) retriever_result 아이템에서 tool/노드/엣지 힌트 추출
        3) article_id 집합으로 실제 기사 메타데이터 재조회
        4) 기사 기반 서브그래프 생성
        """
        result = self.graphrag.search(query_text=query, return_context=True)

        used_nodes: List[str] = []
        used_edges: List[str] = []
        retriever_used = "unknown"
        article_ids: List[str] = []

        retriever_result = getattr(result, "retriever_result", None)
        if retriever_result and hasattr(retriever_result, "items") and retriever_result.items:
            for item in retriever_result.items:
                metadata = getattr(item, "metadata", {}) or {}

                # 실제 사용 retriever 이름 추출
                if "tool" in metadata:
                    retriever_used = str(metadata["tool"])
                elif "retriever_name" in metadata:
                    retriever_used = str(metadata["retriever_name"])

                # VectorRetriever는 score 기반으로 Content node를 필터링해 하이라이트한다.
                if "id" in metadata and "nodeLabels" in metadata:
                    node_labels = metadata.get("nodeLabels") or []
                    score = metadata.get("score", 1.0)
                    node_id = metadata.get("id")
                    if "Content" in node_labels and score >= 0.7 and node_id:
                        used_nodes.append(f"ElementId_{node_id}")
                        used_edges.append("HAS_CHUNK")

                # item.content에서 article/category/content 힌트를 파싱한다.
                content = str(getattr(item, "content", "") or "")
                if content:
                    if retriever_used == "vectorcypher_retriever":
                        nodes, edges, aids = self._extract_vectorcypher_nodes(content)
                    else:
                        nodes, edges, aids = self._extract_nodes_from_content(content)
                    used_nodes.extend(nodes)
                    used_edges.extend(edges)
                    article_ids.extend(aids)

            # Text2Cypher에서 카테고리 노드가 안 잡힌 경우 질의 텍스트로 보강
            if retriever_used == "text2cypher_retriever" and not any("Category_" in n for n in used_nodes):
                for cat in ["정치", "경제", "사회", "생활/문화", "스포츠", "IT/과학", "세계"]:
                    if cat in query:
                        used_nodes.append(f"Category_{cat}")
                        used_edges.append("BELONGS_TO")
                        break

        used_nodes = list(set(used_nodes))
        used_edges = list(set(used_edges))
        article_ids = list(set(article_ids))

        # 파싱된 article_id를 기준으로 실제 기사 정보를 조회한다.
        articles = self._fetch_articles_by_ids(article_ids, top_k=top_k)
        graph = build_graph_from_articles(articles)

        answer = getattr(result, "answer", "") if hasattr(result, "answer") else str(result)
        answer = str(answer)

        return ToolSearchResult(
            tool=retriever_used,
            answer=answer,
            articles=articles,
            nodes=graph["nodes"],
            edges=graph["edges"],
            highlighted_node_ids=graph["highlighted_node_ids"],
            highlighted_edge_ids=graph["highlighted_edge_ids"],
        )

    def _fetch_articles_by_ids(self, article_ids: List[str], top_k: int = 10) -> List[Dict[str, Any]]:
        """article_id 목록으로 Article/Category/Media/Content 정보를 조회한다."""
        if not article_ids:
            return []

        cypher = """
        UNWIND $article_ids AS article_id
        MATCH (a:Article {article_id: article_id})
        OPTIONAL MATCH (a)-[:BELONGS_TO]->(c:Category)
        OPTIONAL MATCH (m:Media)-[:PUBLISHED]->(a)
        OPTIONAL MATCH (a)-[:HAS_CHUNK]->(chunk:Content)
        RETURN
            a.article_id AS article_id,
            a.title AS title,
            a.url AS url,
            a.published_date AS published_date,
            coalesce(c.name, '') AS category,
            coalesce(m.name, '') AS source,
            collect(chunk.chunk)[0..3] AS chunks
        ORDER BY a.published_date DESC
        LIMIT $top_k
        """

        with self.driver.session() as session:
            rows = session.run(cypher, article_ids=article_ids, top_k=top_k).data()

        articles: List[Dict[str, Any]] = []
        for row in rows:
            chunks = row.get("chunks", []) or []
            summary = str(chunks[0])[:260] if chunks else ""
            articles.append(
                {
                    "article_id": str(row.get("article_id", "")),
                    "title": str(row.get("title", "")),
                    "url": str(row.get("url", "")),
                    "published_date": str(row.get("published_date", "")),
                    "category": str(row.get("category", "")),
                    "source": str(row.get("source", "")),
                    "summary": summary,
                    "chunks": chunks,
                }
            )

        return articles

    def _get_neo4j_schema(self) -> str:
        """Text2Cypher 입력용 스키마 문자열을 생성한다."""
        with self.driver.session() as session:
            node_info = session.run(
                """
                CALL db.schema.nodeTypeProperties()
                YIELD nodeType, propertyName, propertyTypes
                RETURN nodeType, collect(propertyName) AS properties
                """
            ).data()

            patterns = session.run(
                """
                MATCH (n)-[r]->(m)
                RETURN DISTINCT labels(n)[0] AS source, type(r) AS relationship, labels(m)[0] AS target
                LIMIT 20
                """
            ).data()

        schema_text = "=== Neo4j Schema ===\n\n노드 타입:\n"
        for node in node_info:
            schema_text += f"- {node['nodeType']}: {node['properties']}\n"

        schema_text += "\n관계 패턴:\n"
        for pattern in patterns:
            schema_text += f"- ({pattern['source']})-[:{pattern['relationship']}]->({pattern['target']})\n"

        return schema_text

    @staticmethod
    def _extract_all_field_values(text: str, field_name: str) -> List[str]:
        """텍스트 블록에서 특정 필드값을 최대한 폭넓게 추출한다.

        지원 패턴:
        - field='value'
        - 'field': 'value'
        - article/content id 전용 정규식
        """
        values: List[str] = []
        pattern1 = rf"['\"]?{field_name}['\"]?\s*=\s*['\"]([^'\"]+)['\"]"
        values.extend(re.findall(pattern1, text))

        pattern2 = rf"['\"]?{field_name}['\"]?\s*:\s*['\"]([^'\"]+)['\"]"
        values.extend(re.findall(pattern2, text))

        if field_name == "article_id":
            values.extend(re.findall(r"(ART_\d{3}_\d{10})", text))
        if field_name == "content_id":
            values.extend(re.findall(r"(ART_\d{3}_\d{10}_chunk_\d+)", text))

        return list(set(values))

    @staticmethod
    def _is_valid_article_id(article_id: str) -> bool:
        """article_id 형식 유효성 검사."""
        return bool(re.match(r"^ART_\d{3}_\d{10}$", article_id))

    @staticmethod
    def _is_valid_category(category: str) -> bool:
        """카테고리 문자열 유효성 검사."""
        invalid_values = [
            "Unknown",
            "No title",
            "text2cypher_retriever",
            "vector_retriever",
            "vectorcypher_retriever",
        ]
        if category in invalid_values:
            return False
        if "retriever" in category.lower():
            return False
        return len(category) > 0

    def _extract_nodes_from_content(self, content: str) -> Tuple[List[str], List[str], List[str]]:
        """일반 content 문자열에서 노드/엣지/기사ID 힌트를 추출한다."""
        nodes: List[str] = []
        edges: List[str] = []
        article_ids: List[str] = []

        aids = self._extract_all_field_values(content, "article_id")
        for article_id in aids:
            if article_id and self._is_valid_article_id(article_id):
                nodes.append(f"Article_{article_id}")
                article_ids.append(article_id)

        categories = self._extract_all_field_values(content, "category_name")
        for category in categories:
            if self._is_valid_category(category):
                nodes.append(f"Category_{category}")

        content_ids = self._extract_all_field_values(content, "content_id")
        for content_id in content_ids:
            if content_id:
                nodes.append(f"Content_{content_id}")

        if aids and categories:
            edges.append("BELONGS_TO")
        if aids and content_ids:
            edges.append("HAS_CHUNK")

        return list(set(nodes)), list(set(edges)), list(set(article_ids))

    def _extract_vectorcypher_nodes(self, content: str) -> Tuple[List[str], List[str], List[str]]:
        """VectorCypher 결과 문자열에서 핵심 노드/엣지/기사ID를 추출한다."""
        nodes: List[str] = []
        edges: List[str] = []
        article_ids: List[str] = []

        # related_articles 영역은 보조 정보라 핵심 기사 파싱에서 제외한다.
        related_idx = content.find("related_articles")
        main_content = content[:related_idx] if related_idx > 0 else content

        content_id_match = re.search(r"content_id=\\?['\"]?(ART_\d{3}_\d{10}_chunk_\d+)", main_content)
        if content_id_match:
            content_id = content_id_match.group(1)
            nodes.append(f"Content_{content_id}")

            article_id = re.sub(r"_chunk_\d+$", "", content_id)
            if self._is_valid_article_id(article_id):
                nodes.append(f"Article_{article_id}")
                article_ids.append(article_id)
                edges.append("HAS_CHUNK")

        if not any("Article_" in n for n in nodes):
            article_match = re.search(r"article_id=\\?['\"]?(ART_\d{3}_\d{10})", main_content)
            if article_match:
                article_id = article_match.group(1)
                if self._is_valid_article_id(article_id):
                    nodes.append(f"Article_{article_id}")
                    article_ids.append(article_id)

        category_match = re.search(r"category_name=\\?['\"]?([가-힣/]+)", main_content)
        if category_match:
            category = category_match.group(1).strip()
            if self._is_valid_category(category):
                nodes.append(f"Category_{category}")
                edges.append("BELONGS_TO")

        return list(set(nodes)), list(set(edges)), list(set(article_ids))

