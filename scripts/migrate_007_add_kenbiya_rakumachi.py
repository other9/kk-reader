#!/usr/bin/env python3
"""
update-007: 健美家・楽待 のスクレイピング系フィードを feeds.json に追加。

このスクリプトは冪等で、既に追加済みのエントリは重複追加しません。
既存フィードの状態(active, error_count, last_fetch等)は一切変更しません。
"""
import json
import sys
from pathlib import Path
import hashlib

PROJECT_ROOT = Path(__file__).parent.parent
FEEDS_PATH = PROJECT_ROOT / "docs" / "data" / "feeds.json"


def feed_id(url: str) -> str:
    return hashlib.md5(url.encode("utf-8")).hexdigest()[:12]


# 追加するフィード(OPML と同じ4エントリ)
NEW_FEEDS_BASE = [
    {
        "title": "健美家 コラム&ニュース",
        "url": "https://www.kenbiya.com/ar/",
        "html_url": "https://www.kenbiya.com/",
        "category": "不動産",
        "source_type": "scrape_kenbiya",
    },
    {
        "title": "楽待新聞 編集部記事",
        "url": "https://www.rakumachi.jp/news/column",
        "html_url": "https://www.rakumachi.jp/news/",
        "category": "不動産",
        "source_type": "scrape_rakumachi",
    },
    {
        "title": "楽待新聞 連載コラム",
        "url": "https://www.rakumachi.jp/news/series",
        "html_url": "https://www.rakumachi.jp/news/series",
        "category": "不動産",
        "source_type": "scrape_rakumachi",
    },
    {
        "title": "楽待 実践大家コラム",
        "url": "https://www.rakumachi.jp/news/practical",
        "html_url": "https://www.rakumachi.jp/news/practical",
        "category": "不動産",
        "source_type": "scrape_rakumachi",
    },
]


def main():
    if not FEEDS_PATH.exists():
        print(f"エラー: {FEEDS_PATH} が見つかりません。")
        sys.exit(1)

    with open(FEEDS_PATH, encoding="utf-8") as f:
        data = json.load(f)

    existing_urls = {feed["url"] for feed in data["feeds"]}
    added_count = 0

    for base in NEW_FEEDS_BASE:
        if base["url"] in existing_urls:
            print(f"  既に存在: {base['title']}")
            continue

        new_feed = {
            "id": feed_id(base["url"]),
            "title": base["title"],
            "url": base["url"],
            "html_url": base["html_url"],
            "category": base["category"],
            "source_type": base["source_type"],
            "active": True,
            "verify_ssl": True,
            "etag": None,
            "last_modified": None,
            "last_fetch": None,
            "last_success": None,
            "error_count": 0,
            "last_error": None,
        }
        data["feeds"].append(new_feed)
        added_count += 1
        print(f"  追加: {base['title']} ({base['source_type']})")

    # カテゴリ集計を再構築
    categories = sorted({f["category"] for f in data["feeds"]})
    data["categories"] = categories

    # ソートも以前と同じパターンに揃える(category → title 順)
    data["feeds"].sort(key=lambda f: (f["category"], f["title"]))

    with open(FEEDS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"\n完了: 新規 {added_count} 件追加。総数 {len(data['feeds'])} 件。")


if __name__ == "__main__":
    main()
