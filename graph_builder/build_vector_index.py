"""Content 임베딩 생성 + 벡터 인덱스 생성 스크립트.

참고자료1(ToolsRetriever.ipynb)의 전처리 흐름을
프로젝트 구조에 맞춰 스크립트화한 버전이다.
"""

from __future__ import annotations

import argparse
import os

import neo4j
from dotenv import load_dotenv
from neo4j_graphrag.embeddings.openai import OpenAIEmbeddings
from neo4j_graphrag.indexes import create_vector_index

DEFAULT_INDEX_NAME = "content_vector_index"
DEFAULT_EMBED_MODEL = "text-embedding-3-small"
DEFAULT_DIMENSION = 1536


def parse_args() -> argparse.Namespace:
    """CLI 인자를 파싱한다."""
    parser = argparse.ArgumentParser(description="Content 임베딩/벡터 인덱스 생성")
    parser.add_argument("--index-name", default=DEFAULT_INDEX_NAME, help="생성할 벡터 인덱스 이름")
    parser.add_argument("--embed-model", default=DEFAULT_EMBED_MODEL, help="OpenAI 임베딩 모델")
    parser.add_argument("--dimension", type=int, default=DEFAULT_DIMENSION, help="임베딩 차원 수")
    parser.add_argument("--batch-log", type=int, default=50, help="진행 로그 출력 간격")
    return parser.parse_args()


def upsert_content_embeddings(
    driver: neo4j.Driver,
    embedder: OpenAIEmbeddings,
    batch_log: int = 50,
) -> int:
    """embedding이 비어 있는 Content 노드에 임베딩 벡터를 저장한다."""
    select_query = """
    MATCH (c:Content)
    WHERE c.chunk IS NOT NULL AND c[$embedding_key] IS NULL
    RETURN elementId(c) AS id, c.chunk AS text
    """

    update_query = """
    MATCH (c)
    WHERE elementId(c) = $id
    SET c.embedding = $embedding
    """

    with driver.session() as session:
        rows = session.run(select_query, embedding_key="embedding").data()
        total = len(rows)

        if total == 0:
            print("임베딩 대상 Content 노드가 없습니다.")
            return 0

        updated = 0
        for idx, row in enumerate(rows, start=1):
            node_id = row["id"]
            text = str(row.get("text", ""))
            if not text.strip():
                continue

            # 참고자료1과 동일하게 chunk 텍스트를 임베딩해 Content.embedding에 저장한다.
            vector = embedder.embed_query(text)
            session.run(update_query, id=node_id, embedding=vector)
            updated += 1

            if idx % max(1, batch_log) == 0:
                print(f"임베딩 진행률: {idx}/{total}")

        return updated


def vector_index_exists(driver: neo4j.Driver, index_name: str) -> bool:
    """벡터 인덱스 존재 여부를 확인한다."""
    query = """
    SHOW INDEXES YIELD name
    WHERE name = $index_name
    RETURN count(*) AS cnt
    """
    with driver.session() as session:
        row = session.run(query, index_name=index_name).single()
        return bool(row and int(row.get("cnt", 0)) > 0)


def create_content_vector_index(
    driver: neo4j.Driver,
    index_name: str,
    dimension: int,
) -> None:
    """Content.embedding 대상으로 벡터 인덱스를 생성한다."""
    if vector_index_exists(driver, index_name):
        print(f"벡터 인덱스가 이미 존재합니다: {index_name}")
        return

    create_vector_index(
        driver,
        index_name,
        label="Content",
        embedding_property="embedding",
        dimensions=dimension,
        similarity_fn="cosine",
    )
    print(f"벡터 인덱스 생성 완료: {index_name}")


def main() -> None:
    """실행 진입점."""
    args = parse_args()
    load_dotenv()

    uri = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
    username = os.getenv("NEO4J_USERNAME", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "password")
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()

    if not openai_key:
        raise RuntimeError("OPENAI_API_KEY가 비어 있습니다. .env를 확인하세요.")

    driver = neo4j.GraphDatabase.driver(uri, auth=(username, password))
    try:
        embedder = OpenAIEmbeddings(model=args.embed_model)

        print("Content 임베딩 생성 시작...")
        updated = upsert_content_embeddings(
            driver=driver,
            embedder=embedder,
            batch_log=args.batch_log,
        )
        print(f"임베딩 업데이트 완료: {updated}건")

        print("벡터 인덱스 확인/생성 시작...")
        create_content_vector_index(
            driver=driver,
            index_name=args.index_name,
            dimension=args.dimension,
        )

        print("벡터 전처리 완료")
    finally:
        driver.close()


if __name__ == "__main__":
    main()

