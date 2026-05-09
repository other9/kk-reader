"""
スクレイピング系アダプターの共通基盤。

更新履歴:
- 2026-05-06 (update-007): 初版
- 2026-05-06 (update-008): エラー詳細化、ブラウザ完全偽装ヘッダ、リトライ追加
- 2026-05-09 (update-009):
    - Cloudflare Worker proxy 経由の取得 (`_fetch_html_via_worker`) を追加。
      feeds.json で `via_worker: true` のフィードは Actions 環境からの直 fetch を
      バイパスし、Worker /fetch エンドポイント経由で取りに行く。
      → 楽待 (rakumachi.jp) のような Actions IP を WAF で弾くサイトに対応。
    - リスティング解析の共通ヘルパー `extract_listing_links()` を追加。
      thumbnail link (text 空) と title link が同じ URL を指す場合に、document
      order の素朴な dedup で title を捨てていたバグの根本対応。
      → 健美家 articles 0 件のサイレント失敗の修正。
    - 末尾の "yyyy/mm/dd New" バッジ等を除去する `clean_listing_title()` /
      `extract_date_from_title()` を追加。
- 2026-05-09 (update-012):
    - `extract_listing_links()` のテキスト抽出を「anchor の get_text 全部連結」
      から「最長子要素テキスト」に変更。
      → 楽待 /news/practical(実践大家コラム)で title 先頭にランキング数字
        ("5築より立地…", "42027年問題…")が貼り付いていた問題の修正。
        anchor 内に <span>5</span><div>築より立地…</div> のように複数子要素が
        並ぶ DOM を、最長要素 = title として正しく識別する。
      → 健美家・楽待 column / series は anchor 内のテキスト構造が単純(または
        title 子要素が圧倒的に長い)ため、振る舞いは事実上同一。
      → 日付は anchor 直下から消える可能性があるため、各 adapter の
        find_parent 経由のフォールバック(既存)で拾う。
"""
import os
import re
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, Callable
from urllib.parse import urljoin, quote

import requests
from bs4 import BeautifulSoup

from .base import SourceAdapter, Article, make_article_id


# =====================================================================
# 直 fetch 用のブラウザ完全偽装(update-008)
# =====================================================================

DEFAULT_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/121.0.0.0 Safari/537.36"
)

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


# =====================================================================
# Worker proxy 設定 (update-009)
# =====================================================================

# 環境変数から取得。GitHub Actions では fetch-feeds.yml で env として渡される。
# 未設定なら直 fetch のみ動作(via_worker 指定フィードはエラーになる)。
WORKER_BASE_URL = os.environ.get("WORKER_BASE_URL", "").rstrip("/")
WORKER_TOKEN = os.environ.get("WORKER_TOKEN", "")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_jp_date(s: str) -> Optional[str]:
    """日本語の日付文字列をISO8601(JST)に変換。失敗したらNone。"""
    if not s:
        return None
    s = s.strip()
    fmts = ["%Y/%m/%d", "%Y.%m.%d", "%Y-%m-%d", "%Y年%m月%d日"]
    for f in fmts:
        try:
            jst = timezone(timedelta(hours=9))
            dt = datetime.strptime(s, f).replace(tzinfo=jst)
            return dt.isoformat()
        except ValueError:
            continue
    return None


# =====================================================================
# Title cleaning ヘルパー (update-009)
# =====================================================================

# 末尾に貼られがちな "yyyy/mm/dd" + 「New」「NEW」「new」「新着」バッジ
_TRAILING_DATE_BADGE_RE = re.compile(
    r"\s*(\d{4})[/.\-](\d{1,2})[/.\-](\d{1,2})\s*(?:New|NEW|new|新着)?\s*$"
)


def clean_listing_title(text: str) -> str:
    """リンクテキストから末尾の date / New バッジを除去。

    例: "大阪市淀川区...どう変わるか2026/05/09New" → "大阪市淀川区...どう変わるか"
    """
    if not text:
        return text
    cleaned = _TRAILING_DATE_BADGE_RE.sub("", text).strip()
    return cleaned if cleaned else text.strip()


