"""
健美家(kenbiya.com)のコラム+ニュース一覧スクレイパー。

対象URL: https://www.kenbiya.com/ar/
このページにはコラムとニュースが時系列で混在表示されている。

DOM構造の前提(2026-05時点):
  ul/dl のような繰り返し構造の各item内に:
  - a タグで記事タイトル+URL
  - 著者または発信元の表記
  - 日付(yyyy/mm/dd 形式)
  - カテゴリ(コラム/ニュース)

ページ構造変更時に動かなくなった場合は、
inspect_failures.py で発見し、selector を調整する。

実装方針: 防御的に書き、既知/未知のセレクタを順に試行する。
"""
from typing import Optional
from urllib.parse import urljoin
import re

from bs4 import BeautifulSoup
from .scrape_base import ScrapeAdapterBase, parse_jp_date


class KenbiyaColumnsAdapter(ScrapeAdapterBase):
    source_type = "scrape_kenbiya"

    def parse_listing(self, soup: BeautifulSoup, base_url: str, feed: dict) -> list[dict]:
        items = []
        seen_urls = set()

        # 健美家のリスト構造に該当しそうな要素を順に試す。
        # /ar/cl/{author}/{N}.html および /ar/ns/{...} 形式のリンクを記事として認識。
        article_link_re = re.compile(
            r"^https?://(?:www\.)?kenbiya\.com/ar/(?:cl|ns)/.+\.html?",
            re.IGNORECASE
        )

        for a in soup.find_all("a", href=True):
            href = a["href"]
            absolute = urljoin(base_url, href)

            # 記事URL以外は除外
            if not article_link_re.match(absolute):
                continue
            if absolute in seen_urls:
                continue
            seen_urls.add(absolute)

            title = (a.get_text(strip=True) or "").strip()
            if not title or len(title) < 4:
                # 短すぎるリンクテキストは目次/ナビと判断してスキップ
                continue

            # 親要素から日付・著者を探す
            published = None
            author = None
            container = a.find_parent(["li", "tr", "div", "article"])
            if container:
                # 日付らしき文字列を全テキストから探す
                full_text = container.get_text(" ", strip=True)
                m = re.search(r"(20\d{2})[/.\-年](\d{1,2})[/.\-月](\d{1,2})", full_text)
                if m:
                    date_str = f"{m.group(1)}/{int(m.group(2)):02d}/{int(m.group(3)):02d}"
                    published = parse_jp_date(date_str)

                # URL中のスラッグから著者を推定 (/ar/cl/<author>/N.html)
                slug_match = re.search(r"/ar/cl/([^/]+)/", absolute)
                if slug_match:
                    author = slug_match.group(1)

            items.append({
                "url": absolute,
                "title": title,
                "published": published,
                "author": author,
                "summary": "",  # 一覧ページからは要約を確実に取れないため空
            })

        return items
