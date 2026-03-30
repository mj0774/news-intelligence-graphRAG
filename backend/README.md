# Backend

질문을 받아 Retriever를 라우팅하고, 답변/기사목록/그래프 하이라이트 데이터를 반환하는 FastAPI 서버입니다.

## 실행
```bash
uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8000
```

## API
- `GET /api/health`: 서버 상태 확인
- `GET /api/graph`: 초기 그래프 조회
- `POST /api/search`: 질의 기반 검색 수행

## Search 요청 예시
```json
{
  "query": "정치 카테고리 최신 뉴스 알려줘"
}
```

## Search 응답 핵심 필드
- `answer`: 생성된 답변
- `used_tool`: 실제 사용 retriever
- `articles`: 기사 목록
- `nodes`, `edges`: 시각화용 그래프 데이터
- `highlighted_node_ids`, `highlighted_edge_ids`: 하이라이트 대상

## 라우팅 대상 Retriever
- `vector_retriever`
- `vectorcypher_retriever`
- `text2cypher_retriever`
