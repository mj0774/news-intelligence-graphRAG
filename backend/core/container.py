from __future__ import annotations

"""의존성 컨테이너(DI Container) 모듈.

컨테이너는 "무엇을 생성할지"를 한 곳에서 관리한다.
라우터/서비스는 컨테이너가 만든 객체를 주입받아 사용하므로,
서로의 구현 세부사항을 몰라도 된다.
"""

import neo4j
from neo4j_graphrag.embeddings import OpenAIEmbeddings
from neo4j_graphrag.llm import OpenAILLM

from backend.core.config import Settings, load_settings
from backend.retriever.graph_reader import GraphReader
from backend.retriever.tools_router import ToolsRouter
from backend.services.retriever_service import RetrieverService


class AppContainer:
    """애플리케이션 전역 객체를 조립/보관하는 컨테이너.

    생성 책임:
    - 외부 리소스 객체(Neo4j Driver, LLM, Embedder)
    - 도메인 모듈(ToolsRouter, GraphReader)
    - 서비스 계층(RetrieverService)
    """

    def __init__(self, settings: Settings) -> None:
        # 설정 객체를 보관해 필요 시 디버깅/로그 확인에 활용한다.
        self.settings = settings

        # Neo4j 드라이버는 생성 비용이 있으므로 요청마다 만들지 않고
        # 앱 수명 동안 재사용한다.
        self.driver = neo4j.GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_username, settings.neo4j_password),
        )

        # LLM/임베더도 재사용 가능한 의존성으로 컨테이너에서 1회 생성한다.
        self.llm = OpenAILLM(
            model_name=settings.openai_llm_model,
            model_params={"temperature": 0},
        )
        self.embedder = OpenAIEmbeddings(model=settings.openai_embed_model)

        # 검색 라우팅과 그래프 조회 모듈을 조립한다.
        self.tools_router = ToolsRouter(
            driver=self.driver,
            llm=self.llm,
            embedder=self.embedder,
        )
        self.graph_reader = GraphReader(driver=self.driver)

        # API가 직접 retriever를 다루지 않도록 서비스 계층으로 감싼다.
        self.retriever_service = RetrieverService(
            router=self.tools_router,
            graph_provider=self.graph_reader,
        )

    def close(self) -> None:
        """프로세스 종료 시 컨테이너 리소스를 정리한다."""
        self.driver.close()


def build_container() -> AppContainer:
    """설정을 로드하고 컨테이너를 생성한다.

    앱 startup 구간에서 이 함수를 한 번 호출해
    전체 의존성 그래프를 초기화한다.
    """
    settings = load_settings()
    return AppContainer(settings)
