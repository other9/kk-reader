# kk-reader

個人専用 RSS リーダー。Cloudflare Pages + Workers + KV + GitHub Actions による
4 層構成。本ファイルは Claude Code(repo ベースのアシスタント)が最初に読む
エントリポイント。詳細は `knowledge/` 配下のドキュメントを参照すること。

## ドキュメントの読み順

| ファイル | 内容 |
|---|---|
| `knowledge/00_README.md` | プロジェクト概要、現状サマリ、ユーザーについて |
| `knowledge/10_ARCHITECTURE.md` | 4 層構成、データフロー、技術スタック |
| `knowledge/20_OPERATIONS.md` | 運用フロー、ZIP 配信、適用手順 |
| `knowledge/30_DESIGN_TOKENS.md` | UI 設計トークン(カラー、フォント、breakpoint) |
| `knowledge/40_KNOWN_ISSUES.md` | 既知の問題と過去解決済み課題 |
| `knowledge/50_ROADMAP.md` | 計画中の機能と購読候補 |
| `knowledge/60_MIGRATION_RUNBOOK.md` | Cloudflare Pages 移行記録(Phase 0〜4 完了) |

最新の進行状況は `00_README.md` の "現在の状況" 節に集約されている。

## このリポジトリで一番大事な約束事

### 1. localStorage の sync token key

`docs/sync.js` の `SYNC_STORAGE.token` の値、すなわち
**`kkreader.syncToken`** が正。過去のドキュメントには `kk-sync-token` という
誤記が残っていた時期があったため、新しい patch を書く前は実コードを `cat
docs/sync.js` で確認すること。

### 2. commit message に `[skip ci]` の文字列を含めない

Cloudflare Pages は commit message に対して **substring match で `[skip ci]`
を検出して build を skip する**(意図的な仕様)。「`[skip ci]` を解除する」
旨の commit を書いてもその commit 自身が skip されるという罠がある。説明的に
言い換えること(例: `chore: enable Cloudflare Pages auto-rebuild on cron commits`)。

### 3. Worker 変更時の smoke test は必須

`worker/worker.js` を変更したら `wrangler deploy` 直後に必ず以下の 4 点を
curl で確認:
- `/ping`(疎通)
- `/article`(健美家既知 URL での本文抽出)
- `/fetch`(楽待プロキシ取得)
- CORS preflight(`https://kk-reader.pages.dev` Origin で OPTIONS)

具体コマンドは `knowledge/20_OPERATIONS.md` の「Worker 変更時の smoke test」節。
TOKEN が ASCII 範囲外文字 or placeholder のままにならないよう
事前チェックも同節に記載されている。

### 4. スクレイピング系を弄る前に実 HTML を見る

adapter (`scripts/adapters/*.py`) や Worker `/article` の selector を修正する
時は、推測ベースの heuristic を書く前に Worker `/fetch` で実 HTML を取り
寄せて DOM 構造を確認すること。これを省くと複数ターン修正を繰り返す。
手順は `knowledge/20_OPERATIONS.md` の「スクレイピング系修正時は実 HTML を
見てから」節。

### 5. feeds.json の構造

`docs/data/feeds.json` の top-level は **`{"feeds": [...]}` の dict 構造**
で、直接 list ではない。migration script を書く前に必ず実物を確認すること
(過去 update-016.1 で AttributeError 事故あり)。

### 6. ZIP 配信の規約

更新は `kk-reader-update-{NNN}-{slug}.zip` 形式。`UPDATE.md` を同梱して
適用手順を明記する。ZIP 内はリポジトリルートを起点とした相対パス。
適用後は `UPDATE.md` を削除する(`.gitignore` 済)。詳細は
`knowledge/20_OPERATIONS.md` の「ZIP 配信パターン」節。

## 機密情報

リポジトリには絶対に置かない:

- `SYNC_SECRET` — Cloudflare 側、`wrangler secret put` 経由で管理
- `WORKER_TOKEN` — GitHub Actions Repository Secrets、`SYNC_SECRET` と同値で運用
- `CLOUDFLARE_API_TOKEN` — GitHub Codespaces Secrets で管理
- メールアドレス全般、Cloudflare account ID 以外の identifier

過去事故: `worker/.wrangler/cache/wrangler-account.json` がメアド込みで
public リポジトリに混入し、`git filter-repo` で 23 commit から履歴削除する
事態になった(2026-05-06)。`.gitignore` と `scripts/snapshot.py` の
`EXCLUDE_TOKENS` で再発防止済み。

## このリポジトリの移管経緯

このリポジトリの運用ドキュメントは元々 Claude.ai 上の Project Knowledge 機能
で管理されていた。Claude Code はその Knowledge を参照できないため、
2026-05-22 に全コンテンツを `knowledge/` 配下に取り込んだ(update-025)。

以降、`knowledge/` 配下が source of truth。更新はこのリポジトリへの commit を
通じて行う。Claude.ai の Project Knowledge 側は不要となったため削除して構わない。

snapshot ZIP(`scripts/snapshot.py`)に `knowledge/` と `CLAUDE.md` を含める
には、`INCLUDE_PATHS` への追加が必要。詳細は本 update の `UPDATE.md` 参照。

## ユーザーについて

- 東京中央区在住、3 端末利用(PC / iPhone / Android)
- 城東エリア中心の不動産投資、地政学・経済分析志向
- 不動産投資の自動分析システムを自前で運用、wrangler/GitHub Actions 等への
  基本理解あり
- **ZIP 配信スタイルを好む**(コマンド列挙よりまとめて適用できるパッケージ形式)
- 文書は構造的、歴史的・理論的に厚いものを好む

## 着手規律

`00_README.md` 末尾の self-check 節を必ず確認すること。「あったら便利」「ついで」
で機能追加を始めると過剰化する。

> 「frozen 化(機能追加停止、現状維持のみ)」もいつでも取れる正当な選択肢。
> kk-reader はあくまで道具で、目的ではない。
