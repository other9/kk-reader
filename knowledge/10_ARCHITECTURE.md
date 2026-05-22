# kk-reader アーキテクチャ

## 4 層構成(移行後、Phase 0〜4 完了状態)

```
┌──────────────────────────────────────────────────────────────────┐
│  Layer 1: クライアント (ブラウザ)                                  │
│  HTML/CSS/JS、状態 localStorage                                   │
│  localStorage keys: kkreader.read, kkreader.favs,                 │
│                     kkreader.syncToken, kkreader.lastSync,        │
│                     kkreader.pendingDiff, kkreader.settings,      │
│                     kkreader.expandedCategories                   │
└──────────────┬─────────────────┬──────────────────────────────────┘
               │ articles.json   │ /state, /article
               │ (静的)          │ (認証 API)
               ▼                 ▼
┌──────────────────────────┐  ┌──────────────────────────────────┐
│  Layer 2a: Cloudflare    │  │  Layer 2b: Cloudflare Worker     │
│  Pages + Access          │  │  kk-sync.other9.workers.dev      │
│  kk-reader.pages.dev     │  │  worker/worker.js                │
│                          │  │  認証: Bearer SYNC_SECRET         │
│  - 認証: メール OTP       │  │  CORS allowlist:                 │
│  - Session: 1 month      │  │   - kk-reader.pages.dev          │
│  - 2 Applications:       │  │   - other9.github.io             │
│    • production          │  │   - localhost:8765               │
│    • preview (wildcard)  │  │   - *.kk-reader.pages.dev (re)   │
│                          │  │                                  │
│  ※ 旧 GitHub Pages も     │  │  - GET  /state                   │
│    並行稼働中(Phase 6    │  │  - POST /state/diff              │
│    で撤去予定)            │  │  - GET  /article?url=...         │
│                          │  │  - GET  /fetch?url=...           │
│  build src: docs/        │  │  - GET  /ping                    │
└──────────────┬───────────┘  └──────────────┬───────────────────┘
               │ git push                    │ KV
               │                             ▼
               │                ┌─────────────────────────────────┐
               │                │  Layer 3: Cloudflare KV          │
               │                │  namespace STATE                 │
               │                │  ID: bcc0dd025aa34897b44a83f...  │
               │                │                                  │
               │                │  - state:default                 │
               │                │    {read:{...}, fav:{...}}       │
               │                │  - article:v3:<sha256(url)>      │
               │                │    {url, content_html, ...}      │
               │                │    TTL 30 日                      │
               │                │  - article:v2:* (stale, 111件)    │
               │                │  - article:<hash> (no version,    │
               │                │    pre-update-011, 13件)          │
               │                └─────────────────────────────────┘
               ▼
┌──────────────────────────────────────────────────────────────────┐
│  Layer 4: GitHub Actions (cron 2 時間ごと、HH:07 起動)            │
│  .github/workflows/fetch-feeds.yml                               │
│  env: WORKER_BASE_URL, WORKER_TOKEN                              │
│                                                                   │
│  scripts/fetch_feeds.py (RETENTION_DAYS=60、update-017)           │
│   ├─ scripts/adapters/rss_adapter.py        (RSS)                │
│   ├─ scripts/adapters/kenbiya_scraper.py    (健美家)              │
│   ├─ scripts/adapters/rakumachi_scraper.py  (楽待 - via_worker)   │
│   └─ scripts/adapters/cfajapan_scraper.py   (CFA - via_worker、   │
│                                              update-016)         │
│                                                                   │
│  → docs/data/articles.json と feeds.json を更新 → bot commit     │
│  → push reject 時は最大 3 回 rebase-retry (update-018)            │
│  → commit message: "chore: update feeds" (skip ci 無し、          │
│                                            update-019 以降)      │
└──────────────────────────────────────────────────────────────────┘
```

cron は `0 */2 * * *` から `7 */2 * * *` に変更済み(update-012)で混雑帯回避。
push reject 時の rebase-retry は update-018 で workflow に組み込み済み。
Phase 4(update-019 セッション)で `[skip ci]` を除去、Cloudflare Pages が
bot commit を build トリガするようになった。

