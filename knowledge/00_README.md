# kk-reader プロジェクト Knowledge

このディレクトリには Claude プロジェクト機能の Knowledge セクションにアップロード
するドキュメント類が含まれる。

## 投入順(推奨)

1. `00_README.md` (本ファイル) — プロジェクト概要、現状サマリ
2. `10_ARCHITECTURE.md` — 4 層構成、データフロー、技術スタック
3. `20_OPERATIONS.md` — 運用フロー、ZIP 配信、適用手順
4. `30_DESIGN_TOKENS.md` — UI 設計トークン(カラー、フォント、breakpoint)
5. `40_KNOWN_ISSUES.md` — 既知の問題と過去解決済み課題
6. `50_ROADMAP.md` — 計画中の機能と購読候補
7. `60_MIGRATION_RUNBOOK.md` — Cloudflare Pages 移行記録(Phase 0〜4 完了)

## チャット開始時の儀式

新しいチャットを開いたら、最初のメッセージで以下を共有:

1. 最新の GitHub snapshot ZIP(`kk-reader-snapshot-YYYYMMDD-HHMMSS.zip`)
2. 必要なら CF snapshot ZIP(`kk-reader-cf-snapshot-YYYYMMDD-HHMMSS.zip`)
3. 取り組みたいタスク

snapshot は Knowledge ではなく**チャット添付**として渡す(古くなるため Knowledge
に置かない)。GitHub snapshot は `scripts/snapshot.py`、CF snapshot は
`scripts/cf_snapshot.py` で生成。

## このプロジェクトの目的

個人専用 RSS リーダー `kk-reader` の継続的な開発・運用。

- ライブサイト: https://kk-reader.pages.dev/(Cloudflare Access 認証必須)
- 旧ライブサイト: https://other9.github.io/kk-reader/(Phase 6 で撤去予定、現在も並行稼働)
- リポジトリ: https://github.com/other9/kk-reader(現:公開、Phase 6 で private 化予定)
- Worker: https://kk-sync.other9.workers.dev(認証ゲート付き)

## ユーザーについて(Claude が把握しておくべき)

- 東京中央区在住、3 端末利用(PC / iPhone / Android)
- 城東エリア中心の不動産投資、地政学・経済分析志向
- 技術的バックグラウンド: 不動産投資の自動分析システム構築、私募インスト
  investor の分析、wrangler/GitHub Actions 等への基本理解
- ZIP 配信スタイルを好む(コマンド列挙よりもまとめて適用できるパッケージ形式)
- 文書は構造的、歴史的・理論的に厚いものを好む

## 現在の状況(2026-05-18 時点)

進行中の課題は **Cloudflare Pages 移行の Phase 5(1〜2 週間並行運用、能動作業はほぼ無し)**。

最新の状態:
- フィード総数: **116**(成功 81 / 失敗 35)
- 記事総数: **625**
- Phase 0〜4 完了済(2026-05-17 着手 → 2026-05-18 22:21 JST 完了確認)
- cron → bot commit → Cloudflare Pages auto-rebuild の連鎖まで実機確認済
- 旧 GitHub Pages サイトと Cloudflare Pages サイトが並行稼働中

## Phase 0〜4 完了内容(2026-05-17 〜 2026-05-18 集中作業)

| Phase | 内容 | 状態 |
|---|---|---|
| 0 | SYNC_SECRET 値を旧サイトの localStorage から取得 | ✓ |
| 1 | Cloudflare Pages プロジェクト作成、kk-reader.pages.dev 配信開始 | ✓ |
| 2 | バックエンド連動検証(/state、/article、データ整合性) | ✓ |
| 3 | Cloudflare Access 認証ゲート(2 application 構成)、3 端末初回認証 | ✓ |
| 4 | GitHub Actions workflow から `[skip ci]` を除去、Pages auto-rebuild 化 | ✓ |

並行して以下の update を投入:

| Update | 内容 | 目的 |
|---|---|---|
| update-019 | Worker CORS allowlist を `kk-reader.pages.dev` + preview wildcard に拡張 | Pages 経由のアクセスを Worker に許可 |
| update-020 → 022 | `#token=<TOKEN>` URL fragment による token 投入、key 名修正 | 新端末追加を簡単に |
| update-021 → 022 | `docs/debug.html` 診断ページ追加 | 端末側で localStorage と Worker 通信を可視化 |
| update-024 | `scripts/cf_snapshot.py` 追加 | Cloudflare 側のデプロイ状態スナップショット |

## 残作業(Phase 5/6)

- **Phase 5**: 1〜2 週間並行運用、不具合観察(能動作業はほぼ無し)
- **Phase 6**: 旧 GitHub Pages サイト撤去 + repo を private 化

詳細は `60_MIGRATION_RUNBOOK.md` 参照。

## このセッションで判明した訂正事項(Knowledge 内に反映済み)

1. `localStorage` の sync token キー名は **`kkreader.syncToken`**(過去の
   Knowledge に記載されていた `kk-sync-token` は誤り、`docs/sync.js` の実装と不一致)
2. Cloudflare Pages の build skip 条件: commit message に `[skip ci]` の文字列を
   含むと、subset match で skip される。Phase 4 のときに `chore: remove [skip ci]...`
   というメッセージで commit したら、その commit 自身が skip された
3. app.js の `performSync(true)` は init() 末尾で呼ばれるが、Android では
   visibility change を契機にしないと UI に既読が反映されない場面がある
   (実害は限定的、別途調査余地)

詳細は `40_KNOWN_ISSUES.md` 参照。

## プロジェクトの規模感に関する self-check

kk-reader は「**個人インフラ**」レベルの規模で、要件(無料・3OS・スクレイピ
ング対応・データ所有)を考えると現状の構成は適正サイズ。これより小さい
構成では要件を満たせない。

ただし Phase 2/3(機能拡張)を進めるときは「**実利用での痛みが出てから着手する**」
規律を保つこと。「あったら便利」「Cloudflare に乗ってるからついで」で
着手すると過剰化する。

「frozen 化(機能追加停止、現状維持のみ)」もいつでも取れる正当な選択肢。
kk-reader はあくまで道具で、目的ではない。
