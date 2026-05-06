#!/usr/bin/env python3
"""
OPMLファイルを feeds.json に変換する一回限りのスクリプト。
新しい購読を追加した OPML をエクスポートしたら再実行する。
既存の feeds.json があれば、メタデータ(last_fetch, active, verify_ssl等)を保持してマージする。
"""
import json
import hashlib
import xml.etree.ElementTree as ET
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
OPML_PATH = PROJECT_ROOT / "opml" / "subscriptions.opml"
FEEDS_JSON_PATH = PROJECT_ROOT / "docs" / "data" / "feeds.json"


def feed_id(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


def parse_opml(path: Path) -> list[dict]:
    tree = ET.parse(path)
    body = tree.getroot().find("body")
    feeds = []

    def walk(node, category):
        for child in node.findall("outline"):
            if child.get("type") == "rss":
                xml_url = child.get("xmlUrl") or ""
                if not xml_url:
                    continue
                feeds.append({
                    "id": feed_id(xml_url),
                    "title": child.get("title") or child.get("text") or xml_url,
                    "url": xml_url,
                    "html_url": child.get("htmlUrl") or "",
                    "category": category,
                    "source_type": "rss",
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
                feed["etag"] = old.get("etag")
                feed["last_modified"] = old.get("last_modified")
                feed["last_fetch"] = old.get("last_fetch")
                feed["last_success"] = old.get("last_success")
                feed["error_count"] = old.get("error_count", 0)
                feed["last_error"] = old.get("last_error")
                feed["active"] = old.get("active", True)
                feed["verify_ssl"] = old.get("verify_ssl", True)
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