KV cache key prefix は v3。v1 は update-011 で v2 に bump(相対 URL 修正)、v2 は
update-015 で v3 に bump(エンティティ二重エンコード修正)。

## Worker `/state`、CORS allowlist(update-019)

`worker/worker.js` 先頭部分:

```javascript
const ALLOWED_ORIGINS = [
  "https://other9.github.io",
  "https://kk-reader.pages.dev",
  "http://localhost:8765",
];
const ALLOWED_ORIGIN_PATTERNS = [
  // Cloudflare Pages preview deployments (e.g. abc1234.kk-reader.pages.dev)
  /^https:\/\/[a-z0-9-]+\.kk-reader\.pages\.dev$/,
];
function isAllowedOrigin(origin) {
  if (!origin) return false;
  if (ALLOWED_ORIGINS.includes(origin)) return true;
  return ALLOWED_ORIGIN_PATTERNS.some((re) => re.test(origin));
}
```

`isAllowedOrigin` は exact match + regex match を統合。preview deployments
(`<hash>.kk-reader.pages.dev`)もここで吸収。

## Cloudflare Pages 設定(Phase 1 で確定)

```
Project name:       kk-reader
Production branch:  main
Build command:      (空)
Build output dir:   docs
Root directory:     (空、リポジトリ root)
Framework:          None
Source:             GitHub other9/kk-reader (linked)
```

push のたびに自動 build。Phase 4 以降は cron commit にも反応する。

build 数の想定: 12 runs/日 × 30 日 = 360 builds/月 + 手動 push = ~370 builds/月。
Free 枠 500 builds/月の 74%。

## Cloudflare Access 設定(Phase 3 で確定)

2 つの Application で `kk-reader.pages.dev` 配下を保護:

| Application | Subdomain | Domain | Session |
|---|---|---|---|
| production | (空) | `kk-reader.pages.dev` | 730h (≈1ヶ月) |
| preview | `*` | `kk-reader.pages.dev` | 730h |

policy: いずれも Action=Allow / Include / Emails / 自分のメアド 1 件のみ。

Identity provider: One-time PIN(メール OTP)、追加 IdP なし。Team domain は
Zero Trust 初期化時に固定。

## Worker エンドポイント

### `/state` / `/state/diff`(同期)

既読・お気に入り情報のクライアント間同期。LWW マージ。詳細は後述「同期」参照。

### `/article?url=X`(本文 on-demand 取得)

スクレイピング系フィード(健美家・楽待・CFA Society Japan)の記事本文を取得
して返す。

- **キャッシュ**: KV `article:v3:<sha256(url)>` (TTL 30 日)
- **本文抽出**: HTMLRewriter で `extractorFor(url)` のサイト別 selector に従う
- **URL 解決**: 抽出時点で `<img src>` `<a href>` を絶対 URL に解決(原ページ
  URL を base に)
- **lazy-load fallback**: `data-src` / `data-original` / `data-lazy-src` を
  `src` の代替として読む
- **void element**: `<br>` `<hr>` `<img>` 等 14 要素は閉じタグを emit しない
  (HTMLRewriter の onEndTag 制約対応、update-010)
- **エンティティ保持**: HTMLRewriter の text chunk が渡してくる HTML entity
  reference(`&nbsp;` `&gt;` 等)を、bare な `&` だけ escape する正規表現で
  処理して二重エンコードを回避(update-015)

cache key の v3 prefix は update-015 で導入。update-014 以前にキャッシュされた
二重エンコード入りのレコードを実質無効化するため。

### `/article` の対応サイト(`extractorFor`)

- `kenbiya.com` (健美家): `div#contents`, `div.article-body`, `article`, …
- `rakumachi.jp` (楽待): `article.news-detail`, `div.article-body`, …
- `cfasociety.org` (CFA Society Japan、Higher Logic 構成): `div#MPContentArea`,
  `div.MainPaneContent`, `main`, `article`
- それ以外: 汎用 fallback (`article`, `main`, `div[role='main']`,
  `div.entry-content`, `div.post`)

