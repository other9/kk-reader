# CLAUDE.md — kk-reader

Claude Code がこのリポジトリを開いたときに自動で読み込む設定ファイル。

最終更新: 2026-06-18（健美家の本文「取得失敗」を一覧スクレイプ時の本文取得で修正 update-020）

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

## 健美家(kenbiya.com)の本文取得（2026-06-18, update-020）

**現状: 一覧取得・本文取得とも稼働。本文は一覧スクレイプ時に同時取得して `content_html` に保存する。**

経緯:
- 健美家スクレイパー(`scrape_kenbiya`)は一覧から URL/タイトル/日付のみ取得し、本文(`content_html`)は None だった。本文はフロント(`app.js`)が記事を開いた時に kk-sync Worker `/article`（= Cloudflare IP）経由でオンデマンド取得していた。
- 2026-06 頃、健美家が CF Bot Management を強化し **Cloudflare IP を 403 ブロック**。Worker `/article` が 403 を返し、フロントが「本文の取得に失敗しました」を表示するようになった（joto 側で既知の同一根本原因）。**フィード削除はしていない（active=true）**。無効化したのは楽待。

対処（Option B = 一覧スクレイプ時に本文も取得）:
- `ScrapeAdapterBase` に本文取得機構を追加（`fetch_body` / `body_fetch_cap=20` / `body_fetch_delay=0.3` / `body_max_chars=50000`）。`fetch_body=True` のアダプターは一覧解析後に各記事ページを取得し `parse_article_body()` で本文を抽出 → `_sanitize_body_html()`（script/onイベント/inline style 除去・相対URL絶対化・長さ上限）→ `content_html` に格納。
- `KenbiyaColumnsAdapter`: `fetch_body=True` ＋ `parse_article_body()` を実装。コラム(/ar/cl/)・ニュース(/ar/ns/)共通の `div#box_entry`（共有ボタン・関連記事を含まないクリーンな本文）を採用。
- `fetch_feeds.py`: `known_body_ids`（content_html 取得済みの記事ID）を adapter に渡し再取得をスキップ。本文未取得の既存記事は毎ラン最大20件ずつバックフィル（in-place で `content_html` 補完）。
- 一覧取得は GitHub Actions(Azure IP)から通るため成立。フロントは `content_html` があれば Worker を呼ばず直接描画する。

⚠️ リスク: 健美家は Azure IP も**間欠的に 403** を返し始めた（楽待化の兆候）。完全403化すると本文取得も一覧取得も停止し、楽待同様 residential プロキシ経路が必要になる。本文取得は1ランあたり最大20リクエスト増えるため cap/delay は保守的に設定。

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
- [ ] 健美家のバックフィル完了確認（update-020。本文未取得の既存記事を 2h ごと最大20件ずつ補完。完全403化したら本文取得も停止し residential プロキシが必要）
- [ ] pytest カバレッジ向上（現在 adapters/base.py + 健美家本文抽出）
