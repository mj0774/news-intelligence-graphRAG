from __future__ import annotations

import neo4j
from neo4j_graphrag.embeddings import OpenAIEmbeddings
from neo4j_graphrag.llm import OpenAILLM

from backend.core.config import Settings, load_settings
from backend.retriever.graph_reader import GraphReader
from backend.retriever.tools_router import ToolsRouter
from backend.services.retriever_service import RetrieverService


class AppContainer:
    """애플리케이션 의존성 컨테이너.

    역할:
    - 인프라 객체(Neo4j, LLM, Embedder) 생성
    - 서비스 객체 조립(DI)
    - 종료 시 리소스 정리
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

        self.driver = neo4j.GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_username, settings.neo4j_password),
        )

        self.llm = OpenAILLM(
            model_name=settings.openai_llm_model,
            model_params={"temperature": 0},
        )
        self.embedder = OpenAIEmbeddings(model=settings.openai_embed_model)

        self.tools_router = ToolsRouter(
            driver=self.driver,
            llm=self.llm,
            embedder=self.embedder,
        )
        self.graph_reader = GraphReader(driver=self.driver)

        self.retriever_service = RetrieverService(
            router=self.tools_router,
            graph_provider=self.graph_reader,
        )

    def close(self) -> None:
        """앱 종료 시 커넥션을 정리한다."""
        self.driver.close()


def build_container() -> AppContainer:
    """설정 로드 + 컨테이너 생성 진입점."""
    settings = load_settings()
    return AppContainer(settings)