### `/fetch?url=X`(任意 URL の HTML プロキシ取得)

GitHub Actions の outbound IP が WAF で弾かれるサイト(楽待 rakumachi.jp、
CFA Society Japan の Higher Logic + Cloudflare CDN 等)対策。生 HTML をそのまま
JSON で包んで返すシンプルなプロキシ。

- **認証**: `/article` と同じ SYNC_SECRET Bearer
- **キャッシュ**: なし
- **ヘッダ**: ブラウザ完全偽装(Sec-Fetch-* 等を含む)で送信

スクレイピング系 adapter の修正時には、`/fetch` で実 HTML を取り寄せて
DOM 構造を確認する運用が推奨される。

### `/ping`

ヘルスチェック。`{ok: true, ts: ...}` を返す(認証必須)。

## クライアント側 token 投入(update-022 以降)

新端末を kk-reader.pages.dev に追加する経路は 3 つ:

1. **URL fragment 経由**(推奨):
   ```
   https://kk-reader.pages.dev/#token=<TOKEN>
   ```
   `docs/index.html` の `<head>` 直下にある bootstrap script が fragment を
   読み取り、`localStorage.setItem("kkreader.syncToken", token)` した上で
   `history.replaceState` で URL から fragment を消す。fragment はサーバに
   送信されないため、server log や Referer に token は残らない。
2. **`/debug.html` のフォームから貼り付け**: アプリ内の診断ページから直接
   localStorage に書き込み。`javascript:` URL や bookmarklet が動かない端末
   (Android Chrome の最近の版等)で有用。
3. **DevTools 直接書き込み**: `localStorage.setItem("kkreader.syncToken", "...")`

bootstrap script は legacy key `kk-sync-token` の自動 migration も行う
(過去誤って書かれた値が残っていれば `kkreader.syncToken` に移し、legacy 側を
削除)。

## docs/debug.html(update-021/022 で追加)

端末追加 + 同期障害切り分け用の独立ページ。`https://kk-reader.pages.dev/debug.html`
からアクセス可能(Cloudflare Access ゲートの内側)。3 セクション構成:

1. **Token**: `kkreader.syncToken` の長さ、ASCII か、先頭末尾を表示。
   フォームから直接書き込み / クリアが可能
2. **Worker connectivity**: `/ping` / `/state` を叩いてレスポンスを表示
3. **Environment**: location.origin、userAgent、cookie 有効性

依存ゼロ、~10KB。`<meta name="robots" content="noindex,nofollow">` 付き。

## データフロー(購読 〜 表示)

### RSS フィードの場合

```
RSS feed → fetch_feeds.py → articles.json に full content_html 格納
  → Cloudflare Pages 配信 → ブラウザが articles.json ロード
  → 詳細表示で content_html 直接 render
```

### スクレイピング系(健美家・楽待・CFA Society Japan)の場合 — Path 2 アーキテクチャ

```
1. fetch_feeds.py が一覧ページをスクレイプ → メタ情報のみ articles.json に格納
   (URL, title, author, published — content_html は null)
   - 健美家は直 fetch
   - 楽待 / CFA は via_worker: true により Worker /fetch 経由で取得

2. ブラウザがリストを表示

3. 記事クリック時 → app.js の renderArticleBodyLazy() が発火
   → sync.js の fetchArticle() → Worker /article?url=X

4. Worker /article:
   a. KV `article:v3:<sha256(url)>` をチェック → ヒットすれば即返却
   b. ミス時 → origin server から HTML 取得(UA 偽装)
   c. HTMLRewriter で extractorFor(url) のセレクタに従って本文抽出
   d. 抽出時に img src / a href を絶対 URL に resolve
   e. text chunk の HTML entity は二重エンコードを避けて保持
   f. KV に保存(TTL 30 日)
   g. ブラウザに返却

5. ブラウザが詳細ビューに content_html を render
```

## 同期(マルチデバイス間)

`/state/diff` は LWW (Last-Writer-Wins) マージ。

