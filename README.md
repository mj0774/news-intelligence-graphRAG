# news-intelligence-graphRAG

뉴스 데이터를 수집하고, Neo4j 지식그래프를 구축한 뒤, 상황에 맞는 Retriever를 선택해 질의응답하는 GraphRAG 프로젝트입니다.

## Architecture

![Agentic GraphRAG Architecture](./assets/agentic-graphrag-architecture.svg)

## Project Structure

- `collector/` : 네이버 뉴스 수집
- `graph_builder/` : 엑셀 데이터 -> Neo4j 그래프 적재
- `backend/` : ToolsRetriever 기반 검색 API
- `frontend/` : 질의 입력 + 결과/그래프 시각화 UI
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

- `frontend/index.html`을 브라우저에서 열어 사용
