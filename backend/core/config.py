from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    """애플리케이션 설정값 객체.

    앱 시작 시 환경변수를 한 번 로드해 고정값으로 사용한다.
    서비스 레이어에서 직접 os.getenv를 호출하지 않도록 분리한다.
    """

    neo4j_uri: str
    neo4j_username: str
    neo4j_password: str
    openai_api_key: str
    openai_llm_model: str
    openai_embed_model: str


def load_settings() -> Settings:
    """.env를 로드하고 설정 객체를 생성한다."""
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
