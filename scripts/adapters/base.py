"""
ソースアダプターの基底クラス。
新しいソース(メール、Cookie認証取得、スクレイピング等)を追加する場合、
このクラスを継承して fetch() を実装する。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from typing import Optional
import hashlib


@dataclass
class Article:
    """全アダプター共通の正規化済み記事スキーマ"""
    id: str                    # ユニークID(URL or GUIDのハッシュ)
    feed_id: str               # 元フィードのID
    feed_title: str            # 元フィードのタイトル(UI表示用に冗長保存)
    category: str              # カテゴリ(UI表示用に冗長保存)
    title: str                 # 記事タイトル
    url: str                   # 元記事のURL
    published: Optional[str]   # ISO8601、不明ならNone
    fetched: str               # ISO8601、取得時刻
    summary: str               # 要約またはリード(プレーンテキスト、200字程度)
    content_html: Optional[str]  # 全文HTML、なければNone
    author: Optional[str]
    source_type: str           # "rss", "email", "scrape" 等

    def to_dict(self) -> dict:
        return asdict(self)


def make_article_id(url: str, guid: Optional[str] = None) -> str:
    """記事のユニークIDを生成。GUIDがあればそれを優先、なければURLのハッシュ。"""
    seed = guid if guid else url
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]


class SourceAdapter(ABC):
    """ソースアダプター基底クラス"""

    source_type: str = "unknown"

    @abstractmethod
    def fetch(self, feed: dict) -> tuple[list[Article], dict]:
        """
        指定フィードから記事を取得する。

        Args:
            feed: feeds.jsonの1エントリ(dict)

        Returns:
            (articles, updated_feed_meta)
            - articles: 取得した記事のリスト
            - updated_feed_meta: 更新するフィードメタデータ
              (etag, last_modified, last_fetch, last_success, error_count, last_error など)
        """
        pass
