"""
RSS/Atomフィード用アダプター。

更新履歴:
- 2026-05-06: ブラウザ偽装UA、パースリカバリ、SSL検証スキップ対応
"""
import re
import requests
import feedparser
import urllib3
from datetime import datetime, timezone
from typing import Optional
from html import unescape

from .base import SourceAdapter, Article, make_article_id


# 多くのフィードサイトはbot系UAを拒否するため、Chrome系を偽装する
DEFAULT_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/121.0.0.0 Safari/537.36"
)


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
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "…"
    return text


def parse_with_recovery(content: bytes):
    """フィードパース。失敗時は段階的にリカバリを試みる。

    試行順:
      1. 標準パース
      2. 制御文字を除去してリトライ
      3. lxmlのrecoverモードでXML修復後にリトライ
    """
    # 試行1: 標準パース
    parsed = feedparser.parse(content)
    if parsed.entries:
        return parsed

    # 試行2: 制御文字除去
    try:
        cleaned = re.sub(rb'[\x00-\x08\x0B-\x0C\x0E-\x1F]', b'', content)
        parsed_clean = feedparser.parse(cleaned)
        if parsed_clean.entries:
            return parsed_clean
    except Exception:
        cleaned = content

    # 試行3: lxml recover
    try:
        from lxml import etree
        parser = etree.XMLParser(recover=True)
        tree = etree.fromstring(cleaned, parser=parser)
        if tree is not None:
            recovered = etree.tostring(tree, encoding="utf-8", xml_declaration=True)
            parsed_recover = feedparser.parse(recovered)
            if parsed_recover.entries:
                return parsed_recover
    except Exception:
        pass

    return parsed  # 最終的に最初の結果を返す(エラー扱いされる)


class RSSAdapter(SourceAdapter):
    source_type = "rss"

    def __init__(self, timeout: int = 15, user_agent: str = DEFAULT_UA):
        self.timeout = timeout
        self.user_agent = user_agent

    def fetch(self, feed: dict) -> tuple[list[Article], dict]:
        url = feed["url"]
        verify_ssl = feed.get("verify_ssl", True)
        meta_update = {
            "last_fetch": now_iso(),
        }

        # 条件付きGET用ヘッダー
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*;q=0.8",
            "Accept-Language": "ja,en-US;q=0.7,en;q=0.3",
        }
        if feed.get("etag"):
            headers["If-None-Match"] = feed["etag"]
        if feed.get("last_modified"):
            headers["If-Modified-Since"] = feed["last_modified"]

        # SSL検証無効化時の警告抑制
        if not verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        try:
            resp = requests.get(
                url,
                headers=headers,
                timeout=self.timeout,
                allow_redirects=True,
                verify=verify_ssl,
            )
        except Exception as e:
            meta_update["error_count"] = feed.get("error_count", 0) + 1
            meta_update["last_error"] = f"接続エラー: {type(e).__name__}: {str(e)[:200]}"
            return [], meta_update

        if resp.status_code == 304:
            meta_update["last_success"] = now_iso()
            meta_update["error_count"] = 0
            meta_update["last_error"] = None
            return [], meta_update

        if resp.status_code >= 400:
            meta_update["error_count"] = feed.get("error_count", 0) + 1
            meta_update["last_error"] = f"HTTP {resp.status_code}"
            return [], meta_update

        if resp.headers.get("ETag"):
            meta_update["etag"] = resp.headers["ETag"]
        if resp.headers.get("Last-Modified"):
            meta_update["last_modified"] = resp.headers["Last-Modified"]

        # パース(段階的リカバリ付き)
        parsed = parse_with_recovery(resp.content)
        if not parsed.entries:
            meta_update["error_count"] = feed.get("error_count", 0) + 1
            err = getattr(parsed, "bozo_exception", "エントリ抽出に失敗")
            meta_update["last_error"] = f"パースエラー: {str(err)[:200]}"
            return [], meta_update

        articles = []
        for entry in parsed.entries[:60]:
            entry_url = entry.get("link") or ""
            guid = entry.get("id") or entry.get("guid")
            if not entry_url and not guid:
                continue
            article_id = make_article_id(entry_url or guid, guid)

            published = parse_struct_time(entry.get("published_parsed")) \
                or parse_struct_time(entry.get("updated_parsed"))

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
