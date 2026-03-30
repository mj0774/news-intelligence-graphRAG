from __future__ import annotations

"""Text2CypherRetriever 래퍼 모듈.

사용자 자연어를 Cypher로 변환해 구조 질의를 수행한다.
카테고리 최신 기사, 통계/집계 질문에 특히 유리하다.
"""

from typing import Any, Dict, List

import neo4j
from neo4j_graphrag.retrievers import Text2CypherRetriever
from neo4j_graphrag.types import RetrieverResultItem

from backend.retriever.common import enrich_articles_from_graph, items_to_articles


class Text2CypherNewsRetriever:
    """자연어 -> Cypher 변환 기반 retriever."""

    def __init__(self, driver: neo4j.Driver, llm: Any) -> None:
        self.driver = driver

        # 스키마 텍스트와 few-shot 예시를 함께 넣어
        # LLM이 올바른 Cypher를 만들도록 유도한다.
        neo4j_schema = self._build_schema_text(driver)
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
RETURN c.name AS category, count(a) AS article_count
ORDER BY article_count DESC
""".strip(),
        ]

        self.retriever = Text2CypherRetriever(
            driver=driver,
            llm=llm,
            neo4j_schema=neo4j_schema,
            examples=examples,
            result_formatter=self._result_formatter,
        )

    @staticmethod
    def _build_schema_text(driver: neo4j.Driver) -> str:
        """DB 메타정보를 읽어 Text2Cypher 입력용 스키마 문자열을 만든다.

        스키마를 동적으로 읽어두면 DB 구조가 약간 바뀌어도
        프롬프트를 하드코딩으로 자주 수정하지 않아도 된다.
        """
        try:
            with driver.session() as session:
                node_rows = session.run(
                    """
                    CALL db.schema.nodeTypeProperties()
                    YIELD nodeType, propertyName, propertyTypes
                    RETURN nodeType, propertyName, propertyTypes
                    ORDER BY nodeType, propertyName
                    """
                ).data()
                rel_rows = session.run(
                    """
                    CALL db.schema.relTypeProperties()
                    YIELD relType, propertyName, propertyTypes
                    RETURN relType, propertyName, propertyTypes
                    ORDER BY relType, propertyName
                    """
                ).data()

            lines: List[str] = ["Node properties:"]
            for row in node_rows:
                ptypes = row.get("propertyTypes") or []
                ptype = ptypes[0] if ptypes else "ANY"
                lines.append(f"{row.get('nodeType')} {{{row.get('propertyName')}: {ptype}}}")

            lines.append("\nRelationship properties:")
            for row in rel_rows:
                ptypes = row.get("propertyTypes") or []
                ptype = ptypes[0] if ptypes else "ANY"
                lines.append(f"{row.get('relType')} {{{row.get('propertyName')}: {ptype}}}")

            return "\n".join(lines)
        except Exception:
            # 스키마 메타 조회 권한/버전 이슈가 있을 때를 대비한 fallback.
            return """
            Node properties:
            Article {article_id: STRING, title: STRING, url: STRING, published_date: STRING}
            Content {content_id: STRING, chunk: STRING, article_id: STRING, chunk_index: INTEGER}
            Media {name: STRING}
            Category {name: STRING}

            Relationships:
            (:Article)-[:HAS_CHUNK]->(:Content)
            (:Media)-[:PUBLISHED]->(:Article)
            (:Article)-[:BELONGS_TO]->(:Category)
            """

    @staticmethod
    def _extract_article_fields(record: neo4j.Record) -> Dict[str, Any]:
        """Text2Cypher 결과 레코드에서 기사 필드를 안전하게 추출한다.

        쿼리마다 반환 alias가 달라질 수 있어서
        `a` 노드 반환 패턴과 개별 필드 반환 패턴을 모두 지원한다.
        """
        article_id = ""
        title = ""
        url = ""
        published_date = ""

        # 1) `RETURN a` 형태
        article_node = record.get("a")
        if article_node is not None:
            props = dict(article_node)
            article_id = str(props.get("article_id", ""))
            title = str(props.get("title", ""))
            url = str(props.get("url", ""))
            published_date = str(props.get("published_date", ""))

        # 2) `RETURN a.article_id AS article_id ...` 형태
        if not article_id:
            article_id = str(record.get("article_id", ""))
            title = str(record.get("title", ""))
            url = str(record.get("url", ""))
            published_date = str(record.get("published_date", ""))

        # 3) 최소 보장 fallback
        if not title:
            title = str(record.get("headline", ""))

        return {
            "article_id": article_id,
            "title": title,
            "url": url,
            "published_date": published_date,
        }

    @classmethod
    def _result_formatter(cls, record: neo4j.Record) -> RetrieverResultItem:
        """레코드를 RetrieverResultItem으로 변환한다."""
        fields = cls._extract_article_fields(record)
        return RetrieverResultItem(
            content=fields.get("title", ""),
            metadata={
                "article_id": fields.get("article_id", ""),
                "title": fields.get("title", ""),
                "url": fields.get("url", ""),
                "published_date": fields.get("published_date", ""),
                "summary": fields.get("title", ""),
                "chunks": [],
            },
        )

    def search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """Text2Cypher 검색 결과를 기사 리스트로 반환한다."""
        result = self.retriever.search(query_text=query)
        articles = items_to_articles(result.items)
        enriched = enrich_articles_from_graph(self.driver, articles)
        return enriched[:top_k]

    def to_tool(self):
        """ToolsRetriever에서 사용할 Tool 객체로 변환한다."""
        return self.retriever.convert_to_tool(
            name="text2cypher_retriever",
            description="카테고리별 기사 수, 특정 카테고리 기사 목록, 통계/집계 등 그래프 구조 기반 쿼리에 사용.",
        )
