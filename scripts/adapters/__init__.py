"""
ソースアダプター群。
将来、メール、スクレイピング、Cookie認証取得などを追加する場合、
adapters/ 配下に新しいファイルを追加し、ADAPTERSに登録する。
"""
from .base import SourceAdapter, Article, make_article_id
from .rss_adapter import RSSAdapter

# source_type → アダプターインスタンスのマッピング
ADAPTERS: dict[str, SourceAdapter] = {
    "rss": RSSAdapter(),
}

__all__ = ["SourceAdapter", "Article", "make_article_id", "RSSAdapter", "ADAPTERS"]
