"""뉴스 엑셀 데이터를 Neo4j 그래프로 적재하는 빌더.

흐름:
1) data/ 폴더에서 엑셀 파일 로드(기본: 최신 파일)
2) Neo4j 연결
3) 텍스트 청킹
4) Article/Content/Media/Category 노드 및 관계 생성
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any, Dict, List

import neo4j
import pandas as pd
from dotenv import load_dotenv

# 프로젝트 루트의 수집 결과 저장 폴더
DATA_DIR = Path("data")

# 청킹 기본값(참고 구현과 동일)
DEFAULT_CHUNK_SIZE = 500
DEFAULT_OVERLAP = 50


def find_latest_excel(data_dir: Path) -> Path:
    """data 폴더에서 가장 최근에 생성된 엑셀 파일을 반환한다."""
    files = sorted(data_dir.glob("*.xlsx"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        raise FileNotFoundError(f"엑셀 파일이 없습니다: {data_dir}")
    return files[0]


def chunk_text(text: Any, chunk_size: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_OVERLAP) -> List[str]:
    """본문 텍스트를 겹침(overlap)을 두고 청킹한다."""
    if pd.isna(text) or text == "":
        return []

    text = str(text)
    chunks: List[str] = []

    # chunk_size-overlap 단위로 이동하면서 문맥이 이어지도록 일부를 겹친다.
    for i in range(0, len(text), chunk_size - overlap):
        chunk = text[i : i + chunk_size]
        if chunk.strip():
            chunks.append(chunk.strip())

    return chunks


def clear_database(tx: neo4j.Transaction) -> None:
    """그래프의 모든 노드/관계를 삭제한다."""
    tx.run("MATCH (n) DETACH DELETE n")


def create_constraints(tx: neo4j.Transaction) -> None:
    """중복 삽입 방지를 위한 유니크 제약조건을 생성한다."""
    constraints = [
        "CREATE CONSTRAINT IF NOT EXISTS FOR (a:Article) REQUIRE a.article_id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Content) REQUIRE c.content_id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (m:Media) REQUIRE m.name IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (cat:Category) REQUIRE cat.name IS UNIQUE",
    ]

    for constraint in constraints:
        try:
            tx.run(constraint)
        except Exception as exc:
            print(f"제약조건 생성 중 오류: {exc}")


def create_article_node(tx: neo4j.Transaction, article_data: Dict[str, str]) -> None:
    """Article 노드를 생성(또는 업데이트)한다."""
    query = """
    MERGE (a:Article {article_id: $article_id})
    SET a.title = $title,
        a.url = $url,
        a.published_date = $published_date
    RETURN a
    """
    tx.run(
        query,
        article_id=article_data["article_id"],
        title=article_data["title"],
        url=article_data["url"],
        published_date=article_data["published_date"],
    )


def create_content_nodes(
    tx: neo4j.Transaction,
    article_id: str,
    content_chunks: List[str],
    article_data: Dict[str, str],
) -> None:
    """Content 청크 노드와 HAS_CHUNK 관계를 생성한다."""
    for i, chunk in enumerate(content_chunks):
        # 같은 기사 내 청크 순번으로 content_id를 고정한다.
        content_id = f"{article_id}_chunk_{i}"

        query = """
        MERGE (c:Content {content_id: $content_id})
        SET c.chunk = $chunk,
            c.article_id = $article_id,
            c.title = $title,
            c.url = $url,
            c.published_date = $published_date,
            c.chunk_index = $chunk_index
        """
        tx.run(
            query,
            content_id=content_id,
            chunk=chunk,
            article_id=article_id,
            title=article_data["title"],
            url=article_data["url"],
            published_date=article_data["published_date"],
            chunk_index=i,
        )

        relationship_query = """
        MATCH (a:Article {article_id: $article_id})
        MATCH (c:Content {content_id: $content_id})
        MERGE (a)-[:HAS_CHUNK]->(c)
        """
        tx.run(relationship_query, article_id=article_id, content_id=content_id)


def create_media_node_and_relationship(tx: neo4j.Transaction, article_id: str, source: Any) -> None:
    """Media 노드와 PUBLISHED 관계를 생성한다."""
    if pd.isna(source) or source == "":
        return

    media_query = """
    MERGE (m:Media {name: $source})
    RETURN m
    """
    tx.run(media_query, source=source)

    relationship_query = """
    MATCH (a:Article {article_id: $article_id})
    MATCH (m:Media {name: $source})
    MERGE (m)-[:PUBLISHED]->(a)
    """
    tx.run(relationship_query, article_id=article_id, source=source)


def create_category_node_and_relationship(tx: neo4j.Transaction, article_id: str, category: Any) -> None:
    """Category 노드와 BELONGS_TO 관계를 생성한다."""
    if pd.isna(category) or category == "":
        return

    category_query = """
    MERGE (cat:Category {name: $category})
    RETURN cat
    """
    tx.run(category_query, category=category)

    relationship_query = """
    MATCH (a:Article {article_id: $article_id})
    MATCH (cat:Category {name: $category})
    MERGE (a)-[:BELONGS_TO]->(cat)
    """
    tx.run(relationship_query, article_id=article_id, category=category)


def build_graph_from_dataframe(
    driver: neo4j.Driver,
    df: pd.DataFrame,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> None:
    """DataFrame 한 줄씩 순회하며 그래프를 구축한다."""
    with driver.session() as session:
        for idx, row in df.iterrows():
            try:
                article_id = row.get("article_id", "")

                # Article 노드에 들어갈 기본 속성
                article_data = {
                    "article_id": article_id,
                    "title": row.get("title", ""),
                    "url": row.get("url", ""),
                    "published_date": str(row.get("published_date", "")),
                }

                # 1) Article 생성
                session.execute_write(create_article_node, article_data)

                # 2) Content 청크 생성 + HAS_CHUNK 관계
                if "content" in row and pd.notna(row["content"]) and row["content"] != "":
                    content_chunks = chunk_text(row["content"], chunk_size, overlap)
                    if content_chunks:
                        session.execute_write(create_content_nodes, article_id, content_chunks, article_data)

                # 3) Media 노드 + PUBLISHED 관계
                if "source" in row:
                    session.execute_write(create_media_node_and_relationship, article_id, row["source"])

                # 4) Category 노드 + BELONGS_TO 관계
                if "category" in row:
                    session.execute_write(create_category_node_and_relationship, article_id, row["category"])

                # 진행률 로그
                if (idx + 1) % 10 == 0:
                    print(f"진행률: {idx + 1}/{len(df)} ({((idx + 1) / len(df) * 100):.1f}%)")

            except Exception as exc:
                print(f"기사 {idx} 처리 중 오류 발생: {exc}")
                continue


def parse_args() -> argparse.Namespace:
    """CLI 인자를 파싱한다."""
    parser = argparse.ArgumentParser(description="뉴스 엑셀 -> Neo4j 그래프 빌더")
    parser.add_argument("--input", type=str, default="", help="입력 엑셀 파일 경로 (기본: data 폴더 최신 파일)")
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE, help="본문 청크 크기")
    parser.add_argument("--overlap", type=int, default=DEFAULT_OVERLAP, help="청크 오버랩 크기")
    parser.add_argument("--no-clear", action="store_true", help="DB 초기화를 생략")
    return parser.parse_args()


def main() -> None:
    """실행 진입점."""
    args = parse_args()

    # .env에서 Neo4j 접속정보를 로드한다.
    load_dotenv()
    uri = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
    auth = ("neo4j", os.getenv("NEO4J_PASSWORD", "password"))

    # 입력 파일 경로: 지정값 우선, 없으면 data 폴더 최신 파일 자동 선택
    input_path = Path(args.input) if args.input else find_latest_excel(DATA_DIR)
    print(f"입력 파일: {input_path}")

    df = pd.read_excel(input_path)
    print(f"기사 행 수: {len(df)}")

    driver = neo4j.GraphDatabase.driver(uri, auth=auth)
    try:
        with driver.session() as session:
            if not args.no_clear:
                print("데이터베이스 초기화 중...")
                session.execute_write(clear_database)
            session.execute_write(create_constraints)

        build_graph_from_dataframe(
            driver=driver,
            df=df,
            chunk_size=args.chunk_size,
            overlap=args.overlap,
        )
        print("그래프 빌드 완료")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