def _anchor_title_text(a_tag) -> str:
    """anchor から「title らしき」テキストを取り出す。

    update-012: 楽待 /news/practical のような DOM では anchor 内に
    <span>5</span><div>築より立地…</div><span>2026/05/09</span> のように
    ランキング数字・タイトル・日付が並列で並ぶ。`a.get_text(strip=True)`
    でこれを連結すると "5築より立地…2026/05/09" のように先頭に数字が
    張り付いた title になってしまう。

    そこで、anchor の strict descendant 要素のうち最も長いテキストを
    持つ要素のテキストを返す。子要素が無い(直下テキストのみ)場合は
    anchor の get_text() にフォールバックするので、健美家・楽待の他
    セクションのような単純な DOM では振る舞いが事実上変わらない。

    Returns:
        str: 抽出された title 候補テキスト(空文字なら anchor 内が完全に空)
    """
    if a_tag is None:
        return ""

    longest = ""
    for descendant in a_tag.find_all(True):
        # find_all(True) は a_tag 自身を含まず strict descendant のみ返す
        text = descendant.get_text(strip=True)
        if len(text) > len(longest):
            longest = text

    if longest:
        return longest

    # 子要素が無い、または全部空 → anchor 直下の text のみ
    return (a_tag.get_text(strip=True) or "").strip()


def extract_date_from_title(text: str) -> Optional[str]:
    """リンクテキスト末尾の "yyyy/mm/dd" を抽出して ISO8601 で返す。"""
    if not text:
        return None
    m = _TRAILING_DATE_BADGE_RE.search(text)
    if not m:
        return None
    date_str = f"{m.group(1)}/{int(m.group(2)):02d}/{int(m.group(3)):02d}"
    return parse_jp_date(date_str)


# =====================================================================
# ScrapeAdapterBase
# =====================================================================

