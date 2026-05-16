"""
update-016 用 migration: CFA Society Japan ブログの feed エントリに
`via_worker: true` を立てる。

opml_to_feeds.py が新規 feed として entry を作る際は via_worker は付与しない
(OPML_OWNED_FIELDS にない field の初期値は付与されないため)。Higher Logic +
Cloudflare CDN 構成のサイトに対しては GitHub Actions の outbound IP からの直
fetch で 403 を踏むリスクがあるため、初手から Worker proxy 経由(`/fetch`)で
取りに行く構成にする。

実行は idempotent。何度走らせても結果は同じ。

更新履歴:
- 2026-05-16 (update-016):   初版
- 2026-05-16 (update-016.1): feeds.json の構造を `{"feeds": [...]}` に修正
                              (初版は top-level list と誤推定して
                               'str' object has no attribute 'get' で死亡)
"""
import json
import sys
from pathlib import Path


FEEDS_PATH = Path("docs/data/feeds.json")
TARGET_SOURCE_TYPE = "scrape_cfajapan"


def main() -> int:
    if not FEEDS_PATH.exists():
        print(f"ERROR: {FEEDS_PATH} が存在しません。先に opml_to_feeds.py を実行してください。",
              file=sys.stderr)
        return 1

    with FEEDS_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict) or "feeds" not in data:
        print(f"ERROR: {FEEDS_PATH} の構造が想定外です(top-level に 'feeds' キーがない)。",
              file=sys.stderr)
        return 1

    feeds = data["feeds"]
    if not isinstance(feeds, list):
        print(f"ERROR: data['feeds'] が list ではありません。", file=sys.stderr)
        return 1

    changed = 0
    targeted = 0
    for feed in feeds:
        if not isinstance(feed, dict):
            continue
        if feed.get("source_type") != TARGET_SOURCE_TYPE:
            continue
        targeted += 1
        if feed.get("via_worker") is True:
            continue
        feed["via_worker"] = True
        changed += 1
        print(f"  via_worker=true → {feed.get('title', '?')} ({feed.get('id', '?')})")

    if targeted == 0:
        print(f"WARNING: source_type={TARGET_SOURCE_TYPE} のフィードが見つかりません。",
              file=sys.stderr)
        print("opml_to_feeds.py が新規 entry を作成済みか確認してください。", file=sys.stderr)
        return 1

    if changed == 0:
        print(f"既に全 {targeted} 件で via_worker=true 設定済み。変更なし。")
        return 0

    with FEEDS_PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"{changed}/{targeted} 件を更新しました。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
