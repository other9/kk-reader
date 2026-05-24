"""
Foreign Affairs Japan (foreignaffairsj.co.jp) スクレイパー。

対象 URL: https://www.foreignaffairsj.co.jp/articles/
認証: セッション Cookie (環境変数 FOREIGNAFFAIRSJ_COOKIE)

Cookie が未設定の場合でも無料公開記事は取得できる。
Cookie が設定されている場合、購読者限定記事を含む全記事が取得対象になる。

Cookie の取得方法:
  1. ブラウザで https://www.foreignaffairsj.co.jp/login/ にログイン
  2. DevTools → Network タブ → 任意のリクエストを選択
  3. Request Headers の Cookie 行の値をコピー
  4. GitHub Secrets に FOREIGNAFFAIRSJ_COOKIE として保存

Cookie 有効期限:
  セッション Cookie は数週間〜数ヶ月で失効する。失効すると
  last_error に HTTP 403 または 0 件取得が記録される。
  その場合は上記手順で Cookie を再取得すること。

記事 URL パターン: /articles/YYYYMM_slug/
  例: /articles/202607_rose/  → 2026年7月号
"""
import os
import re
from datetime import timezone, timedelta, datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .scrape_base import ScrapeAdapterBase

_ARTICLE_RE = re.compile(
    r"^https?://(?:www\.)?foreignaffairsj\.co\.jp/articles/(\d{6})_[a-z0-9_-]+/?$",
    re.IGNORECASE,
)
_JST = timezone(timedelta(hours=9))


def _date_from_url(url: str) -> str | None:
    """URL の YYYYMM 部分から ISO8601 日付文字列を生成。"""
    m = _ARTICLE_RE.match(url)
    if not m:
        return None
    ym = m.group(1)
    try:
        dt = datetime(int(ym[:4]), int(ym[4:6]), 1, tzinfo=_JST)
        return dt.isoformat()
    except ValueError:
        return None


class ForeignAffairsJAdapter(ScrapeAdapterBase):
    source_type = "scrape_foreignaffairsj"

    def _build_headers(self, url: str) -> dict:
        headers = super()._build_headers(url)
        cookie = os.environ.get("FOREIGNAFFAIRSJ_COOKIE", "").strip()
        if cookie:
            headers["Cookie"] = cookie
        return headers

    def parse_listing(self, soup: BeautifulSoup, base_url: str, feed: dict) -> list[dict]:
        items = []
        seen = set()
        for h3 in soup.find_all("h3"):
            a = h3.find("a", href=True)
            if not a:
                continue
            href = urljoin(base_url, a["href"])
            # 末尾スラッシュを正規化
            href = href.rstrip("/")
            if not _ARTICLE_RE.match(href + "/"):
                continue
            if href in seen:
                continue
            seen.add(href)

            title = a.get_text(separator=" ", strip=True)
            if not title:
                continue

            # h3 直後の兄弟 p タグを要約として使う
            summary = ""
            sibling = h3.find_next_sibling()
            if sibling and sibling.name == "p":
                summary = sibling.get_text(strip=True)

            items.append({
                "url": href,
                "title": title,
                "published": _date_from_url(href + "/"),
                "author": None,
                "summary": summary,
            })

        return items