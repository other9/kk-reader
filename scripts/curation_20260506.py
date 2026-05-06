#!/usr/bin/env python3
"""
2026-05-06 のフィード整理を適用する一回限りのスクリプト。

実施内容:
1. 確実に死んでいるフィードを active: false に設定
   - 廃止サービス (Yahoo Blog, goo blog, so-net blog 等)
   - 長期 404 (URLパス消滅)
   - DNS解決不能 (ドメイン失効)
2. SSL証明書問題のあるフィードに verify_ssl: false を設定

冪等(べきとう): 何度実行しても結果は同じ。
"""
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
FEEDS_PATH = PROJECT_ROOT / "docs" / "data" / "feeds.json"


# 確実に死亡しているフィード(復活見込みなし)
DEAD_FEED_URLS = {
    # 404 (URLパス消滅、長期化)
    "http://markethack.net/index.rdf",
    "http://giraffyk1.hatenablog.com/feed",
    "http://urbansprawl.net/atom.xml",
    "http://blog.livedoor.jp/yuwave2009/index.rdf",
    "http://streetlightblog.blogspot.com/feeds/posts/default",
    "http://rss.exblog.jp/rss/exblog/manshukits/atom.xml",
    "http://blog.livedoor.jp/tateit/index.rdf",
    "http://nuemura.com/xml-rss2.php",
    "http://ohtake.cocolog-nifty.com/ohtake/rss.xml",
    "http://rss.exblog.jp/rss/exblog/linate/atom.xml",
    "http://feedblog.ameba.jp/rss/ameblo/laborintus2/rss20.xml",
    "http://401k.sblo.jp/index.rdf",
    "http://takahato.blog112.fc2.com/?xml",
    "http://rss.exblog.jp/rss/exblog/hongokucho/index.xml",  # 本石町日記(exblogで消滅、新URLなら復活可能)
    # DNS解決不能(ドメイン失効・廃止サービス)
    "https://aripy.net/feed/",
    "http://blogs.yahoo.co.jp/sfscottiedog/rss.xml",  # Yahoo Blog 2019終了
    "http://mituikenta.blog.so-net.ne.jp/index.rdf",  # so-net blog 終了
    "http://www.mh3.co.jp/?feed=rss2",
    "http://blog.goo.ne.jp/mit_sloan/rss2.xml",  # goo blog 2025終了
    "http://blog.goo.ne.jp/dongyingwenren/rss2.xml",  # goo blog 2025終了
    "http://takahato.net/?feed=atom",
    "http://alphalifehacker.jp/?xml",
    "https://tanoshimulife.com/feed",
}

# SSL証明書検証を無効化するフィード
# 自己署名証明書や期限切れ等で接続できないが、コンテンツ自体は信頼できる場合のみ
SSL_SKIP_URLS = {
    "https://diary.urbansprawl.net/index.rdf",
}


def main():
    if not FEEDS_PATH.exists():
        print(f"エラー: {FEEDS_PATH} が見つかりません")
        sys.exit(1)

    with open(FEEDS_PATH, encoding="utf-8") as f:
        data = json.load(f)

    disabled = []
    ssl_skipped = []
    already_disabled = 0
    already_ssl_skipped = 0
    not_found = []

    feeds_by_url = {fd["url"]: fd for fd in data["feeds"]}

    for url in DEAD_FEED_URLS:
        if url not in feeds_by_url:
            not_found.append(url)
            continue
        fd = feeds_by_url[url]
        if not fd.get("active", True):
            already_disabled += 1
        else:
            fd["active"] = False
            disabled.append(fd)

    for url in SSL_SKIP_URLS:
        if url not in feeds_by_url:
            not_found.append(url)
            continue
        fd = feeds_by_url[url]
        if not fd.get("verify_ssl", True):
            already_ssl_skipped += 1
        else:
            fd["verify_ssl"] = False
            ssl_skipped.append(fd)

    with open(FEEDS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # 結果表示
    print(f"=== 2026-05-06 フィード整理 適用結果 ===\n")

    print(f"無効化したフィード: {len(disabled)} 件")
    if already_disabled:
        print(f"  (既に無効化済み: {already_disabled} 件)")
    for fd in disabled:
        print(f"  ✗ [{fd['category']}] {fd['title']}")

    print(f"\nSSL検証スキップに設定: {len(ssl_skipped)} 件")
    if already_ssl_skipped:
        print(f"  (既に設定済み: {already_ssl_skipped} 件)")
    for fd in ssl_skipped:
        print(f"  ⚠ [{fd['category']}] {fd['title']}")

    if not_found:
        print(f"\n警告: feeds.json に見つからないURL: {len(not_found)} 件")
        for url in not_found:
            print(f"  ? {url}")

    active_count = sum(1 for fd in data["feeds"] if fd.get("active", True))
    inactive_count = sum(1 for fd in data["feeds"] if not fd.get("active", True))
    print(f"\n=== フィード状態 ===")
    print(f"アクティブ: {active_count} / 無効: {inactive_count} / 合計: {len(data['feeds'])}")
    print(f"\n次回 GitHub Actions 実行時から、無効化したフィードは取得対象外になります。")


if __name__ == "__main__":
    main()
