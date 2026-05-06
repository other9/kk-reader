#!/usr/bin/env python3
"""
取得失敗フィードの診断ツール。
カテゴリ別にエラーを集計し、対応方針の判断材料を提示する。
"""
import json
import sys
from pathlib import Path
from collections import defaultdict

PROJECT_ROOT = Path(__file__).parent.parent
FEEDS_PATH = PROJECT_ROOT / "docs" / "data" / "feeds.json"


def categorize(err: str) -> tuple[str, str]:
    e = err.lower()
    if "http 404" in e:
        return ("404", "URL消滅 - 新しいフィードURLを探す or 無効化")
    if "http 403" in e:
        return ("403", "アクセス拒否 - User-Agent変更で改善の可能性")
    if "http 410" in e:
        return ("410", "サービス終了 - 無効化推奨")
    if "http 401" in e:
        return ("401", "認証要求 - Cookie/Basic認証アダプターが必要")
    if "http 5" in e:
        return ("5xx", "サーバーエラー - 一時的なら待つ")
    if "ssl" in e or "certificate" in e:
        return ("SSL", "証明書問題 - サイト管理者対応待ち")
    if "connection" in e or "name or service" in e or "nodename" in e or "name resolution" in e:
        return ("接続", "DNS/サイト消滅 - 無効化推奨")
    if "timeout" in e:
        return ("タイムアウト", "サーバー遅延 - 様子見")
    if "parse" in e or "bozo" in e:
        return ("パース", "形式不正 - サイト確認")
    return ("その他", err[:80])


def main():
    if not FEEDS_PATH.exists():
        print(f"エラー: {FEEDS_PATH} が見つかりません")
        sys.exit(1)

    with open(FEEDS_PATH, encoding="utf-8") as f:
        data = json.load(f)

    feeds = data["feeds"]
    failed = [fd for fd in feeds if fd.get("last_error")]
    success = [fd for fd in feeds if not fd.get("last_error") and fd.get("last_success")]
    never = [fd for fd in feeds if not fd.get("last_fetch")]

    print(f"=== 取得状況サマリ ===")
    print(f"全 {len(feeds)} フィード: 成功 {len(success)} / 失敗 {len(failed)} / 未取得 {len(never)}\n")

    if not failed:
        print("失敗なし。問題ありません。")
        return

    groups = defaultdict(list)
    for fd in failed:
        cat, desc = categorize(fd["last_error"])
        groups[(cat, desc)].append(fd)

    print(f"=== 失敗の内訳 (原因別) ===")
    for (cat, desc), fs in sorted(groups.items(), key=lambda x: -len(x[1])):
        print(f"\n■ [{cat}] {desc} — {len(fs)}件")
        for fd in fs:
            err_count = fd.get("error_count", 0)
            marker = " ★無効化対象" if err_count >= 10 else ""
            print(f"  • [{fd['category']}] {fd['title']}{marker}")
            print(f"    URL: {fd['url']}")
            print(f"    エラー: {fd['last_error']}")
            print(f"    連続失敗: {err_count}回")
            if fd.get("html_url"):
                print(f"    サイト: {fd['html_url']}")

    print(f"\n=== 推奨アクション ===")
    print(f"無効化候補(連続10回以上失敗): {sum(1 for fd in failed if fd.get('error_count', 0) >= 10)}件")
    print(f"\nfeeds.json を編集して `\"active\": false` にすることで明示的に無効化できます。")
    print(f"または、opml/subscriptions.opml から該当エントリを削除してください。")


if __name__ == "__main__":
    main()
