#!/usr/bin/env python3
"""
プロジェクト現状スナップショットを生成し、Claudeに提供するためのZIPを作る。

生成物の中身:
  - STATE.json : 全体の状態サマリ(git, フィード, 記事の集計)
  - source/    : 現在のソースコード一式(記事データは除く)

記事本文(content_html)は意図的に含めない:
  - プライバシー保護
  - サイズ抑制
  - 開発判断には集計とサンプルで十分

使い方:
  python3 scripts/snapshot.py
"""
import json
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter, defaultdict

PROJECT_ROOT = Path(__file__).parent.parent
TIMESTAMP = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
OUTPUT_NAME = f"kk-reader-snapshot-{TIMESTAMP}.zip"
OUTPUT_PATH = PROJECT_ROOT / OUTPUT_NAME

# スナップショットに含めるソースのパターン(プロジェクトルート相対)
INCLUDE_PATHS = [
    ".github/workflows/fetch-feeds.yml",
    "docs/index.html",
    "docs/app.js",
    "docs/style.css",
    "docs/sync.js",
    "worker",
    "docs/data/feeds.json",
    "opml/subscriptions.opml",
    "scripts",
    "README.md",
    "SETUP.md",
    "requirements.txt",
    ".gitignore",
]

# パスに含まれていたら除外するパターン
EXCLUDE_TOKENS = ["__pycache__", ".pyc", ".DS_Store", ".pytest_cache"]


