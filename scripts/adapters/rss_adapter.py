"""
RSS/Atomフィード用アダプター。
"""
import re
import requests
import feedparser
from datetime import datetime, timezone
from typing import Optional
from html import unescape

from .base import SourceAdapter, Article, make_article_id


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_struct_time(t) -> Optional[str]:
    """feedparserのstruct_timeをISO8601文字列に変換"""
    if t is None:
        return None
    try:
        dt = datetime(*t[:6], tzinfo=timezone.utc)
        return dt.isoformat()
    except Exception:
        return None


def strip_html(html: str, max_chars: int = 280) -> str:
    """HTMLタグを除去してプレーンテキストの要約を作る"""
    if not html:
        return ""
    # スクリプト/スタイルブロックを除去
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # タグ除去
    text = re.sub(r"<[^>]+>", " ", text)
    # HTMLエンティティのデコード
    text = unescape(text)
    # 連続する空白の正規化
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "…"
    return text


class RSSAdapter(SourceAdapter):
    source_type = "rss"

    def __init__(self, timeout: int = 15, user_agent: str = "kk-reader/1.0 (personal RSS aggregator)"):
        self.timeout = timeout
        self.user_agent = user_agent

    def fetch(self, feed: dict) -> tuple[list[Article], dict]:
        url = feed["url"]
        meta_update = {
            "last_fetch": now_iso(),
        }

        # 条件付きGET用ヘッダー
        headers = {"User-Agent": self.user_agent}
        if feed.get("etag"):
            headers["If-None-Match"] = feed["etag"]
        if feed.get("last_modified"):
            headers["If-Modified-Since"] = feed["last_modified"]

        try:
            resp = requests.get(url, headers=headers, timeout=self.timeout, allow_redirects=True)
        except Exception as e:
            meta_update["error_count"] = feed.get("error_count", 0) + 1
            meta_update["last_error"] = f"接続エラー: {type(e).__name__}: {str(e)[:200]}"
            return [], meta_update

        # 304 Not Modified
        if resp.status_code == 304:
            meta_update["last_success"] = now_iso()
            meta_update["error_count"] = 0
            meta_update["last_error"] = None
            return [], meta_update

        if resp.status_code >= 400:
            meta_update["error_count"] = feed.get("error_count", 0) + 1
            meta_update["last_error"] = f"HTTP {resp.status_code}"
            return [], meta_update

        # ETag/Last-Modifiedを保存
        if resp.headers.get("ETag"):
            meta_update["etag"] = resp.headers["ETag"]
        if resp.headers.get("Last-Modified"):
            meta_update["last_modified"] = resp.headers["Last-Modified"]

        # パース
        parsed = feedparser.parse(resp.content)
        if parsed.bozo and not parsed.entries:
            meta_update["error_count"] = feed.get("error_count", 0) + 1
            err = getattr(parsed, "bozo_exception", "不明なパースエラー")
            meta_update["last_error"] = f"パースエラー: {str(err)[:200]}"
            return [], meta_update

        articles = []
        for entry in parsed.entries[:60]:  # 1フィードあたり最大60件
            entry_url = entry.get("link") or ""
            guid = entry.get("id") or entry.get("guid")
            if not entry_url and not guid:
                continue
            article_id = make_article_id(entry_url or guid, guid)

            # 公開日
            published = parse_struct_time(entry.get("published_parsed")) \
                or parse_struct_time(entry.get("updated_parsed"))

            # 本文取得(content > summary)
            content_html = None
            if entry.get("content"):
                content_html = entry.content[0].get("value") if entry.content else None
            if not content_html:
                content_html = entry.get("summary") or entry.get("description") or ""

            summary_text = strip_html(content_html, max_chars=280)

            articles.append(Article(
                id=article_id,
                feed_id=feed["id"],
                feed_title=feed["title"],
                category=feed.get("category", "未分類"),
                title=strip_html(entry.get("title", ""), max_chars=300) or "(無題)",
                url=entry_url,
                published=published,
                fetched=now_iso(),
                summary=summary_text,
                content_html=content_html if content_html else None,
                author=entry.get("author"),
                source_type="rss",
            ))

        meta_update["last_success"] = now_iso()
        meta_update["error_count"] = 0
        meta_update["last_error"] = None
        return articles, meta_update
