#!/usr/bin/env python3
"""
取得失敗フィードの診断ツール。

カテゴリ別にエラーを集計し、対応方針の判断材料を提示する。

update-009 で「サイレント失敗」(last_success は立つが articles.json に
0件しか入っていないフィード)の検出を追加。これは parser が破損して
items 抽出に失敗しているケースで、従来の error_count では発見できなかった。
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
        return ("403", "アクセス拒否 - Worker proxy(via_worker)で改善の可能性")
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
    if "via worker" in e:
        return ("Worker経由", "Worker /fetch 経由でも失敗 - origin が完全ブロック中")
    if "worker " in e:
        return ("Worker到達不能", "Worker 自体に届かない - 認証/設定確認")
    return ("その他", err[:80])


def find_silent_failures(feeds: list) -> list:
    """`last_items_count == 0` を検出(成功扱いだが items が抽出されていない状態)。

    scrape_base.py が成功時に必ず last_items_count をセットする(update-009 以降)。
    値が None の場合はまだ update-009 適用後のフェッチが走っていない、
    あるいは last_items_count を記録しないアダプタ(RSS 等)なので判定対象外。
    
    articles.json の件数を見る fallback は意図的に持たない:
      - retention window で古い記事が削られる
      - 新規記事が出ない RSS 等は false positive を量産する
    last_items_count が信頼できる単一情報源。
    """
    silent = []
    for fd in feeds:
        if not fd.get("active", True):
            continue
        if not fd.get("last_success"):
            continue
        if fd.get("last_items_count") == 0:
            silent.append(fd)
    return silent


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

    # =================================================================
    # サイレント失敗の検出
    # =================================================================
    silent = find_silent_failures(feeds)
    if silent:
        print(f"=== ⚠️  サイレント失敗(last_success だが items 0件) — {len(silent)}件 ===")
        print("→ parser が壊れている可能性。adapter のセレクタを確認してください。\n")
        for fd in silent:
            via = " [via_worker]" if fd.get("via_worker") else ""
            print(f"  • [{fd.get('category', '?')}] {fd['title']}{via}")
            print(f"    URL: {fd['url']}")
            print(f"    last_success: {fd.get('last_success')}")
            if fd.get("last_items_count") is not None:
                print(f"    last_items_count: {fd['last_items_count']}")
        print()

    # =================================================================
    # 通常の失敗(error_count > 0)
    # =================================================================
    if not failed:
        if not silent:
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
            via = " [via_worker]" if fd.get("via_worker") else ""
            print(f"  • [{fd['category']}] {fd['title']}{marker}{via}")
            print(f"    URL: {fd['url']}")
            print(f"    エラー: {fd['last_error']}")
            print(f"    連続失敗: {err_count}回")
            if fd.get("html_url"):
                print(f"    サイト: {fd['html_url']}")

    print(f"\n=== 推奨アクション ===")
    print(f"無効化候補(連続10回以上失敗): {sum(1 for fd in failed if fd.get('error_count', 0) >= 10)}件")
    if any(c == "403" for (c, _) in groups.keys()):
        print(f"403系: feeds.json で `via_worker: true` を設定すると Cloudflare Worker 経由で取得できます。")
    print(f"\nfeeds.json を編集して `\"active\": false` にすることで明示的に無効化できます。")
    print(f"または、opml/subscriptions.opml から該当エントリを削除してください。")


if __name__ == "__main__":
    main()
