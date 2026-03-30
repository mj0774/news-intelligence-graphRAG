from __future__ import annotations

"""네이버 뉴스 수집 모듈.

이 스크립트는 Selenium 기반으로 네이버 뉴스 섹션 페이지를 순회하며
기사 URL을 모은 뒤, 각 기사 상세 페이지에서 본문/메타데이터를 파싱해
루트 `data/` 폴더에 엑셀 파일로 저장한다.

포트폴리오 관점에서 이 파일을 읽을 때 핵심 흐름:
1) `init_driver()`로 브라우저 드라이버 준비
2) `get_article_links()`로 카테고리별 기사 링크 수집
3) `parse_article_detail()`로 기사 상세 데이터 파싱
4) `run_collection()`으로 전체 카테고리 루프 실행
5) `save_articles_to_excel()`로 결과 저장
"""

import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager


# -----------------------------------------------------------------------------
# 수집 대상 카테고리 정의
# -----------------------------------------------------------------------------
# key: 우리 프로젝트에서 사용할 카테고리명
# value: 네이버 뉴스 섹션 URL
CATEGORIES: Dict[str, str] = {
    "정치": "https://news.naver.com/section/100",
    "경제": "https://news.naver.com/section/101",
    "사회": "https://news.naver.com/section/102",
    "생활/문화": "https://news.naver.com/section/103",
    "IT/과학": "https://news.naver.com/section/105",
    "세계": "https://news.naver.com/section/104",
}

# 카테고리당 기본 수집 기사 수
NUM_ARTICLES_PER_CATEGORY = 10

# 결과 파일 저장 위치(프로젝트 루트 기준)
DATA_DIR = Path("data")


def init_driver() -> webdriver.Chrome:
    """Selenium Chrome 드라이버를 초기화한다.

    안정성 옵션 설명:
    - `--no-sandbox`: 제한된 환경에서 브라우저 실행 실패 방지
    - `--disable-dev-shm-usage`: 공유 메모리 부족 이슈 완화
    """
    service = Service(ChromeDriverManager().install())
    options = webdriver.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    return webdriver.Chrome(service=service, options=options)


def get_article_links(driver: Any, category_url: str, num_articles: int) -> List[str]:
    """카테고리 페이지에서 기사 링크를 추출한다.

    네이버 뉴스 DOM 구조는 시점에 따라 달라질 수 있으므로,
    셀렉터를 1개에 고정하지 않고 후보 목록을 순차 시도한다.
    """
    driver.get(category_url)
    time.sleep(3)

    article_links: List[str] = []

    try:
        selectors = [
            "a.sa_text_lede",
            "a.sa_text_strong",
            ".sa_text a",
            ".cluster_text_headline a",
            ".cluster_text_lede a",
        ]

        for selector in selectors:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            for element in elements:
                url = element.get_attribute("href")

                # 기사 본문 URL만 유지하고, 댓글/중복 링크는 제거한다.
                if (
                    url
                    and "news.naver.com" in url
                    and "/article/" in url
                    and "/comment/" not in url
                    and url not in article_links
                ):
                    article_links.append(url)

                # 목표 개수에 도달하면 즉시 중단해 불필요한 탐색을 줄인다.
                if len(article_links) >= num_articles:
                    break

            if len(article_links) >= num_articles:
                break

        print(f"✓ {len(article_links)}개의 기사 링크 수집 완료")

    except Exception as exc:
        print(f"✗ 기사 링크 수집 실패: {exc}")

    return article_links[:num_articles]


