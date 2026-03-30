from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from backend.core.container import AppContainer, build_container
from backend.schemas import GraphResponse, SearchRequest, SearchResponse
from backend.services.retriever_service import RetrieverService


@asynccontextmanager
async def lifespan(app: FastAPI):
    """애플리케이션 시작/종료 시점의 리소스를 관리한다."""
    # startup: 컨테이너 1회 생성
    app.state.container = build_container()
    try:
        yield
    finally:
        # shutdown: 컨테이너 리소스 정리
        container: AppContainer = app.state.container
        container.close()


# 백엔드 앱 초기화
app = FastAPI(title="News GraphRAG Backend", version="0.4.0", lifespan=lifespan)

# 프론트 로컬 개발 편의를 위해 CORS는 일단 전체 허용한다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_retriever_service(request: Request) -> RetrieverService:
    """요청 핸들러에서 사용할 서비스 의존성을 주입한다."""
    container: AppContainer = request.app.state.container
    return container.retriever_service


@app.get("/api/health")
def health() -> dict[str, str]:
    """헬스체크 엔드포인트."""
    return {"status": "ok"}


@app.get("/api/graph", response_model=GraphResponse)
def graph(service: RetrieverService = Depends(get_retriever_service)) -> GraphResponse:
    """프론트 초기 렌더링용 전체 그래프를 반환한다."""
    result = service.graph()
    return GraphResponse(**result)


@app.post("/api/search", response_model=SearchResponse)
def search(
    payload: SearchRequest,
    service: RetrieverService = Depends(get_retriever_service),
) -> SearchResponse:
    """질의를 받아 도구 라우팅 기반 검색 결과를 반환한다."""
    result = service.search(payload.query)
    return SearchResponse(**result)
