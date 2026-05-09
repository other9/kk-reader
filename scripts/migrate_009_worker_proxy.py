#!/usr/bin/env python3
"""
update-009 マイグレーション: 楽待を Worker proxy 経由に切り替え。

このスクリプトは feeds.json を更新するだけ。コード変更(scrape_base.py、
worker/worker.js、.github/workflows/fetch-feeds.yml)は ZIP 展開時点で
適用済み前提。

具体的な変更:
  rakumachi.jp の各フィードについて:
    active        → True  (auto-disable されていたので復活)
    via_worker    → True  (Worker /fetch 経由で取得)
    error_count   → 0     (リセット)
    last_error    → None  (リセット)

冪等: 既に適用済みでも安全に再実行できる。
"""
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
FEEDS_PATH = PROJECT_ROOT / "docs" / "data" / "feeds.json"

RAKUMACHI_PREFIX = "https://www.rakumachi.jp/news/"


def main():
    if not FEEDS_PATH.exists():
        print(f"エラー: {FEEDS_PATH} が見つかりません", file=sys.stderr)
        sys.exit(1)

    with open(FEEDS_PATH, encoding="utf-8") as f:
        data = json.load(f)

    feeds = data["feeds"]
    rakumachi_feeds = [fd for fd in feeds if fd.get("url", "").startswith(RAKUMACHI_PREFIX)]

    if not rakumachi_feeds:
        print("rakumachi フィードが feeds.json に存在しません。何もしません。")
        return

    print(f"対象: {len(rakumachi_feeds)} 個の rakumachi フィードを Worker proxy 経由に切替")
    changed = 0
    for fd in rakumachi_feeds:
        before = (
            fd.get("active", True),
            fd.get("via_worker", False),
            fd.get("error_count", 0),
            fd.get("last_error"),
        )
        fd["active"] = True
        fd["via_worker"] = True
        fd["error_count"] = 0
        fd["last_error"] = None
        after = (True, True, 0, None)

        marker = "→ 更新" if before != after else "  (変更なし)"
        print(f"  {marker} {fd['title']}")
        if before != after:
            changed += 1

    if changed == 0:
        print("\n全フィード既に適用済みです。feeds.json は touch しません。")
        return

    with open(FEEDS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n{changed} フィードを更新しました。")
    print("\n次のステップ:")
    print("  1. cd worker && wrangler deploy && cd ..   # Worker /fetch を有効化")
    print("  2. gh secret set WORKER_TOKEN              # SYNC_SECRET と同値で開始")
    print("  3. git add -A && git commit -m '...' && git push")
    print("  4. Actions の workflow_dispatch で手動実行 or cron 待ち")
    print("  5. 動作確認は UPDATE.md 参照")


if __name__ == "__main__":
    main()
