# CLAUDE.md — kk-reader

Claude Code がこのリポジトリを開いたときに自動で読み込む設定ファイル。

最終更新: 2026-06-16（楽待をネイティブRSS化→ただし WAF で到達不可のため無効化保留）

---

## 楽待(rakumachi.jp)の取得状況（2026-06-16）

**現状: 2フィードとも `active=false`（無効化・保留）。kenbiya / cfajapan は正常。**

経緯:
- 楽待は元々スクレイピング（`scrape_rakumachi` + `via_worker`）で取得していたが、
  2026-06-11 頃に Cloudflare Bot Management が強化され、kk-sync Worker 経由
  （CF→CF）の `/fetch` が `upstream HTTP 403` で全滅 → error_count=10 で自動無効化。
- 楽待は現在ネイティブ RSS を提供しているため `scrape_rakumachi` → `rss` へ移行:
  - 楽待 実践大家コラム → `https://www.rakumachi.jp/news/practical/feed`
  - 楽待新聞 編集部記事 → `https://www.rakumachi.jp/news/column/feed`
  - 楽待新聞 連載コラム → 綺麗な RSS が無い（`/news/series/feed` は 404）ため**購読削除**
- しかし検証の結果、**楽待は UA ではなくデータセンターIPでブロック**していると判明:

  | 経路 × UA | 結果 |
  |---|---|
  | Actions直 × ブラウザ詐称UA | HTTP 403 |
  | Actions直 × Feedly UA | HTTP 403 |
  | Worker × ブラウザ詐称UA | upstream HTTP 403 |
  | 住宅IP（ローカル）× 任意 | 200 ✅ |

  Actions直 × Feedly UA でも 403 のため、正直な feed-reader UA でもデータセンターIPは
  弾かれる。楽待は Feedly 等の公開IPレンジを allowlist していると推定。無料基盤
  （Azure / Cloudflare）からは到達不可。

実装済み（基盤として維持、将来 residential プロキシ導入時に再開可能）:
- RSS アダプタの `via_worker` 対応（`fetch_bytes_via_worker`）
- RSS/Worker の feed-reader UA 上書き機構（`feed.user_agent` / Worker `/fetch?ua=`）

再開する場合: 住宅IP相当の residential プロキシ経由で取得する仕組みが別途必要。
feeds.json の楽待2フィードを `active=true` に戻し、プロキシ経路を実装する。

注: kk-sync Worker の更新版（`?ua=` 対応）は **CLOUDFLARE_API_TOKEN に KV write 権限が
無く `wrangler deploy` 不可**（code 10023）。デプロイには KV write 権限付与が必要。

---

## プロジェクト概要

Feedly の代替として作った個人用 RSS リーダー。サーバー不要・無料枠で完結。

- **更新**: GitHub Actions（2時間ごと、`:07` に実行）
- **配信**: GitHub Pages（`other9.github.io/kk-reader`）
- **同期**: Cloudflare Worker `kk-sync`（既読/お気に入り・記事取得・プロキシ）

---

## アーキテクチャ

```
GitHub Actions (2時間ごと cron: "7 */2 * * *")
  scripts/fetch_feeds.py
    ├── opml/subscriptions.opml → feeds.json
    └── 各フィード取得
        ├── 通常フィード: 直接HTTP
        └── via_worker: true のフィード: kk-sync /fetch 経由（WAF回避）
  → docs/data/feeds.json, articles.json をコミット
  → GitHub Pages が自動配信

ブラウザ (SPA)
  docs/index.html + app.js + style.css
  docs/sync.js → kk-sync Worker と通信
    - 既読/お気に入り: localStorage ↔ Worker /state/diff (LWW merge)
    - 記事本文: Worker /article（KVキャッシュ30日）
```

---

## ディレクトリ構成

```
docs/                    # GitHub Pages 公開ディレクトリ
  index.html
  app.js
  style.css
  sync.js                # SyncClient（Worker通信・マジックリンク認証）
  data/
    feeds.json           # フィード一覧（Actions自動更新）
    articles.json        # 記事キャッシュ（Actions自動更新）
scripts/
  fetch_feeds.py         # フィード取得メイン
  opml_to_feeds.py       # OPML → feeds.json 変換
  adapters/
    base.py              # SourceAdapter 基底クラス
    rss_adapter.py       # RSS取得
tests/
  test_adapters.py       # アダプター単体テスト（3件）
opml/
  subscriptions.opml     # 購読リスト（手動編集）
worker/
  worker.js              # kk-sync Cloudflare Worker
  wrangler.toml          # Worker設定（KV: STATE）
pyproject.toml           # Ruff + pytest 設定
```

---

## kk-sync Worker エンドポイント

ホスト: `https://kk-sync.other9.workers.dev`
認証: `Authorization: Bearer <SYNC_SECRET>`

| エンドポイント | メソッド | 用途 |
|---|---|---|
| `/ping` | GET | ヘルスチェック |
| `/state` | GET | 既読/お気に入り全取得 |
| `/state/diff` | POST | 差分を LWW マージ |
| `/article?url=X` | GET | 記事本文抽出+KVキャッシュ（30日） |
| `/fetch?url=X` | GET | 生HTMLプロキシ（WAF回避、5MBボディ上限） |

