from __future__ import annotations

"""뉴스 엑셀 데이터를 Neo4j 그래프로 적재하는 빌더.

이 스크립트는 수집된 엑셀(`data/*.xlsx`)을 읽어서
다음 그래프 구조를 만든다.
- (Article)
- (Content)
- (Media)
- (Category)
- (Article)-[:HAS_CHUNK]->(Content)
- (Media)-[:PUBLISHED]->(Article)
- (Article)-[:BELONGS_TO]->(Category)

중요: 이 파일은 "그래프 구조 생성"에 집중하며,
임베딩/벡터인덱스 생성은 `build_vector_index.py`에서 분리 처리한다.
"""

import argparse
import os
from pathlib import Path
from typing import Any, Dict, List

import neo4j
import pandas as pd
from dotenv import load_dotenv


# 수집 엑셀 기본 경로(프로젝트 루트 기준)
DATA_DIR = Path("data")

# 본문 청킹 기본값
DEFAULT_CHUNK_SIZE = 500
DEFAULT_OVERLAP = 50


def find_latest_excel(data_dir: Path) -> Path:
    """`data/` 폴더에서 가장 최근 엑셀 파일을 찾는다."""
    files = sorted(data_dir.glob("*.xlsx"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        raise FileNotFoundError(f"엑셀 파일이 없습니다: {data_dir}")
    return files[0]


def chunk_text(text: Any, chunk_size: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_OVERLAP) -> List[str]:
    """본문 문자열을 겹침(overlap)을 두고 청킹한다.

    왜 overlap을 쓰는가?
    - 문장 경계가 chunk 중간에서 끊겨 의미가 손실되는 문제를 완화하기 위해.
    """
    if pd.isna(text) or text == "":
        return []

    text = str(text)
    chunks: List[str] = []

    # step이 0 이하가 되지 않게 안전장치 적용
    step = max(1, chunk_size - overlap)
    for i in range(0, len(text), step):
        chunk = text[i : i + chunk_size]
        if chunk.strip():
            chunks.append(chunk.strip())

    return chunks


def clear_database(tx: neo4j.Transaction) -> None:
    """그래프 DB 전체 데이터를 삭제한다.

    개발/실험 단계에서 재적재 시 중복 축적을 방지하기 위해 사용한다.
    """
    tx.run("MATCH (n) DETACH DELETE n")


def create_constraints(tx: neo4j.Transaction) -> None:
    """중복 삽입 방지용 유니크 제약조건을 생성한다."""
    constraints = [
        "CREATE CONSTRAINT IF NOT EXISTS FOR (a:Article) REQUIRE a.article_id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Content) REQUIRE c.content_id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (m:Media) REQUIRE m.name IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (cat:Category) REQUIRE cat.name IS UNIQUE",
    ]

    for constraint in constraints:
        tx.run(constraint)


def create_article_node(tx: neo4j.Transaction, article_data: Dict[str, str]) -> None:
    """Article 노드를 생성 또는 업데이트한다."""
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
    """Content 노드와 HAS_CHUNK 관계를 생성한다."""
    for idx, chunk in enumerate(content_chunks):
        content_id = f"{article_id}_chunk_{idx}"

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
            chunk_index=idx,
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

    tx.run("MERGE (m:Media {name: $source}) RETURN m", source=source)

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

    tx.run("MERGE (cat:Category {name: $category}) RETURN cat", category=category)

    relationship_query = """
    MATCH (a:Article {article_id: $article_id})
    MATCH (cat:Category {name: $category})
    MERGE (a)-[:BELONGS_TO]->(cat)
    """
    tx.run(relationship_query, article_id=article_id, category=category)


def build_graph_from_dataframe(
    df: pd.DataFrame,
    driver: neo4j.Driver,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> None:
    """DataFrame를 순회하며 그래프를 구축한다."""
    with driver.session() as session:
        for idx, row in df.iterrows():
            try:
                article_id = str(row.get("article_id", "")).strip()
                if not article_id:
                    continue

                article_data = {
                    "article_id": article_id,
                    "title": str(row.get("title", "")),
                    "url": str(row.get("url", "")),
                    "published_date": str(row.get("published_date", "")),
                }

                # 1) Article 생성
                session.execute_write(create_article_node, article_data)

                # 2) Content 생성
                if "content" in row and pd.notna(row["content"]) and row["content"] != "":
                    content_chunks = chunk_text(row["content"], chunk_size, overlap)
                    if content_chunks:
                        session.execute_write(create_content_nodes, article_id, content_chunks, article_data)

                # 3) Media 연결
                if "source" in row:
                    session.execute_write(create_media_node_and_relationship, article_id, row["source"])

                # 4) Category 연결
                if "category" in row:
                    session.execute_write(create_category_node_and_relationship, article_id, row["category"])

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
    """스크립트 실행 진입점."""
    args = parse_args()

    load_dotenv()
    uri = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
    auth = (os.getenv("NEO4J_USERNAME", "neo4j"), os.getenv("NEO4J_PASSWORD", "password"))

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
            df=df,
            driver=driver,
            chunk_size=args.chunk_size,
            overlap=args.overlap,
        )

        print("그래프 빌드 완료")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
