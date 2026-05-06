"""
楽待(rakumachi.jp)新聞のコラム/ニュース一覧スクレイパー。

楽待新聞は3つの主要セクションがあり、それぞれ別フィードとして購読する:
  - /news/column     - 楽待編集部の取材記事
  - /news/series     - 専門家による連載コラム
  - /news/practical  - 実践大家コラム

すべて同じDOM構造のため、URL違いだけで同じパーサーを使う。

記事URL形式: https://www.rakumachi.jp/news/{section}/{numeric_id}
  例: https://www.rakumachi.jp/news/column/318756
"""
from typing import Optional
from urllib.parse import urljoin
import re

from bs4 import BeautifulSoup
from .scrape_base import ScrapeAdapterBase, parse_jp_date


class RakumachiNewsAdapter(ScrapeAdapterBase):
    """楽待新聞 全セクション共通スクレイパー。

    feeds.json の url で各セクション(column / series / practical)を切り替える。
    """
    source_type = "scrape_rakumachi"

    def parse_listing(self, soup: BeautifulSoup, base_url: str, feed: dict) -> list[dict]:
        items = []
        seen_urls = set()

        # 楽待新聞の記事URL: /news/{column|series|practical|...}/<id>
        article_link_re = re.compile(
            r"^https?://(?:www\.)?rakumachi\.jp/news/[a-z_-]+/\d+/?(?:\?.*)?$",
            re.IGNORECASE
        )

        for a in soup.find_all("a", href=True):
            href = a["href"]
            absolute = urljoin(base_url, href)
            # クエリ・フラグメントを除いて正規化
            absolute = absolute.split("?")[0].split("#")[0].rstrip("/")

            if not article_link_re.match(absolute + "/"):  # 末尾スラッシュ補正で再確認
                # match 失敗時、queryなしで再試行
                if not article_link_re.match(absolute):
                    continue

            if absolute in seen_urls:
                continue
            seen_urls.add(absolute)

            title = (a.get_text(strip=True) or "").strip()
            # アイコンや小さなボタンのリンクをスキップ
            if not title or len(title) < 8:
                continue
            # ページネーションっぽいリンクを除外
            if title.isdigit() or title in {"次へ", "前へ", "more", "もっと見る"}:
                continue

            published = None
            author = None
            container = a.find_parent(["li", "tr", "div", "article"])
            if container:
                full_text = container.get_text(" ", strip=True)
                m = re.search(r"(20\d{2})[/.\-年](\d{1,2})[/.\-月](\d{1,2})", full_text)
                if m:
                    date_str = f"{m.group(1)}/{int(m.group(2)):02d}/{int(m.group(3)):02d}"
                    published = parse_jp_date(date_str)

                # 著者名は記事カード内に存在することが多い
                # 楽待は著者名がリンクテキストやspanで表示される。最初に見つかる
                # 6〜30文字の日本語テキスト(title 以外)を著者と仮定
                for el in container.find_all(["span", "a"], limit=10):
                    txt = (el.get_text(strip=True) or "").strip()
                    if (txt and txt != title and 2 <= len(txt) <= 30
                        and not txt.isdigit()
                        and not re.match(r"\d", txt)
                        and "20" not in txt):
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
