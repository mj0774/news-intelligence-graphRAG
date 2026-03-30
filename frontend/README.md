# Frontend

검색 UI와 그래프 시각화 화면을 제공합니다.

## 파일
- `index.html`: 화면 구조
- `styles.css`: 스타일
- `app.js`: API 연동/그래프 렌더링 로직

## 실행
정적 파일이므로 아래 중 하나로 실행할 수 있습니다.

1. 파일 직접 열기
- 브라우저에서 `frontend/index.html` 열기

2. 정적 서버 실행
```bash
cd frontend
python -m http.server 5500
```

## 백엔드 연동
- `app.js`의 `API_BASE` 기본값: `http://localhost:8000`
- 백엔드가 다른 포트/호스트에서 실행되면 `API_BASE`를 맞춰주세요.
