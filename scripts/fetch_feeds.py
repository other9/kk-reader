#!/usr/bin/env python3
"""
全フィードを取得して articles.json を更新するスクリプト。
GitHub Actions から定期実行される。

更新履歴(merge ロジックに関係する分のみ):
- 2026-05-09 (update-013): 既存記事のメタデータ in-place 更新を追加。
  従来は ID(URL ハッシュ)で dedup して既存があれば新パース結果を捨てて
  いたため、adapter の改善が反映されないままだった。
"""
import json
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# scripts/ をパスに追加
sys.path.insert(0, str(Path(__file__).parent))

from adapters import ADAPTERS

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "docs" / "data"
FEEDS_PATH = DATA_DIR / "feeds.json"
ARTICLES_PATH = DATA_DIR / "articles.json"

# 設定値
RETENTION_DAYS = 30          # 何日分の記事を保持するか
MAX_WORKERS = 12             # 並列取得数
DISABLE_AFTER_FAILURES = 10  # 連続失敗回数で自動無効化


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_feeds() -> dict:
    if not FEEDS_PATH.exists():
        print(f"エラー: {FEEDS_PATH} がありません。先に opml_to_feeds.py を実行してください。")
        sys.exit(1)
    with open(FEEDS_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_existing_articles() -> dict:
    if ARTICLES_PATH.exists():
        with open(ARTICLES_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"articles": [], "last_updated": None}


def fetch_one(feed: dict) -> tuple[dict, list, dict]:
    """1フィードを取得。(feed, articles, meta_update) を返す"""
    if not feed.get("active", True):
        return feed, [], {}

    adapter = ADAPTERS.get(feed.get("source_type", "rss"))
    if adapter is None:
        return feed, [], {"last_error": f"アダプターなし: {feed.get('source_type')}"}

    try:
        articles, meta_update = adapter.fetch(feed)
        return feed, [a.to_dict() for a in articles], meta_update
    except Exception as e:
        return feed, [], {
            "last_fetch": now_iso(),
            "error_count": feed.get("error_count", 0) + 1,
            "last_error": f"未捕捉例外: {type(e).__name__}: {str(e)[:200]}",
        }


def main():
    print(f"=== フィード取得開始: {now_iso()} ===")
    feeds_data = load_feeds()
    feeds = feeds_data["feeds"]
    active_feeds = [f for f in feeds if f.get("active", True)]
    print(f"アクティブフィード: {len(active_feeds)}/{len(feeds)} 件")

    # 既存記事を読み込み
    existing = load_existing_articles()
    existing_articles = existing["articles"]
    # update-013: 既存記事を id でインデックス化することで、再フェッチ時に
    # title/published/summary/author を最新値で上書き可能にする。
    # 従来は existing_ids に入っているだけで「既存ならスキップ」だったため、
    # adapter 側のパース修正があっても古い broken レコードが残り続けていた。
    existing_by_id = {a["id"]: a for a in existing_articles}

    # 並列取得
    new_count = 0
    refreshed_count = 0
    success_count = 0
    fail_count = 0
    feed_id_to_meta: dict[str, dict] = {}
    new_articles_buffer: list[dict] = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(fetch_one, f): f for f in active_feeds}
        for fut in as_completed(futures):
            feed, articles, meta_update = fut.result()
            feed_id_to_meta[feed["id"]] = meta_update

            if meta_update.get("last_error"):
                fail_count += 1
                err = meta_update.get("last_error", "")
                print(f"  ✗ {feed['title']}: {err}")
            else:
                success_count += 1

            for art in articles:
                aid = art["id"]
                if aid not in existing_by_id:
                    # 新規記事
                    new_articles_buffer.append(art)
                    existing_by_id[aid] = art
                    new_count += 1
                else:
                    # update-013: 既存記事のメタデータを in-place 更新する。
                    # title / published / summary / author は source 側で
                    # 訂正・補完されたら反映したい。`fetched`(初出時刻)と
                    # `content_html`(別経路で fetch される / RSS は重複書込
                    # 回避のため)は触らない。空値での上書きはしない。
                    rec = existing_by_id[aid]
                    changed = False
                    for field in ("title", "published", "summary", "author"):
                        v = art.get(field)
                        if v is not None and v != "" and rec.get(field) != v:
                            rec[field] = v
                            changed = True
                    if changed:
                        refreshed_count += 1

    print(f"成功: {success_count}件 / 失敗: {fail_count}件 / 新規: {new_count}件 / 更新: {refreshed_count}件")

    # フィードメタデータを更新
    for feed in feeds:
        if feed["id"] in feed_id_to_meta:
            update = feed_id_to_meta[feed["id"]]
            for k, v in update.items():
                feed[k] = v
            # 連続失敗が閾値を超えたら自動無効化
            if feed.get("error_count", 0) >= DISABLE_AFTER_FAILURES:
                if feed.get("active", True):
                    feed["active"] = False
                    print(f"  自動無効化: {feed['title']} (連続失敗 {feed['error_count']}回)")

    # 記事をマージ
    all_articles = existing_articles + new_articles_buffer

    # 古い記事を削除
    cutoff = (datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)).isoformat()
    before_count = len(all_articles)
    all_articles = [
        a for a in all_articles
        if (a.get("published") or a.get("fetched", "")) >= cutoff
    ]
    pruned = before_count - len(all_articles)
    if pruned > 0:
        print(f"古い記事 {pruned}件を削除(保持期間: {RETENTION_DAYS}日)")

    # 公開日(なければ取得日)で降順ソート
    all_articles.sort(
        key=lambda a: a.get("published") or a.get("fetched", ""),
        reverse=True,
    )

    # 書き出し
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(ARTICLES_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "articles": all_articles,
            "last_updated": now_iso(),
            "stats": {
                "total": len(all_articles),
                "fetched_just_now": new_count,
                "feeds_success": success_count,
                "feeds_failed": fail_count,
            },
        }, f, ensure_ascii=False, indent=2)

    with open(FEEDS_PATH, "w", encoding="utf-8") as f:
        # categoriesも更新
        feeds_data["categories"] = sorted({fd["category"] for fd in feeds})
        json.dump(feeds_data, f, ensure_ascii=False, indent=2)

    print(f"記事総数: {len(all_articles)}件")
    print(f"=== 完了: {now_iso()} ===")


if __name__ == "__main__":
    main()
