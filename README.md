# news-intelligence-graphRAG

뉴스 데이터를 수집하고, Neo4j 지식그래프를 구축한 뒤, 상황에 맞는 Retriever를 선택해 질의응답하는 GraphRAG 프로젝트입니다.

## Architecture

![Agentic GraphRAG Architecture](./assets/agentic-graphrag-architecture.svg)

## Project Structure

- `collector/` : 네이버 뉴스 수집
- `graph_builder/` : 엑셀 데이터 -> Neo4j 그래프 적재
- `backend/` : ToolsRetriever 기반 검색 API
- `frontend/` : 참고자료2 스타일 그래프 시각화 UI
- `data/` : 수집 결과 파일(`.xlsx`)

## Quick Start

1. 의존성 설치

```bash
pip install -r requirements.txt
```

2. 환경변수 설정

```bash
cp .env.example .env
```

3. 백엔드 실행

```bash
uvicorn backend.api.main:app --reload
```

4. 프론트 실행

- 브라우저에서 `frontend/index.html` 열기
- 백엔드 기본 주소: `http://localhost:8000`

## API

- `GET /api/health` : 서버 상태 확인
- `GET /api/graph` : 초기 전체 그래프 조회
- `POST /api/search` : tools retriever 기반 질의 검색 + 하이라이트 정보 반환
