# Backend 실행

```bash
uvicorn backend.api.main:app --reload
```

- Health: `GET http://localhost:8000/api/health`
- Search: `POST http://localhost:8000/api/search`

예시 요청:

```json
{"query": "생활/문화 카테고리 뉴스 3개 알려줘"}
```