def parse_article_detail(driver: Any, article_url: str, category: str) -> Dict[str, str]:
    """기사 상세 페이지에서 제목/본문/메타데이터를 파싱한다.

    반환 스키마는 그래프 빌더 입력 컬럼과 맞춘다.
    - article_id, title, content, url, published_date, source, author, category
    """
    driver.get(article_url)
    time.sleep(1.5)

    article_data: Dict[str, str] = {
        "article_id": "",
        "title": "",
        "content": "",
        "url": article_url,
        "published_date": "",
        "source": "",
        "author": "",
        "category": category,
    }

    try:
        # URL 패턴(oid/aid)로 재현 가능한 기사 ID를 생성한다.
        match = re.search(r"article/(\d+)/(\d+)", article_url)
        if match:
            article_data["article_id"] = f"ART_{match.group(1)}_{match.group(2)}"
        else:
            # 예외 URL 대비 fallback ID
            article_data["article_id"] = f"ART_{datetime.now().strftime('%Y%m%d%H%M%S')}"

        # 제목 파싱: DOM 변동 대비 다중 셀렉터 순차 시도
        title_selectors = [
            "#title_area span",
            "#ct .media_end_head_headline",
            ".media_end_head_headline",
            "h2#title_area",
            ".news_end_title",
        ]
        for selector in title_selectors:
            try:
                title_element = driver.find_element(By.CSS_SELECTOR, selector)
                if title_element.text.strip():
                    article_data["title"] = title_element.text.strip()
                    break
            except Exception:
                continue

        # 본문 파싱: 레이아웃 버전에 맞춰 후보 셀렉터 시도
        content_selectors = [
            "#dic_area",
            "article#dic_area",
            ".go_trans._article_content",
            "._article_body_contents",
        ]
        for selector in content_selectors:
            try:
                content_element = driver.find_element(By.CSS_SELECTOR, selector)
                if content_element.text.strip():
                    article_data["content"] = content_element.text.strip()
                    break
            except Exception:
                continue

        # 언론사명 추출
        try:
            source_element = driver.find_element(By.CSS_SELECTOR, "a.media_end_head_top_logo img")
            article_data["source"] = source_element.get_attribute("alt") or ""
        except Exception:
            try:
                source_element = driver.find_element(By.CSS_SELECTOR, ".media_end_head_top_logo_text")
                article_data["source"] = source_element.text.strip()
            except Exception:
                pass

        # 발행일 추출 실패 시 현재 시각을 fallback으로 사용
        try:
            date_element = driver.find_element(
                By.CSS_SELECTOR,
                "span.media_end_head_info_datestamp_time, span[data-date-time]",
            )
            date_text = date_element.get_attribute("data-date-time") or date_element.text
            article_data["published_date"] = date_text.strip()
        except Exception:
            article_data["published_date"] = datetime.now().strftime("%Y-%m-%d %H:%M")

        # 기자명 추출
        try:
            author_element = driver.find_element(
                By.CSS_SELECTOR,
                "em.media_end_head_journalist_name, span.byline_s",
            )
            article_data["author"] = author_element.text.strip()
        except Exception:
            pass

    except Exception as exc:
        print(f" ✗ 파싱 오류: {exc}")

    return article_data


def run_collection(driver: Any, num_articles_per_category: int = NUM_ARTICLES_PER_CATEGORY) -> List[Dict[str, str]]:
    """전체 카테고리를 순회하며 기사 데이터를 수집한다."""
    all_articles: List[Dict[str, str]] = []

    for category_name, category_url in CATEGORIES.items():
        print(f"\n{'=' * 60}")
        print(f"[{category_name}] 카테고리 수집 시작...")
        print(f"{'=' * 60}")

        # 1) 카테고리 페이지에서 기사 URL 수집
        article_links = get_article_links(driver, category_url, num_articles_per_category)

        # 2) URL별 상세 데이터 파싱
        for idx, article_url in enumerate(article_links, 1):
            print(f" [{idx}/{len(article_links)}] {article_url}")
            article_data = parse_article_detail(driver, article_url, category_name)

            # 제목이 없는 경우는 품질이 낮거나 파싱 실패 가능성이 높아 제외한다.
            if article_data["title"]:
                all_articles.append(article_data)
                print(f" ✓ 수집 완료: {article_data['title'][:50]}...")
            else:
                print(" ✗ 수집 실패 - 제목을 찾을 수 없습니다.")

            # 사이트 부하/차단 리스크를 줄이기 위한 짧은 대기
            time.sleep(0.5)

    return all_articles


def save_articles_to_excel(all_articles: List[Dict[str, str]]) -> str:
    """수집 결과를 `data/` 폴더 아래 엑셀로 저장하고 경로를 반환한다."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    df_articles = pd.DataFrame(all_articles)
    output_path = DATA_DIR / f"Articles_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    df_articles.to_excel(output_path, index=False, engine="openpyxl")

    return str(output_path)


def main() -> None:
    """스크립트 실행 진입점."""
    driver = init_driver()
    try:
        all_articles = run_collection(driver=driver, num_articles_per_category=NUM_ARTICLES_PER_CATEGORY)
        output_filename = save_articles_to_excel(all_articles)

        print("\n수집 완료")
        print(f"- 총 기사 수: {len(all_articles)}")
        print(f"- 저장 파일: {output_filename}")
    finally:
        # 예외 여부와 관계없이 브라우저 프로세스를 정리한다.
        driver.quit()


if __name__ == "__main__":
    main()