def run_git(args: list[str]) -> str:
    """git コマンドを実行して出力を返す。失敗時は空文字。"""
    try:
        return subprocess.check_output(
            ["git"] + args,
            cwd=PROJECT_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""


def get_git_info() -> dict:
    info = {
        "branch": run_git(["rev-parse", "--abbrev-ref", "HEAD"]),
        "commit": run_git(["log", "-1", "--format=%H"]),
        "commit_short": run_git(["log", "-1", "--format=%h"]),
        "commit_message": run_git(["log", "-1", "--format=%s"]),
        "commit_date": run_git(["log", "-1", "--format=%aI"]),
        "author": run_git(["log", "-1", "--format=%an"]),
    }
    log = run_git(["log", "-15", "--format=%h|%aI|%an|%s"])
    info["recent_commits"] = [
        dict(zip(["hash", "date", "author", "subject"], line.split("|", 3)))
        for line in log.split("\n") if line
    ]
    status = run_git(["status", "--short"])
    info["uncommitted_changes"] = status.split("\n") if status else []
    return info


def summarize_feeds() -> dict:
    feeds_path = PROJECT_ROOT / "docs" / "data" / "feeds.json"
    if not feeds_path.exists():
        return {"error": "feeds.json not found"}

    with open(feeds_path, encoding="utf-8") as f:
        data = json.load(f)
    feeds = data.get("feeds", [])

    active = [f for f in feeds if f.get("active", True)]
    inactive = [f for f in feeds if not f.get("active", True)]
    failed = [f for f in feeds if f.get("last_error")]
    succeeded = [f for f in feeds if not f.get("last_error") and f.get("last_success")]
    never = [f for f in feeds if not f.get("last_fetch")]

    # エラー分類
    err_buckets = defaultdict(int)
    for f in failed:
        err = (f.get("last_error") or "").lower()
        if "http 404" in err: err_buckets["404"] += 1
        elif "http 403" in err: err_buckets["403"] += 1
        elif "http 410" in err: err_buckets["410"] += 1
        elif "http 401" in err: err_buckets["401"] += 1
        elif "http 5" in err: err_buckets["5xx"] += 1
        elif "ssl" in err or "cert" in err: err_buckets["SSL"] += 1
        elif any(s in err for s in ["connection", "name or service", "nodename"]): err_buckets["connection"] += 1
        elif "timeout" in err: err_buckets["timeout"] += 1
        elif "parse" in err or "bozo" in err: err_buckets["parse"] += 1
        else: err_buckets["other"] += 1

    # カテゴリ別の集計
    by_category = Counter(f.get("category", "未分類") for f in feeds)

    # 失敗フィードの全リスト(URL等を含む)を提供
    failed_detail = [
        {
            "title": f["title"],
            "url": f["url"],
            "category": f.get("category"),
            "last_error": f.get("last_error"),
            "error_count": f.get("error_count", 0),
            "last_fetch": f.get("last_fetch"),
        }
        for f in failed
    ]

    return {
        "total": len(feeds),
        "active": len(active),
        "inactive": len(inactive),
        "succeeded": len(succeeded),
        "failed": len(failed),
        "never_fetched": len(never),
        "categories": dict(by_category),
        "error_breakdown": dict(err_buckets),
        "failed_feeds": failed_detail,
    }


def summarize_articles() -> dict:
    """articles.json から本文を除いた集計情報を作る"""
    articles_path = PROJECT_ROOT / "docs" / "data" / "articles.json"
    if not articles_path.exists():
        return {"error": "articles.json not found"}

    with open(articles_path, encoding="utf-8") as f:
        data = json.load(f)
    articles = data.get("articles", [])

    by_category = Counter()
    by_feed = Counter()
    for a in articles:
        by_category[a.get("category", "未分類")] += 1
        by_feed[a.get("feed_title", "?")] += 1

    # 経過時間別の集計
    now = datetime.now(timezone.utc)
    age_buckets = {"24h以内": 0, "1週間以内": 0, "1ヶ月以内": 0, "それ以前": 0}
    for a in articles:
        ts = a.get("published") or a.get("fetched")
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            hours = (now - dt).total_seconds() / 3600
            if hours < 24: age_buckets["24h以内"] += 1
            elif hours < 24 * 7: age_buckets["1週間以内"] += 1
            elif hours < 24 * 30: age_buckets["1ヶ月以内"] += 1
            else: age_buckets["それ以前"] += 1
        except Exception:
            pass

    # 直近20件のメタデータのみ(本文は含めない)
    sorted_articles = sorted(
        articles,
        key=lambda a: a.get("published") or a.get("fetched") or "",
        reverse=True,
    )
    recent_sample = [
        {
            "title": a.get("title"),
            "feed_title": a.get("feed_title"),
            "category": a.get("category"),
            "published": a.get("published"),
            "summary": (a.get("summary") or "")[:120],
        }
        for a in sorted_articles[:20]
    ]

    return {
        "total": len(articles),
        "last_updated": data.get("last_updated"),
        "fetch_stats": data.get("stats", {}),
        "by_category": dict(by_category),
        "top_feeds": dict(by_feed.most_common(15)),
        "age_distribution": age_buckets,
        "recent_sample": recent_sample,
    }


def detect_modifications() -> dict:
    """Claude が最後に提供したコードからの変更があるかを git ベースで検出"""
    return {
        "uncommitted": run_git(["status", "--short"]).split("\n") if run_git(["status", "--short"]) else [],
        "note": "ローカルでファイルを直接編集した場合、ここに表示されます",
    }


def collect_source_files() -> list[Path]:
    """ZIPに含めるソースファイルのリストを集める"""
    files = []
    for include in INCLUDE_PATHS:
        path = PROJECT_ROOT / include
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            for sub in path.rglob("*"):
                if sub.is_file() and not any(tok in str(sub) for tok in EXCLUDE_TOKENS):
                    files.append(sub)
    return files


def main():
    print(f"=== スナップショット生成開始 ===")

    state = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git": get_git_info(),
        "feeds": summarize_feeds(),
        "articles": summarize_articles(),
        "local_modifications": detect_modifications(),
    }

    # STATE.json を一時的に作成
    state_path = PROJECT_ROOT / "STATE.json"
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

    # ソースファイルを集める
    source_files = collect_source_files()
    print(f"ソースファイル: {len(source_files)} 件")

    # ZIP作成
    with zipfile.ZipFile(OUTPUT_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
        # STATE.json はZIPルートに置く
        zf.write(state_path, "STATE.json")

        # ソースは source/ 配下に配置
        for path in source_files:
            rel = path.relative_to(PROJECT_ROOT)
            zf.write(path, f"source/{rel}")

        # 簡易説明書を入れる
        readme_text = f"""# kk-reader Snapshot

Generated: {state['generated_at']}
Git commit: {state['git'].get('commit_short')} ({state['git'].get('commit_message')})

## 構造

- STATE.json : 全体の状態サマリ(まずこれを読む)
- source/    : 現在のソースコード一式

## 含まれないもの(意図的)

- 記事本文(docs/data/articles.json の content_html)
- 既読/お気に入り情報(localStorage に格納されており、サーバー側に存在しない)
- 認証情報(そもそも保存していない)

## 統計サマリ

- フィード総数: {state['feeds'].get('total')}
- 取得成功: {state['feeds'].get('succeeded')}
- 取得失敗: {state['feeds'].get('failed')}
- 記事総数: {state['articles'].get('total')}
"""
        zf.writestr("README.txt", readme_text)

    # STATE.json は一時ファイルなので削除
    state_path.unlink()

    size_kb = OUTPUT_PATH.stat().st_size / 1024
    print(f"\n生成完了: {OUTPUT_NAME}")
    print(f"サイズ:   {size_kb:.1f} KB")
    print(f"パス:     {OUTPUT_PATH}")
    print(f"\n統計:")
    print(f"  フィード: {state['feeds'].get('total')} 件 (成功 {state['feeds'].get('succeeded')} / 失敗 {state['feeds'].get('failed')})")
    print(f"  記事:     {state['articles'].get('total')} 件")
    if state["git"].get("uncommitted_changes"):
        print(f"  未コミット変更: {len(state['git']['uncommitted_changes'])} 件 ※注意")
    print(f"\n=> このZIPをClaudeにアップロードしてください")


if __name__ == "__main__":
    main()
