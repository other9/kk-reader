"""
スクレイピング系アダプターの共通基盤。

RSSが提供されていないサイト(健美家・楽待 等)の
コラム/ニュース一覧ページから記事メタ情報を抽出する。

設計方針:
- 一覧ページのみスクレイピング、記事本文は取得しない
  (本文は Cloudflare Worker が必要時にon-demand取得+キャッシュする)
- メタ情報のみを Article として返す: title, url, published, author, summary
- content_html は None のまま(フロントが Worker から動的取得)

更新履歴:
- 2026-05-06: 初版
"""
from datetime import datetime, timezone
from typing import Optional
import requests
from bs4 import BeautifulSoup

from .base import SourceAdapter, Article, make_article_id


# 多くのサイトはbot系UAを拒否するため、Chrome系を偽装する(rss_adapter.py と同じ)
DEFAULT_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/121.0.0.0 Safari/537.36"
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_jp_date(s: str) -> Optional[str]:
    """日本語の日付文字列をISO8601に変換。失敗したらNone。

    対応形式:
      "2026/4/28" → "2026-04-28T00:00:00+09:00"
      "2026.4.28" → 同上
      "2026年4月28日" → 同上
      "2026-04-28" → 同上
    """
    if not s:
        return None
    s = s.strip()

    # 候補となるフォーマット
    fmts = [
        "%Y/%m/%d",
        "%Y.%m.%d",
        "%Y-%m-%d",
        "%Y年%m月%d日",
    ]

    for f in fmts:
        try:
            # JST として解釈
            from datetime import timezone, timedelta
            jst = timezone(timedelta(hours=9))
            dt = datetime.strptime(s, f).replace(tzinfo=jst)
            return dt.isoformat()
        except ValueError:
            continue
    return None


class ScrapeAdapterBase(SourceAdapter):
    """スクレイピング系アダプターの共通基底クラス。"""

    source_type: str = "scrape_base"
    timeout: int = 20

    def __init__(self, timeout: int = 20, user_agent: str = DEFAULT_UA):
        self.timeout = timeout
        self.user_agent = user_agent

    def _fetch_html(self, url: str) -> Optional[str]:
        """指定URLのHTMLを取得。失敗時はNone。"""
        try:
            headers = {
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
            }
            r = requests.get(url, headers=headers, timeout=self.timeout)
            r.raise_for_status()
            r.encoding = r.apparent_encoding or r.encoding
            return r.text
        except Exception:
            return None

    def fetch(self, feed: dict) -> tuple[list[Article], dict]:
        """
        feeds.json の1エントリから記事リストを取得。
        サブクラスは parse_listing() のみ実装すれば良い。
        """
        meta_update = {"last_fetch": now_iso()}
        url = feed["url"]
        html = self._fetch_html(url)

        if html is None:
            meta_update["error_count"] = feed.get("error_count", 0) + 1
            meta_update["last_error"] = "fetch failed"
            return [], meta_update

        try:
            soup = BeautifulSoup(html, "html.parser")
            items = self.parse_listing(soup, base_url=url, feed=feed)
        except Exception as e:
            meta_update["error_count"] = feed.get("error_count", 0) + 1
            meta_update["last_error"] = f"parse error: {e}"
            return [], meta_update

        articles = []
        for item in items:
            if not item.get("url") or not item.get("title"):
                continue
            articles.append(Article(
                id=make_article_id(item["url"]),
                feed_id=feed["id"],
                feed_title=feed["title"],
                category=feed.get("category", "未分類"),
                title=item["title"],
                url=item["url"],
                published=item.get("published"),
                fetched=now_iso(),
                summary=item.get("summary", ""),
                content_html=None,  # Worker が on-demand 取得
                author=item.get("author"),
                source_type=self.source_type,
            ))

        meta_update["last_success"] = now_iso()
        meta_update["error_count"] = 0
        meta_update["last_error"] = None
        return articles, meta_update

    def parse_listing(self, soup: BeautifulSoup, base_url: str, feed: dict) -> list[dict]:
        """
        一覧ページのBeautifulSoupからアイテムリストを抽出。
        サブクラスでオーバーライド。
        各アイテムは dict: {url, title, published, author, summary}
        """
        raise NotImplementedError
