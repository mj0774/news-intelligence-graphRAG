from __future__ import annotations

"""환경설정 로더 모듈.

이 프로젝트는 환경변수 값을 코드 곳곳에서 직접 읽지 않고,
서버 시작 시 한 번만 읽어 `Settings` 객체로 고정해 사용한다.
이 패턴을 통해 다음 이점을 얻는다.
- 설정 키 누락을 조기에 발견
- 테스트 시 설정 주입이 쉬움
- 서비스 계층이 `os.getenv`에 의존하지 않음
"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    """애플리케이션 전역 설정 모델.

    `frozen=True`를 사용해 런타임 중 설정이 바뀌지 않도록 고정한다.
    """

    # Neo4j 연결 정보
    neo4j_uri: str
    neo4j_username: str
    neo4j_password: str

    # OpenAI 사용 정보
    openai_api_key: str
    openai_llm_model: str
    openai_embed_model: str


def load_settings() -> Settings:
    """`.env`를 로드하고 Settings 객체를 생성한다.

    반환 전 필수값(OPENAI_API_KEY)을 검증해,
    서버 실행 중 뒤늦게 실패하는 상황을 예방한다.
    """
    load_dotenv()

    settings = Settings(
        neo4j_uri=os.getenv("NEO4J_URI", "neo4j://localhost:7687"),
        neo4j_username=os.getenv("NEO4J_USERNAME", "neo4j"),
        neo4j_password=os.getenv("NEO4J_PASSWORD", "password"),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_llm_model=os.getenv("OPENAI_LLM_MODEL", "gpt-4o"),
        openai_embed_model=os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small"),
    )

    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY가 설정되지 않았습니다. .env를 확인하세요.")

    return settings