class ScrapeAdapterBase(SourceAdapter):
    """スクレイピング系アダプターの共通基底クラス。"""

    source_type: str = "scrape_base"
    timeout: int = 20
    retries: int = 2
    retry_delay: float = 1.5

    def __init__(self, timeout: int = 20, user_agent: Optional[str] = None):
        self.timeout = timeout
        self.user_agent = user_agent or DEFAULT_UA

    # -----------------------------------------------------------------
    # 直 fetch (update-008)
    # -----------------------------------------------------------------

    def _build_headers(self, url: str) -> dict:
        headers = dict(DEFAULT_HEADERS)
        headers["User-Agent"] = self.user_agent
        return headers

    def _fetch_html(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """指定URLのHTMLを直接取得。

        Returns:
          (html, error_msg)
          成功時: (html, None)
          失敗時: (None, "HTTP 403" / "timeout" / "ssl: ..." 等)
        """
        last_err: Optional[str] = None

        for attempt in range(self.retries + 1):
            try:
                headers = self._build_headers(url)
                r = requests.get(url, headers=headers, timeout=self.timeout)
                if r.status_code >= 400:
                    last_err = f"HTTP {r.status_code}"
                    if r.status_code in (403, 404, 410, 451, 429, 503):
                        return None, last_err
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

            if attempt < self.retries:
                time.sleep(self.retry_delay * (attempt + 1))

        return None, last_err or "unknown"

    # -----------------------------------------------------------------
    # Worker proxy 経由 fetch (update-009)
    # -----------------------------------------------------------------

    def _fetch_html_via_worker(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """Cloudflare Worker /fetch 経由でHTMLを取得。

        Worker は origin から取得した結果を JSON で包んで返す:
          成功: {"url": ..., "status": 200, "html": "<html>...</html>", ...}
          origin が 4xx/5xx: {"url": ..., "status": 403, "error": "upstream HTTP 403", ...}
          Worker 自体が fetch 失敗: {"error": "fetch error: ...", ...}
        """
        if not WORKER_BASE_URL:
            return None, "worker not configured (WORKER_BASE_URL missing)"
        if not WORKER_TOKEN:
            return None, "worker not configured (WORKER_TOKEN missing)"

        proxy_url = f"{WORKER_BASE_URL}/fetch?url={quote(url, safe='')}"
        worker_timeout = self.timeout * 2
        last_err: Optional[str] = None

        for attempt in range(self.retries + 1):
            try:
                r = requests.get(
                    proxy_url,
                    headers={"Authorization": f"Bearer {WORKER_TOKEN}"},
                    timeout=worker_timeout,
                )
            except requests.exceptions.Timeout:
                last_err = "worker timeout"
                if attempt < self.retries:
                    time.sleep(self.retry_delay * (attempt + 1))
                    continue
                return None, last_err
            except requests.exceptions.ConnectionError as e:
                last_err = f"worker connection: {str(e)[:80]}"
                if attempt < self.retries:
                    time.sleep(self.retry_delay * (attempt + 1))
                    continue
                return None, last_err
            except Exception as e:
                last_err = f"worker unexpected: {type(e).__name__}: {str(e)[:80]}"
                return None, last_err

            if r.status_code == 401:
                return None, "worker HTTP 401 (token mismatch)"
            if r.status_code != 200:
                return None, f"worker HTTP {r.status_code}"

            try:
                data = r.json()
            except Exception:
                return None, "worker returned non-JSON"

            html = data.get("html")
            upstream_status = data.get("status")

            if html:
                return html, None

            if upstream_status and upstream_status >= 400:
                err_msg = f"via worker: upstream HTTP {upstream_status}"
                if 400 <= upstream_status < 500 and upstream_status not in (408, 429):
                    return None, err_msg
                last_err = err_msg
            else:
                err_detail = (data.get("error") or "no html")[:80]
                last_err = f"via worker: {err_detail}"

            if attempt < self.retries:
                time.sleep(self.retry_delay * (attempt + 1))

        return None, last_err or "via worker: unknown"

    # -----------------------------------------------------------------
    # リスティング解析の共通ヘルパー (update-009)
    # -----------------------------------------------------------------

    @staticmethod
    def extract_listing_links(
        soup: BeautifulSoup,
        base_url: str,
        article_pattern: re.Pattern,
        normalize_url: Optional[Callable[[str], str]] = None,
    ) -> dict:
        """リスティングページから記事リンクを集約する。

        各記事に対して thumbnail link(text 空)+ title link が同じ URL を
        指して並ぶケースが多く、document order の素朴な dedup では title 側を
        捨ててしまう。本ヘルパーは「URL → 最も長いリンクテキストを持つ <a>」を
        返すので、この問題が起きない。

        update-012:
            anchor 内のテキスト抽出は `_anchor_title_text()` に委譲する。
            anchor 内に <span>5</span><div>築より立地…</div> のような複数の
            子要素が並ぶ場合、`a.get_text(strip=True)` だと "5築より立地…"
            のように連結してしまうため、最長子要素のテキストを title として
            採用する戦略に変更。

        Returns:
            dict: {absolute_url: (longest_text, anchor_tag)}
        """
        url_to_link: dict = {}
        for a in soup.find_all("a", href=True):
            absolute = urljoin(base_url, a["href"])
            if normalize_url:
                absolute = normalize_url(absolute)
            if not article_pattern.match(absolute):
                continue
            text = _anchor_title_text(a)
            existing = url_to_link.get(absolute)
            if existing is None or len(text) > len(existing[0]):
                url_to_link[absolute] = (text, a)
        return url_to_link

    # -----------------------------------------------------------------
    # メイン fetch エントリポイント
    # -----------------------------------------------------------------

    def fetch(self, feed: dict) -> tuple[list[Article], dict]:
        """feeds.json の1エントリから記事リストを取得。"""
        meta_update = {"last_fetch": now_iso()}
        url = feed["url"]

        # via_worker: True なら Worker proxy 経由、それ以外は直 fetch
        if feed.get("via_worker"):
            html, err = self._fetch_html_via_worker(url)
        else:
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
        # update-009: items_count を追跡することでサイレント失敗(parser破損)を検知可能に
        meta_update["last_items_count"] = len(articles)
        return articles, meta_update

    def parse_listing(self, soup: BeautifulSoup, base_url: str, feed: dict) -> list[dict]:
        raise NotImplementedError
