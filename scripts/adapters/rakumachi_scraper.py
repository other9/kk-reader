"""
楽待(rakumachi.jp)新聞のコラム/ニュース一覧スクレイパー。

楽待新聞は3つの主要セクションがあり、それぞれ別フィードとして購読する:
  - /news/column     - 楽待編集部の取材記事
  - /news/series     - 専門家による連載コラム
  - /news/practical  - 実践大家コラム

すべて同じDOM構造のため、URL違いだけで同じパーサーを使う。

記事URL形式: https://www.rakumachi.jp/news/{section}/{numeric_id}
  例: https://www.rakumachi.jp/news/column/318756

更新履歴:
- 2026-05-06 (update-007): 初版
- 2026-05-09 (update-009):
    - via_worker: True で Cloudflare Worker proxy 経由で取得するため、
      Actions IP の WAF ブロックを回避(scrape_base 側で対応、本ファイルは
      パース部のみ)
    - thumbnail link が title link を dedup で食う bug を修正
      (scrape_base.extract_listing_links を使用)
    - 末尾 "yyyy/mm/dd New" バッジを title から除去
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


# 楽待新聞の記事URL: /news/{column|series|practical|...}/<id>(末尾スラッシュなし正規化済前提)
_ARTICLE_RE = re.compile(
    r"^https?://(?:www\.)?rakumachi\.jp/news/[a-z_-]+/\d+$",
    re.IGNORECASE,
)


def _normalize_rakumachi_url(url: str) -> str:
    """クエリ・フラグメントを除き、末尾スラッシュを除去。"""
    return url.split("?")[0].split("#")[0].rstrip("/")


class RakumachiNewsAdapter(ScrapeAdapterBase):
    """楽待新聞 全セクション共通スクレイパー。

    feeds.json の url で各セクション(column / series / practical)を切り替える。
    feeds.json で `via_worker: true` を立てると Cloudflare Worker 経由で取得する。
    """
    source_type = "scrape_rakumachi"

    def parse_listing(self, soup: BeautifulSoup, base_url: str, feed: dict) -> list[dict]:
        url_to_link = self.extract_listing_links(
            soup,
            base_url,
            _ARTICLE_RE,
            normalize_url=_normalize_rakumachi_url,
        )

        items = []
        for absolute, (raw_text, a_tag) in url_to_link.items():
            published = extract_date_from_title(raw_text)
            title = clean_listing_title(raw_text)

            # 短すぎ・ページネーション系は除外
            if not title or len(title) < 8:
                continue
            if title.isdigit() or title in {"次へ", "前へ", "more", "もっと見る"}:
                continue

            # 著者・日付は親 container から(楽待は author を URL から取れない)
            author: Optional[str] = None
            if a_tag is not None:
                container = a_tag.find_parent(["li", "tr", "div", "article"])
                if container:
                    full_text = container.get_text(" ", strip=True)
                    if not published:
                        m = re.search(
                            r"(20\d{2})[/.\-年](\d{1,2})[/.\-月](\d{1,2})",
                            full_text,
                        )
                        if m:
                            date_str = (
                                f"{m.group(1)}/{int(m.group(2)):02d}/{int(m.group(3)):02d}"
                            )
                            published = parse_jp_date(date_str)

                    # 著者名: title 以外で 2-30 文字の日本語テキスト(数字混じりや日付除外)
                    for el in container.find_all(["span", "a"], limit=10):
                        txt = (el.get_text(strip=True) or "").strip()
                        if (
                            txt
                            and txt != title
                            and txt != raw_text
                            and 2 <= len(txt) <= 30
                            and not txt.isdigit()
                            and not re.match(r"\d", txt)
                            and "20" not in txt
                            and "New" not in txt
                        ):
                            author = txt
                            break

            items.append({
                "url": absolute,
                "title": title,
                "published": published,
                "author": author,
                "summary": "",
            })

        return items
