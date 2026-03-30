# news-intelligence-graphRAG

네이버 뉴스를 수집해 지식그래프를 구축하고, 질의 의도에 맞는 Retriever를 선택해 답변하는 Agentic GraphRAG 프로젝트입니다.

## 프로젝트 개요
- 데이터 파이프라인: `수집 -> 그래프 적재 -> 임베딩/벡터 인덱스`
- 검색 파이프라인: `ToolsRouter -> GraphRAG -> 답변 + 하이라이트 그래프`
- 핵심 기능: 질문 유형에 따라 `vector_retriever`, `vectorcypher_retriever`, `text2cypher_retriever` 중 적절한 도구 선택

## 아키텍처
![Agentic GraphRAG Architecture](./assets/agentic-graphrag-architecture.svg)

## 디렉토리
- [collector/](./collector/README.md): 뉴스 수집 모듈
- [graph_builder/](./graph_builder/README.md): 그래프 생성 및 벡터 인덱스 모듈
- [backend/](./backend/README.md): 검색 API 및 Retriever 라우팅 모듈
- [frontend/](./frontend/README.md): 시각화 UI 모듈

## 빠른 시작
1. 의존성 설치
```bash
pip install -r requirements.txt
```
2. 환경변수 파일 생성
```bash
# Windows PowerShell
Copy-Item .env.example .env
```
3. 실행 순서
```bash
python collector/news_collector.py
python graph_builder/build_graph.py
python graph_builder/build_vector_index.py
uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8000
```

프론트 실행과 모듈별 상세 설명은 내부 README를 참고하세요.

## 기술 스택
- Python, FastAPI, Uvicorn
- Neo4j, neo4j-graphrag
- OpenAI (LLM, Embedding)
- Selenium, Pandas, OpenPyXL
- vis-network, marked.js