```
クライアント A:                 Worker (KV)               クライアント B:
  read[id-x] = 1, ts=100   →   merge: id-x state=1
                                 ts=100 ← 採用
                                                       ←  read[id-x] = 0, ts=50
                              merge: ts=100 > 50
                                 → ts=100 のまま 維持
                                                          (B には伝播せず)
```

各レコード: `{state: 0|1, ts: epoch_ms}`. クライアントは前回 sync 時の state
を保持し、ローカル変更時に新しい ts で diff を送信。

### app.js 側の sync 呼び出し(performSync)

`docs/app.js` の `init()` は以下の順で実行:

1. `loadFromStorage()` — localStorage から read/favs を読む
2. `window.kkSync.init()` — `SyncClient` を生成
3. UI イベントリスナー登録
4. `visibilitychange` ハンドラ登録(タブが可視に戻ったら `performSync(false)`)
5. `loadData()` — articles.json をロード
6. 初期 render
7. **末尾で `performSync(true)` を呼ぶ**(初回 pull)

`performSync` の動作:
- pending diff があれば flush
- `sc.pull()` で /state を取得
- server vs local を LWW でマージ
- 変更があれば `saveRead()` / `saveFavs()` + `renderArticleList()` で再描画

Android では稀に初回 `performSync(true)` の結果が UI に反映されず、visibility
change を待つ必要がある場面が観測された。原因は完全には未解明、実用上は
タブ切替で回復するので Phase 5 期間中は様子見。詳細は `40_KNOWN_ISSUES.md` 参照。

## 主要 URL とリソース

| 項目 | 値 |
|---|---|
| ライブサイト | https://kk-reader.pages.dev/(Cloudflare Access 必須) |
| 旧ライブサイト | https://other9.github.io/kk-reader/(Phase 6 撤去予定) |
| リポジトリ | https://github.com/other9/kk-reader |
| Worker | https://kk-sync.other9.workers.dev |
| Worker compatibility_date | `2026-05-06` |
| KV namespace ID | `bcc0dd025aa34897b44a83f13ce88973` |
| Cloudflare account ID | `3fbbef709acd9608e64302bc0dec48a7` |
| GitHub アカウント | `other9` |

## 機密情報の管理

| 機密値 | 保存場所 | 用途 |
|---|---|---|
| `SYNC_SECRET` | `wrangler secret put` 経由(Cloudflare 側) | Worker 側 Bearer 認証 |
| `WORKER_TOKEN` | GitHub Actions Repository Secrets | Actions runner が Worker `/fetch` を叩く際の Bearer。**SYNC_SECRET と同値**で運用 |
| `CLOUDFLARE_API_TOKEN` | GitHub Codespaces Secrets | Codespaces 内で `wrangler deploy` する際の認証 |

ソースコードや Knowledge ドキュメントには記載しない。

`WORKER_TOKEN` と `CLOUDFLARE_API_TOKEN` は GitHub の異なる secret store
(Actions vs Codespaces)に保存される。Codespaces secret は Actions runner からは
見えない、逆も同様。Phase 3 で `WORKER_TOKEN` の multi-token 化を計画。

ローカル smoke test で curl を叩く時の TOKEN は browser localStorage の
**`kkreader.syncToken`** から取得できる:

```javascript
// PC ブラウザの Console で
copy(localStorage.getItem("kkreader.syncToken"))
```

過去の Knowledge には誤って `kk-sync-token` というキー名が記載されていたが、
実装と一致しない誤記。正しいキー名は `kkreader.syncToken`(`docs/sync.js` の
`SYNC_STORAGE.token` 定数の値)。

## CLOUDFLARE_API_TOKEN に必要な scope

`scripts/cf_snapshot.py`(update-024)で CF 側状態を取得するために必要な scope:

| Permission | 用途 |
|---|---|
| Account: Workers Scripts: Edit(または Read) | Worker deployments, settings, secrets |
| Account: Workers KV Storage: Edit(または Read) | KV namespaces, keys |
| Account: Cloudflare Pages: Edit(または Read) | Pages project, deployments |
| Account: Access: Apps and Policies: Read | Access apps, policies |