### CORS 許可オリジン
- `https://other9.github.io`
- `https://kk-reader.pages.dev`
- `https://*.kk-reader.pages.dev`（preview）
- `http://localhost:8765`

---

## 認証設計

**Worker認証**: Bearer トークン（SYNC_SECRET）のみ。個人用途として適切。

**フロントエンド認証**:
- localStorage に `kkreader.syncToken` として保存
- マジックリンク: `?token=xxx` → localStorage に保存 → URL から即削除（history.replaceState）
- トークン未設定時は同期機能が無効（読み取り専用で動作）

**GitHub Actions**: `WORKER_TOKEN`（SYNC_SECRET と同値）で `/fetch` を利用。

---

## GitHub Secrets（必須）

| Secret名 | 用途 |
|---|---|
| `WORKER_TOKEN` | kk-sync Worker 認証（SYNC_SECRETと同値） |

---

## fetch_feeds.py 設定値

```python
RETENTION_DAYS = 30      # 記事保持日数
MAX_WORKERS = 12         # 並列取得スレッド数
DISABLE_AFTER_FAILURES = 10  # 連続失敗で自動無効化
```

---

## Cloudflare KV

- Namespace: `STATE`（ID: `bcc0dd025aa34897b44a83f13ce88973`）
- 用途: 既読/お気に入り状態、記事本文キャッシュ
- キャッシュキー形式: `article:v3:<url_sha256_32char>`（v3: update-015でbump）

---

## GitHub Actions ワークフロー設計

### fetch-feeds.yml（メイン）
```yaml
cron: "7 */2 * * *"   # :00/:15/:30/:45 を避けてキュー遅延を緩和
concurrency:
  group: fetch-feeds
  cancel-in-progress: false  # 実行中のものは止めない
timeout-minutes: 15
```

push リトライ（update-018）: non-fast-forward reject 時、データを退避して reset --hard origin/main → 復元 → 再 commit。最大3回。

### ci.yml（品質チェック）
push のたびに自動実行（`docs/data/**` と `*.md` は除外）。

---

## 品質チェック（2026-05-24 追加）

| ツール | 設定 | 対象 |
|---|---|---|
| Ruff | select = ["F", "E9"]、ユーティリティスクリプト除外 | scripts/fetch_feeds.py, adapters/ 等 |
| pytest | testpaths = ["tests"]、pythonpath = ["scripts"] | tests/test_adapters.py（3件） |

テスト内容:
- `make_article_id()` の一貫性・GUID優先ロジック
- `Article.to_dict()` フィールド検証

```bash
pip install -r requirements.txt
ruff check .
pytest tests/ --tb=short
```

---

## やってはいけないこと

- worker.js の void elements（`img`, `br`, `input` 等）に `onEndTag()` を登録しない（Cloudflare Workers HTMLRewriter がエラーを投げる）
- キャッシュキーのバージョン（`article:v3:`）を理由なく変更しない（古いキャッシュが無効化される）
- CORS の `ALLOWED_ORIGINS` に `*` を追加しない
- `escapeText()` で既存のHTMLエンティティ（`&nbsp;` 等）を二重エンコードしない（update-015で修正済み）
- GitHub Actions の cron を `:00` や `:15` に設定しない（混雑帯）
- `pyproject.toml` の exclude リストを削除しない（ユーティリティスクリプトがlintエラーになる）

---

## よく使うコマンド

```bash
# フィード取得を手動トリガー
gh workflow run fetch-feeds.yml --repo other9/kk-reader

# 最新コミット確認
gh api repos/other9/kk-reader/commits?per_page=5 --jq '.[] | {sha: .sha[0:7], message: .commit.message, date: .commit.author.date}'

# Worker ローカル開発
cd worker && wrangler dev

# Worker デプロイ
cd worker && wrangler deploy

# KV 状態確認
wrangler kv key list --namespace-id bcc0dd025aa34897b44a83f13ce88973

# lint + テスト
ruff check . && pytest tests/ --tb=short
```

---

## joto-property-report との連携

`kk-sync` Worker の `/fetch` エンドポイントは kk-reader 専用ではなく、
`joto-property-report` の scraper.py も kenbiya スクレイピングに利用している。

`SYNC_SECRET` = kk-reader の `WORKER_TOKEN` = joto-property-report の `WORKER_TOKEN`（同値）

---

## 今後の改善候補

- [ ] articles.json 肥大化対策（ページネーション or 分割）
- [ ] HTMLRewriter チャンク分割問題の根本対処（update-016候補）
- [ ] 複数デバイス間同期の動作確認（SyncClient の pull/push フロー）
- [ ] 非RSSソース対応（メール、スクレイピング等のアダプター追加）
- [ ] 楽待の取得再開（residential プロキシ経路の実装。現状はデータセンターIPブロックで無効化保留）
- [ ] pytest カバレッジ向上（現在 adapters/base.py のみ）
