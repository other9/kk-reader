# CLAUDE.md — kk-reader

Claude Code がこのリポジトリを開いたときに自動で読み込む設定ファイル。

最終更新: 2026-05-24

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
- [ ] pytest カバレッジ向上（現在 adapters/base.py のみ）
