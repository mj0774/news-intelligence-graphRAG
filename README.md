# news-intelligence-graphRAG

뉴스 기반 GraphRAG 분석 에이전트 프로젝트입니다.

## 프로젝트 구조

- `backend/`: 질의응답/검색 API 서버
- `frontend/`: 사용자 인터페이스
- `ingestion/`: 뉴스 수집/전처리/적재 파이프라인

## 목표 (MVP)

1. 뉴스 수집 (네이버 뉴스 API)
2. 엔티티/관계 추출
3. 지식 그래프 구축
4. 하이브리드 검색 (Graph + Vector)
5. 분석형 질의응답

## 시작 가이드

현재는 초기 스캐폴딩 단계입니다.

다음 구현 권장 순서:

1. `ingestion`에 수집기 구현
2. `backend`에 검색/응답 API 구현
3. `frontend`에 질의/리포트 화면 구현

## 개발 메모

- 수집 배치(`ingestion`)와 실시간 API(`backend`)는 분리 운영을 권장합니다.
- 환경 변수는 루트 `.env` 또는 각 서비스별 `.env`로 관리하세요.
