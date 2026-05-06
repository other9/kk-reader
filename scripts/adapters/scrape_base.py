"""
スクレイピング系アダプターの共通基盤。

更新履歴:
- 2026-05-06 (update-007): 初版
- 2026-05-06 (update-008): エラー詳細化、ブラウザ完全偽装ヘッダ、リトライ追加
"""
from datetime import datetime, timezone
from typing import Optional, Tuple
import time
import requests
from bs4 import BeautifulSoup

from .base import SourceAdapter, Article, make_article_id


# Chrome 121 系の完全偽装。Sec-Fetch-* 系まで含めて bot 検出をすり抜けやすくする。
DEFAULT_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/121.0.0.0 Safari/537.36"
)

# ブラウザがトップページにアクセスした時に送る一通り
DEFAULT_HEADERS = {
    "User-Agent": DEFAULT_UA,
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="121", "Google Chrome";v="121"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Linux"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_jp_date(s: str) -> Optional[str]:
    """日本語の日付文字列をISO8601に変換。失敗したらNone。"""
    if not s:
        return None
    s = s.strip()

    fmts = [
        "%Y/%m/%d",
        "%Y.%m.%d",
        "%Y-%m-%d",
        "%Y年%m月%d日",
    ]
    for f in fmts:
        try:
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
    retries: int = 2  # 失敗時のリトライ回数
    retry_delay: float = 1.5  # リトライ間隔(秒)

    def __init__(self, timeout: int = 20, user_agent: Optional[str] = None):
        self.timeout = timeout
        self.user_agent = user_agent or DEFAULT_UA

    def _build_headers(self, url: str) -> dict:
        """サイト別カスタマイズも将来できるよう、ベースヘッダを返す。"""
        headers = dict(DEFAULT_HEADERS)
        headers["User-Agent"] = self.user_agent
        return headers

    def _fetch_html(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """
        指定URLのHTMLを取得。
        Returns:
          (html, error_msg)
          成功時: (html, None)
          失敗時: (None, "HTTP 403" / "timeout" / "ssl: ..." 等の具体的メッセージ)
        """
        last_err: Optional[str] = None

        for attempt in range(self.retries + 1):
            try:
                headers = self._build_headers(url)
                r = requests.get(url, headers=headers, timeout=self.timeout)
                # 4xx/5xx も明示エラーとして扱う(以前は raise_for_status で隠蔽されていた)
                if r.status_code >= 400:
                    last_err = f"HTTP {r.status_code}"
                    # 403/429/503 はリトライしても無駄なので即離脱
                    if r.status_code in (403, 429, 503, 451):
                        return None, last_err
                    # 5xx は一時的な可能性ありリトライ対象
                    if attempt < self.retries:
                        time.sleep(self.retry_delay * (attempt + 1))
                        continue
                    return None, last_err

                r.encoding = r.apparent_encoding or r.encoding
                return r.text, None

            except requests.exceptions.SSLError as e:
                last_err = f"ssl: {str(e)[:80]}"
            except requests.exceptions.Timeout:
                last_err = "timeout"
            except requests.exceptions.ConnectionError as e:
                last_err = f"connection: {str(e)[:80]}"
            except requests.exceptions.RequestException as e:
                last_err = f"request: {type(e).__name__}: {str(e)[:80]}"
            except Exception as e:
                last_err = f"unexpected: {type(e).__name__}: {str(e)[:80]}"

            # リトライ前に少し待つ
            if attempt < self.retries:
                time.sleep(self.retry_delay * (attempt + 1))

        return None, last_err or "unknown"

    def fetch(self, feed: dict) -> tuple[list[Article], dict]:
        """feeds.json の1エントリから記事リストを取得。"""
        meta_update = {"last_fetch": now_iso()}
        url = feed["url"]
        html, err = self._fetch_html(url)

        if html is None:
            meta_update["error_count"] = feed.get("error_count", 0) + 1
            meta_update["last_error"] = err or "fetch failed"
            return [], meta_update

        try:
            soup = BeautifulSoup(html, "html.parser")
            items = self.parse_listing(soup, base_url=url, feed=feed)
        except Exception as e:
            meta_update["error_count"] = feed.get("error_count", 0) + 1
            meta_update["last_error"] = f"parse error: {type(e).__name__}: {str(e)[:80]}"
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
                content_html=None,
                author=item.get("author"),
                source_type=self.source_type,
            ))

        meta_update["last_success"] = now_iso()
        meta_update["error_count"] = 0
        meta_update["last_error"] = None
        return articles, meta_update

    def parse_listing(self, soup: BeautifulSoup, base_url: str, feed: dict) -> list[dict]:
        raise NotImplementedError
