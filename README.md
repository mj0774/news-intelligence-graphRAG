# news-intelligence-graphRAG

## 1. 프로젝트 한 줄 소개
네이버 뉴스 데이터를 그래프로 구조화하고, 질의 의도에 따라 검색 전략을 선택하는 **GraphRAG + ToolsRetriever** 시스템입니다.

## 2. 개요
- 데이터: 네이버 뉴스 기사(제목, 본문, URL, 발행일, 카테고리, 언론사)
- 저장: Neo4j 그래프(`Article`, `Content`, `Category`, `Media`) + `Content.embedding` 벡터 인덱스
- 결과: 답변과 함께 `used_tool`, `articles`, `highlighted_*` 반환

## 3. 문제 정의 및 해결 방식
기존 단일 RAG 경로는 질문 유형이 달라질 때 검색 편차가 큽니다.  
이 프로젝트는 이를 줄이기 위해 다음 구조를 설계했습니다.
- 문서를 그래프로 모델링해 관계 질의를 가능하게 함
- Retriever를 목적별로 분리함
- ToolsRetriever가 질의 의도에 맞는 경로를 선택하도록 구성함
-> 단일 검색이 아닌, 질의 유형에 따라 검색 전략을 선택하는 구조로 설계했습니다.

## 4. 시스템 구조
파이프라인:
`뉴스 수집 -> 그래프 적재/청킹 -> 임베딩/벡터 인덱스 생성 -> ToolsRetriever 선택 -> GraphRAG 답변 생성`

동작 흐름:
1. 수집 데이터 적재 후 Neo4j 그래프 생성
2. `Content.embedding` 생성 및 `content_vector_index` 준비
3. `/api/search` 요청 시 ToolsRetriever가 retriever 선택
4. GraphRAG가 최종 답변 생성
5. API가 구조화 응답 반환

## 5. 검색 전략
| Retriever | 역할 | 언제 사용하는가 |
|---|---|---|
| `VectorRetriever` | 의미 유사 청크 탐색 | 키워드/개념 기반으로 유사 기사 빠르게 찾을 때 |
| `VectorCypherRetriever` | 벡터 검색 + 그래프 관계 확장 | 기사 상세, 카테고리, 연관 기사까지 함께 보고 싶을 때 |
| `Text2CypherRetriever` | 자연어 -> Cypher 변환 구조 질의 | 카테고리 조건, 목록 조회, 집계/통계 질문일 때 |

ToolsRetriever는 위 3개를 도구로 등록하고, 질의 텍스트를 기준으로 적절한 경로를 선택합니다.

## 6. 핵심 기능
- 네이버 뉴스 수집 및 표준 스키마 저장
- 기사 본문 청킹 기반 Neo4j 그래프 모델 생성
- Content 임베딩 및 벡터 인덱스 구축
- ToolsRetriever 기반 멀티-retriever 라우팅
- 검색 결과를 구조화 응답으로 제공

## 7. 주요 구현 (내 기여)
- 단일 검색이 아닌 **GraphRAG 파이프라인 구조**를 설계했습니다.
- 질의 유형별 처리를 위해 **Retriever 분리 + ToolsRetriever 선택 구조**를 설계했습니다.
- Neo4j 그래프 모델과 데이터 적재 전략(청킹, 관계, 제약조건, 벡터 인덱스)을 설계했습니다.
- API 응답을 `answer`, `used_tool`, `articles`, `highlighted_*` 형태로 표준화하는 구조를 설계했습니다.

## 8. 실행 방법
```bash
pip install -r requirements.txt
Copy-Item .env.example .env
python collector/news_collector.py
python graph_builder/build_graph.py
python graph_builder/build_vector_index.py
uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8000
```
