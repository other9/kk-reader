#!/usr/bin/env python3
"""
OPMLファイルを feeds.json に変換する一回限りのスクリプト。
新しい購読を追加した OPML をエクスポートしたら再実行する。
既存の feeds.json があれば、メタデータ(last_fetch, active, via_worker等)を保持してマージする。

更新履歴:
- 2026-05-09 (update-009.1): merge ロジックを「OPML 由来でない全フィールドを保持」方式に変更。
  以前は明示的な allowlist だったため、migrate スクリプトが追加した `via_worker` 等の
  config field が Actions の checkout 後に rebuild された際に消える事故が発生していた。
  これに伴い `last_items_count` 等の状態 field も自動で保持されるようになる。
"""
import json
import hashlib
import xml.etree.ElementTree as ET
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
OPML_PATH = PROJECT_ROOT / "opml" / "subscriptions.opml"
FEEDS_JSON_PATH = PROJECT_ROOT / "docs" / "data" / "feeds.json"

# OPML が source of truth として持つ field。これらは rebuild 時に OPML から
# 上書きされる。これら以外は既存の feeds.json から保持する。
OPML_OWNED_FIELDS = {"id", "title", "url", "html_url", "category", "source_type"}


def feed_id(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


def parse_opml(path: Path) -> list[dict]:
    tree = ET.parse(path)
    body = tree.getroot().find("body")
    feeds = []

    def walk(node, category):
        for child in node.findall("outline"):
            outline_type = child.get("type") or ""
            # rss と scrape_* (健美家・楽待等のスクレイピング系) を扱う
            if outline_type == "rss" or outline_type.startswith("scrape_"):
                xml_url = child.get("xmlUrl") or ""
                if not xml_url:
                    continue
                feeds.append({
                    "id": feed_id(xml_url),
                    "title": child.get("title") or child.get("text") or xml_url,
                    "url": xml_url,
                    "html_url": child.get("htmlUrl") or "",
                    "category": category,
                    "source_type": outline_type or "rss",
                    "active": True,
                    "verify_ssl": True,
                    "etag": None,
                    "last_modified": None,
                    "last_fetch": None,
                    "last_success": None,
                    "error_count": 0,
                    "last_error": None,
                })
            else:
                folder_name = child.get("title") or child.get("text") or "未分類"
                walk(child, folder_name)

    walk(body, "未分類")
    return feeds


def main():
    feeds = parse_opml(OPML_PATH)
    print(f"OPMLから {len(feeds)} 件のフィードを読み込みました")

    if FEEDS_JSON_PATH.exists():
        with open(FEEDS_JSON_PATH, encoding="utf-8") as f:
            existing = json.load(f)
        existing_by_id = {f["id"]: f for f in existing.get("feeds", [])}
        for feed in feeds:
            if feed["id"] in existing_by_id:
                old = existing_by_id[feed["id"]]
                # OPML 由来でない全フィールドを保持(via_worker 等の config / 状態 field 含む)
                for k, v in old.items():
                    if k not in OPML_OWNED_FIELDS:
                        feed[k] = v
        print(f"既存の {len(existing_by_id)} 件とメタデータをマージしました")

    categories = sorted({f["category"] for f in feeds})
    feeds.sort(key=lambda f: (f["category"], f["title"]))

    output = {
        "feeds": feeds,
        "categories": categories,
        "total": len(feeds),
    }

    FEEDS_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(FEEDS_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"書き出し: {FEEDS_JSON_PATH}")
    print(f"カテゴリ: {categories}")


if __name__ == "__main__":
    main()
