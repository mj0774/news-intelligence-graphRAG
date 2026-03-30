# Graph Builder

수집된 엑셀 데이터를 Neo4j 그래프로 적재하고, Content 임베딩/벡터 인덱스를 생성합니다.

## 파일
- `build_graph.py`: Article/Content/Category/Media 노드 및 관계 생성
- `build_vector_index.py`: Content 임베딩 생성 + 벡터 인덱스 생성

## 실행 순서
1. 그래프 생성
```bash
python graph_builder/build_graph.py
```

2. 벡터 인덱스 생성
```bash
python graph_builder/build_vector_index.py
```

## build_graph.py 옵션
```bash
python graph_builder/build_graph.py --help
```
주요 옵션:
- `--input`: 입력 엑셀 파일 경로 (기본: `data/` 최신 파일)
- `--chunk-size`: 본문 청크 크기
- `--overlap`: 청크 오버랩 크기
- `--no-clear`: DB 초기화 생략

## 사전 조건
- `.env`에 Neo4j 접속 정보 필요
- 벡터 인덱스 생성 시 `.env`에 `OPENAI_API_KEY` 필요
