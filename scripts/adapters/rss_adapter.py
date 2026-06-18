"""
RSS/Atomフィード用アダプター。

更新履歴:
- 2026-05-06: ブラウザ偽装UA、パースリカバリ、SSL検証スキップ対応
- 2026-06-16 (update-019): via_worker 対応を追加。feeds.json で via_worker:true の
  RSS フィードは Cloudflare Worker /fetch 経由で取得する。楽待(rakumachi.jp)が
  Actions IP も Worker IP も WAF で弾くようになったが、HTML 用 scrape_base では
  Worker proxy しか持っていなかった。RSS に移行したフィードでも Actions 直 fetch が
  403 になるため、RSS アダプタにも同じ Worker proxy 経路を持たせる。
"""
import os
import re
import time
import requests
import feedparser
import urllib3
from datetime import datetime, timezone
from typing import Optional, Tuple
from urllib.parse import quote
from html import unescape

from .base import SourceAdapter, Article, make_article_id


# Worker proxy 設定 (update-019)。GitHub Actions では fetch-feeds.yml で env として渡される。
WORKER_BASE_URL = os.environ.get("WORKER_BASE_URL", "").rstrip("/")
WORKER_TOKEN = os.environ.get("WORKER_TOKEN", "")


# 多くのフィードサイトはbot系UAを拒否するため、Chrome系を偽装する
DEFAULT_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/121.0.0.0 Safari/537.36"
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_bytes_via_worker(
    url: str, timeout: int = 15, retries: int = 2, retry_delay: float = 1.5,
    user_agent: Optional[str] = None,
) -> Tuple[Optional[bytes], Optional[str]]:
    """Cloudflare Worker /fetch 経由で生レスポンスを取得し bytes で返す。

    Worker は origin の body を decode 済みの文字列(JSON の "html" フィールド)で
    返すため、feedparser / parse_with_recovery に渡せるよう UTF-8 bytes に再エンコード
    する(RSS は UTF-8 前提)。scrape_base._fetch_html_via_worker と同じ契約。

    user_agent を渡すと Worker /fetch の `ua` クエリ引数で origin への
    User-Agent を上書きする(update-019: 楽待 Bot Management 対策の feed-reader UA)。

    Returns: (content_bytes, error_msg)
    """
    if not WORKER_BASE_URL:
        return None, "worker not configured (WORKER_BASE_URL missing)"
    if not WORKER_TOKEN:
        return None, "worker not configured (WORKER_TOKEN missing)"

    proxy_url = f"{WORKER_BASE_URL}/fetch?url={quote(url, safe='')}"
    if user_agent:
        proxy_url += f"&ua={quote(user_agent, safe='')}"
    last_err: Optional[str] = None

    for attempt in range(retries + 1):
        try:
            r = requests.get(
                proxy_url,
                headers={"Authorization": f"Bearer {WORKER_TOKEN}"},
                timeout=timeout * 2,
            )
        except requests.exceptions.RequestException as e:
            last_err = f"worker {type(e).__name__}: {str(e)[:80]}"
            if attempt < retries:
                time.sleep(retry_delay * (attempt + 1))
                continue
            return None, last_err

        if r.status_code == 401:
            return None, "worker HTTP 401 (token mismatch)"
        if r.status_code != 200:
            return None, f"worker HTTP {r.status_code}"

        try:
            data = r.json()
        except Exception:
            return None, "worker returned non-JSON"

        body = data.get("html")
        upstream_status = data.get("status")
        if body:
            return body.encode("utf-8"), None

        if upstream_status and upstream_status >= 400:
            err_msg = f"via worker: upstream HTTP {upstream_status}"
            if 400 <= upstream_status < 500 and upstream_status not in (408, 429):
                return None, err_msg
            last_err = err_msg
        else:
            last_err = f"via worker: {(data.get('error') or 'no body')[:80]}"

        if attempt < retries:
            time.sleep(retry_delay * (attempt + 1))

    return None, last_err or "via worker: unknown"


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

    def fetch(
        self, feed: dict, known_body_ids: Optional[set] = None
    ) -> tuple[list[Article], dict]:
        # known_body_ids は RSS では未使用(本文はフィード本体に同梱されるため)。
        url = feed["url"]
        verify_ssl = feed.get("verify_ssl", True)
        meta_update = {
            "last_fetch": now_iso(),
        }

        # via_worker:true のフィードは Cloudflare Worker /fetch 経由で取得する。
        # (update-019) 楽待のように Actions IP を WAF で弾くサイト用。条件付き GET
        # (etag/last-modified)は Worker proxy では使えないため毎回フル取得になる。
        # feed 単位の User-Agent 上書き。楽待のように datacenter IP × ブラウザ詐称UA
        # を Bot Management で弾くサイト向けに、正直な feed-reader UA を指定できる。
        ua = feed.get("user_agent") or self.user_agent

        if feed.get("via_worker"):
            content, err = fetch_bytes_via_worker(
                url, timeout=self.timeout, user_agent=feed.get("user_agent")
            )
            if content is None:
                meta_update["error_count"] = feed.get("error_count", 0) + 1
                meta_update["last_error"] = err or "via worker: fetch failed"
                return [], meta_update
        else:
            # 条件付きGET用ヘッダー
            headers = {
                "User-Agent": ua,
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

            content = resp.content

        # パース(段階的リカバリ付き)
        parsed = parse_with_recovery(content)
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
