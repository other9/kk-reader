"""
健美家(kenbiya.com)のコラム+ニュース一覧スクレイパー。

対象URL: https://www.kenbiya.com/ar/
このページにはコラムとニュースが時系列で混在表示されている。

記事URL形式(2026-05時点):
  https://www.kenbiya.com/ar/cl/<author>/<id>.html  ← コラム
  https://www.kenbiya.com/ar/ns/<category>/<id>.html ← ニュース
  https://www.kenbiya.com/ar/ns/<category>/<sub>/<id>.html ← ニュース(2階層)

更新履歴:
- 2026-05-06 (update-007): 初版
- 2026-05-09 (update-009):
    - thumbnail link が title link を dedup で食う bug を修正
      (scrape_base.extract_listing_links を使用)
    - 末尾 "yyyy/mm/dd New" バッジを title から除去
    - title 末尾 date を published として優先採用
"""
import re
from typing import Optional

from bs4 import BeautifulSoup

from .scrape_base import (
    ScrapeAdapterBase,
    parse_jp_date,
    clean_listing_title,
    extract_date_from_title,
)


# /ar/cl/<author>/<id>.html または /ar/ns/<category>[/sub]/<id>.html
_ARTICLE_RE = re.compile(
    r"^https?://(?:www\.)?kenbiya\.com/ar/(?:cl|ns)/[^/]+(?:/[^/]+)?/\d+\.html?$",
    re.IGNORECASE,
)


class KenbiyaColumnsAdapter(ScrapeAdapterBase):
    source_type = "scrape_kenbiya"

    def parse_listing(self, soup: BeautifulSoup, base_url: str, feed: dict) -> list[dict]:
        # URL → (最長 text, anchor) を集約。thumbnail link 問題を回避。
        url_to_link = self.extract_listing_links(soup, base_url, _ARTICLE_RE)

        items = []
        for absolute, (raw_text, a_tag) in url_to_link.items():
            # title 末尾の "yyyy/mm/dd New" を date+title に分離
            published = extract_date_from_title(raw_text)
            title = clean_listing_title(raw_text)

            if not title or len(title) < 4:
                continue

            # 著者は URL slug から推定 (/ar/cl/<author>/N.html)
            author: Optional[str] = None
            slug_match = re.search(r"/ar/cl/([^/]+)/", absolute)
            if slug_match:
                author = slug_match.group(1)

            # title から date を取れなかった場合のフォールバック: 親 container の text から
            if not published and a_tag is not None:
                container = a_tag.find_parent(["li", "tr", "div", "article"])
                if container:
                    full_text = container.get_text(" ", strip=True)
                    m = re.search(
                        r"(20\d{2})[/.\-年](\d{1,2})[/.\-月](\d{1,2})",
                        full_text,
                    )
                    if m:
                        date_str = (
                            f"{m.group(1)}/{int(m.group(2)):02d}/{int(m.group(3)):02d}"
                        )
                        published = parse_jp_date(date_str)

            items.append({
                "url": absolute,
                "title": title,
                "published": published,
                "author": author,
                "summary": "",  # 一覧ページからは要約を確実に取れないため空
            })

        return items