既存の `wrangler deploy` 用 token に上 3 つはあるはず。Access 用 scope は手動
追加が必要だった。

## feeds.json 内の主な field

```json
{
  "id": "0604078e48ca",
  "title": "楽待 実践大家コラム",
  "url": "https://www.rakumachi.jp/news/practical",
  "html_url": "https://www.rakumachi.jp/news/practical",
  "category": "不動産",
  "source_type": "scrape_rakumachi",
  "active": true,
  "verify_ssl": true,
  "via_worker": true,
  "etag": null,
  "last_modified": null,
  "last_fetch": "2026-05-18T...",
  "last_success": "2026-05-18T...",
  "last_items_count": 41,
  "error_count": 0,
  "last_error": null
}
```

feeds.json の top-level は **`{"feeds": [...]}` の dict 構造**。直接 list では
ない。migration script を書く時は `data = json.load(f); feeds = data["feeds"]`
の二段取り出しが必要。

## 技術スタック

| Layer | 技術 |
|---|---|
| Layer 1 (Frontend) | Vanilla JS、CSS Variables、localStorage、no framework |
| Layer 2a (Pages、現) | Cloudflare Pages + Access、`docs/` をビルド配信 |
| Layer 2a (Pages、旧) | GitHub Pages、`docs/` ディレクトリ自動配信(Phase 6 撤去予定) |
| Layer 2b (Worker) | Cloudflare Worker、HTMLRewriter、Web Crypto |
| Layer 3 (KV) | Cloudflare KV |
| Layer 4 (Fetch) | Python 3.11、feedparser、BeautifulSoup4、requests、lxml |
| 配信トリガー | GitHub Actions、cron 2h(HH:07)、push retry-with-rebase、Pages auto-build |

すべて無料枠内で運用:
- Cloudflare Worker: 100k req/day 無料
- KV: 1k write/day 無料
- Cloudflare Pages: 500 builds/月、bandwidth 無制限
- Cloudflare Access: 50 user まで無料、user 1 で永久範囲内
- GitHub Actions: public リポジトリ間は無制限、Phase 6 で private 化後は
  2000 min/月 Free 枠(実測 ~1100 min/月で枠内)

## ファイル構造

```
kk-reader/
├── docs/                       # Cloudflare Pages / GitHub Pages 配信先
│   ├── index.html              # update-022 で <head> に token bootstrap 追加
│   ├── debug.html              # update-021/022、診断・端末追加用
│   ├── app.js                  # メインロジック
│   ├── sync.js                 # SyncClient: /state, /article 呼び出し
│   ├── style.css
│   └── data/
│       ├── articles.json       # 全記事(メタ + RSS の content_html)
│       └── feeds.json          # フィード一覧 + 取得状態({"feeds": [...]})
├── worker/
│   ├── worker.js               # CORS allowlist + /state /article /fetch /ping
│   └── wrangler.toml
├── scripts/
│   ├── fetch_feeds.py          # メインフェッチャ(RETENTION_DAYS=60)
│   ├── opml_to_feeds.py        # OPML → feeds.json (merge: denylist 方式)
│   ├── inspect_failures.py     # 失敗フィード診断 + サイレント失敗検出
│   ├── snapshot.py             # GitHub 側状態 ZIP 生成
│   ├── cf_snapshot.py          # Cloudflare 側状態 ZIP 生成(update-024)
│   ├── curation_*.py           # 一括無効化等のメンテスクリプト
│   └── adapters/
│       ├── __init__.py
│       ├── base.py
│       ├── rss_adapter.py
│       ├── scrape_base.py
│       ├── kenbiya_scraper.py
│       ├── rakumachi_scraper.py
│       └── cfajapan_scraper.py
├── opml/
│   └── subscriptions.opml      # 購読定義(source of truth)
├── .github/workflows/
│   └── fetch-feeds.yml         # cron 7 */2 * * *
│                               # commit message: "chore: update feeds"
│                               # (Phase 4 で [skip ci] 削除済)
│                               # rebase-retry ロジック組込み(update-018)
├── requirements.txt
└── .gitignore                  # kk-reader-*.zip 等を除外
```
