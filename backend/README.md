# Backend 실행

```bash
uvicorn backend.api.main:app --reload
```

## Endpoints

- Health: `GET http://localhost:8000/api/health`
- Graph: `GET http://localhost:8000/api/graph`
- Search: `POST http://localhost:8000/api/search`

예시 요청:

```json
{"query": "생활/문화 카테고리 뉴스 3개 알려줘"}
```
