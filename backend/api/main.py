from __future__ import annotations

"""FastAPI 엔트리포인트 모듈.

이 파일의 역할은 크게 3가지다.
1) 앱 생명주기(lifespan)에서 DI 컨테이너를 생성/정리한다.
2) API 라우트를 정의하고 요청/응답 스키마를 연결한다.
3) 실제 비즈니스 로직은 서비스 계층으로 위임해 결합도를 낮춘다.
"""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from backend.core.container import AppContainer, build_container
from backend.schemas import GraphResponse, SearchRequest, SearchResponse
from backend.services.retriever_service import RetrieverService


@asynccontextmanager
async def lifespan(app: FastAPI):
    """애플리케이션 시작/종료 시 공용 리소스를 관리한다.

    - 시작 시: 컨테이너를 1회 생성해 `app.state`에 저장
    - 종료 시: 컨테이너가 보유한 연결(Neo4j 드라이버 등) 정리

    참고: FastAPI 최신 권장 방식은 `@app.on_event` 대신 lifespan 사용이다.
    """
    # startup: 서버 프로세스가 뜰 때 컨테이너를 한 번만 만든다.
    app.state.container = build_container()
    try:
        # 여기서 yield 이전은 startup, 이후는 shutdown 구간이다.
        yield
    finally:
        # shutdown: 남아 있는 외부 연결을 안전하게 닫는다.
        container: AppContainer = app.state.container
        container.close()


# 백엔드 API 앱 초기화.
app = FastAPI(title="News GraphRAG Backend", version="0.4.0", lifespan=lifespan)

# 개발 단계에서는 프론트/백 분리 실행이 잦아서 CORS를 전체 허용한다.
# 배포 환경에서는 허용 Origin을 특정 도메인으로 좁히는 것이 안전하다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_retriever_service(request: Request) -> RetrieverService:
    """요청 핸들러에 RetrieverService를 주입하는 의존성 함수.

    API 함수가 컨테이너 내부 구조를 직접 알 필요 없도록
    FastAPI `Depends`를 통해 서비스 객체만 전달한다.
    """
    container: AppContainer = request.app.state.container
    return container.retriever_service


@app.get("/api/health")
def health() -> dict[str, str]:
    """헬스체크 엔드포인트.

    인프라/배포 환경에서 서버 기동 상태를 빠르게 확인할 때 사용한다.
    """
    return {"status": "ok"}


@app.get("/api/graph", response_model=GraphResponse)
def graph(service: RetrieverService = Depends(get_retriever_service)) -> GraphResponse:
    """초기 그래프 시각화를 위한 전체 노드/엣지 데이터를 반환한다."""
    result = service.graph()
    return GraphResponse(**result)


@app.post("/api/search", response_model=SearchResponse)
def search(
    payload: SearchRequest,
    service: RetrieverService = Depends(get_retriever_service),
) -> SearchResponse:
    """사용자 질의를 받아 GraphRAG 검색 결과를 반환한다.

    요청 바디에서 `query`를 받아 서비스 계층으로 위임하고,
    프론트가 바로 렌더링할 수 있는 구조화된 응답으로 돌려준다.
    """
    result = service.search(payload.query)
    return SearchResponse(**result)
