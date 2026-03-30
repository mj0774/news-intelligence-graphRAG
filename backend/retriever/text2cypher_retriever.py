from __future__ import annotations

from typing import Any, Dict, List

import neo4j
from neo4j_graphrag.retrievers import Text2CypherRetriever
from neo4j_graphrag.types import RetrieverResultItem

from backend.retriever.common import enrich_articles_from_graph, items_to_articles


class Text2CypherNewsRetriever:
    """자연어를 Cypher로 변환해 구조 질의를 수행하는 retriever."""

    def __init__(self, driver: neo4j.Driver, llm: Any) -> None:
        self.driver = driver

        # 스키마는 고정 문자열 대신 DB에서 동적으로 읽는다.
        neo4j_schema = self._build_schema_text(driver)

        self.retriever = Text2CypherRetriever(
            driver=driver,
            llm=llm,
            neo4j_schema=neo4j_schema,
            # 하드코딩 예시는 제거하고, 스키마 기반 변환에 집중한다.
            examples=[],
            custom_prompt="""
            한국어 질문을 Neo4j Cypher로 변환하세요.
            가능한 경우 Article 정보를 함께 반환하도록 작성하세요.
            반환 컬럼 alias 예시: article_id, title, url, published_date
            """,
            result_formatter=self._result_formatter,
        )

    @staticmethod
    def _build_schema_text(driver: neo4j.Driver) -> str:
        """DB 메타데이터를 조회해 Text2Cypher 입력 스키마 문자열을 만든다."""
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
            # 메타데이터 조회 권한/버전 이슈 시 최소 스키마로 fallback
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
        """Text2Cypher 결과 레코드에서 Article 필드를 유연하게 추출한다."""
        article_id = ""
        title = ""
        url = ""
        published_date = ""

        # 1) a 노드 반환 패턴 (권장)
        article_node = record.get("a")
        if article_node is not None:
            props = dict(article_node)
            article_id = str(props.get("article_id", ""))
            title = str(props.get("title", ""))
            url = str(props.get("url", ""))
            published_date = str(props.get("published_date", ""))

        # 2) alias 반환 패턴
        if not article_id:
            article_id = str(record.get("article_id", ""))
            title = str(record.get("title", ""))
            url = str(record.get("url", ""))
            published_date = str(record.get("published_date", ""))

        # 3) title만 있는 경우도 받아서 최소 응답 보장
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

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        result = self.retriever.search(query_text=query)
        articles = items_to_articles(result.items)
        enriched = enrich_articles_from_graph(self.driver, articles)
        return enriched[:top_k]

    def to_tool(self):
        return self.retriever.convert_to_tool(
            name="text2cypher_retriever",
            description="자연어를 Cypher로 변환해 카테고리/언론사/최신 등 구조 질의를 처리합니다.",
        )
