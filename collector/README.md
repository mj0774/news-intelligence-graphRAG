# Collector

네이버 뉴스 카테고리 페이지에서 기사 링크를 수집하고, 기사 상세 페이지에서 본문/메타데이터를 파싱해 엑셀로 저장합니다.

## 파일
- `news_collector.py`: 수집 실행 스크립트

## 수집 스키마
수집 결과는 아래 컬럼으로 저장됩니다.
- `article_id`
- `title`
- `content`
- `url`
- `published_date`
- `source`
- `author`
- `category`

## 실행
```bash
python collector/news_collector.py
```

## 출력
- 저장 경로: `data/Articles_YYYYMMDD_HHMMSS.xlsx`

## 메모
- 카테고리별 기본 수집 개수는 코드 상수(`NUM_ARTICLES_PER_CATEGORY`)로 관리합니다.
- 페이지 구조 변경에 대비해 다중 CSS 셀렉터를 순차 적용합니다.
