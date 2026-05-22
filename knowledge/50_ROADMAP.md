# kk-reader ロードマップ

## 現状の購読分布(2026-05-18 時点)

総数 **116** / アクティブ 81 / 取得成功 81 / 失敗 35 / 記事総数 **625**。

| カテゴリ | 記事数 | 主な内容 |
|---|---|---|
| 不動産 | 416 | 健美家、楽待×3 (編集部 / 連載 / 実践大家、Worker proxy)、URBANSPRAWL、のらえもん、東京マンション等 |
| 金融・経済・投資 | 163 | CFA Society Japan ブログ、himaginary、市況かぶ全力 2 階建、本石町日記、CFA 学習方法 Tips、山崎元等 |
| ブログ | 41 | 中国・上海・東南アジア・米国政治・データ分析等 |
| 未分類 | 残り | Quants/finance: Mock Quant、RUM、ハリセルダン、ウォールストリート日記等 |

直近 24h published: 21 件、直近 1 週間: 176 件、直近 1 ヶ月: 349 件、それ以前: 74 件。

## 累計 update 履歴(マイルストーン)

update-018 までの履歴は `40_KNOWN_ISSUES.md` を参照。直近の流れ:

- ~~update-018: cron push レース対策(workflow rebase-retry)~~ → 完了
- ~~Phase 0〜4: Cloudflare Pages 移行集中作業(2026-05-17〜2026-05-18)~~ → 完了
- ~~update-019: Worker CORS allowlist 拡張~~ → 完了
- ~~update-020〜022: URL fragment による token 投入 + localStorage key 名修正~~ → 完了
- ~~update-021〜022: docs/debug.html 診断ページ~~ → 完了
- ~~update-024: scripts/cf_snapshot.py で CF 側スナップショット~~ → 完了

(update-023 は構想したが Android 同期問題が別経路で解決して未配信)

## 構造的ギャップ(変わらず)

現状で薄い領域:

- **シンクタンク研究レポート**: 0 本(ニッセイ基礎研で穴埋め予定)
- **業界統計データソース**: 0 本
- **重量級エコノミスト個人**: 山崎元のみ(野口悠紀雄等不在)
- **政策研究機関**: 0 本

これを埋めるための候補が以下の Tier 1〜5。

## 推奨フィード Tier 別

### Tier 1: シンクタンク・研究機関(最優先)

ユーザーの関心(マクロ経済・地政学・不動産・REIT)に最もインパクトがある層。

| # | フィード | URL | 状態 | 備考 |
|---|---|---|---|---|
| 1 | ニッセイ基礎研究所 | `https://www.nli-research.co.jp/rss/?data_format=xml&site=nli` | ✅ 検証済 | 経済・金融・不動産・REIT・年金・中国/アジア |
| 2 | RIETI コラム | `https://www.rieti.go.jp/jp/rss/columns_jp.xml` | 要確認 | 経済産業研究所 |
| 3 | 大和総研 | `https://www.dir.co.jp/rss/index.xml` | 要確認 | マクロ経済予測、金利・為替・株 |
| 4 | 三井住友トラスト基礎研究所 | サイト要確認 | 要調査 | REIT/不動産専業の最高峰 |

### Tier 2: 不動産業界(投資直接補強)

| # | フィード | URL | 状態 |
|---|---|---|---|
| 5 | 健美家コラム&ニュース | `https://www.kenbiya.com/ar/` | ✅ **取得成功** |
| 6 | 楽待新聞 編集部 | `https://www.rakumachi.jp/news/column` | ✅ **取得成功**(via_worker) |
| 7 | 楽待 連載コラム | `https://www.rakumachi.jp/news/series` | ✅ **取得成功**(via_worker) |
| 8 | 楽待 実践大家 | `https://www.rakumachi.jp/news/practical` | ✅ **取得成功**(via_worker) |
| 9 | SUUMO ジャーナル | `https://suumo.jp/journal/feed/` | 要確認 | マンション市場マクロ |

### Tier 3: 地政学・アジア・国際

| # | フィード | URL | 状態 |
|---|---|---|---|
| 10 | JETRO ビジネス短信 | `https://www.jetro.go.jp/biznews_rss/` | 要確認 | 中国・東南アジアのビジネス短信 |
| 11 | 東京財団政策研究所 | サイト要確認 | 要調査 | 国際関係・安全保障・財政 |
| 12 | アジア経済研究所(IDE-JETRO) | `https://www.ide.go.jp/Japanese/Rss/` | 要確認 | 新興国経済 |

### Tier 4: 重量級エコノミスト個人

| # | フィード | URL | 状態 |
|---|---|---|---|
| 13 | 野口悠紀雄 Online | サイト要確認 | 要調査 |
| 14 | 池田信夫 blog | `https://agora-web.jp/feed/` (Agora) | 要確認 |
| 15 | 山形浩生 cruel.org | `https://cruel.hatenablog.com/feed` | 要確認 |

### Tier 5: 専門業界誌・翻訳系

| # | フィード | URL | 状態 |
|---|---|---|---|
| 16 | CFA Society Japan ブログ | `https://www.cfasociety.org/japan/society-news-resources/blog` | ✅ **取得成功**(update-016 scrape_cfajapan、via_worker) |

## 次の候補(優先順位は好みによる)

1. **★ Phase 5 観察期間(2026-05-18〜)**: 1〜2 週間、能動作業ほぼ無し
2. **★ Phase 6 旧サイト撤去 + private 化**(Phase 5 完了後、所要 30 分 + 1 週間放置)
3. **死亡フィード棚卸し**(失敗 35 件のうち恒久死亡を選別)
4. **Tier 1: ニッセイ基礎研究所 RSS 追加**(検証済 URL あり、5 分)
5. **Worker smoke test スクリプト化**(`scripts/smoke_test_worker.sh`)
6. **Knowledge 訂正の徹底**: `kk-sync-token` 表記が他に残っていないか grep
7. **Phase 2: 翻訳機能設計開始**(前提条件すべてクリア、移行完了で同一プラットフォーム化済)
8. **Phase 3 候補**: マルチ token 対応、TZ-aware prune、検索強化(D1)等

着手規律: **「実利用での痛みが出てから着手する」**。「あったら便利」「Cloudflare
に乗ってるからついで」で着手すると過剰化する(`00_README.md` の self-check
節参照)。

## Phase 2: 翻訳機能(設計済、未実装)

update-007 で構築 + update-010/011/015 で fix した Worker `/article` エンド
ポイントは翻訳機能の素地として最適。Cloudflare Pages 移行完了で同一プラット
フォーム化したため、Workers AI binding を Pages Functions から直接呼べる
構成も可能になった。

### 設計概要

```
GET /article?url=X                  → 原文(現行)
GET /article?url=X&translate=ja     → 日本語訳(追加)

KV キー:
article:v3:<sha256(url)>        → 原文
article:v3:<sha256(url)>:ja     → 日本語訳
```

cache キーが既に v3 にバンプ済みなので、翻訳機能追加時に再 bump (v4) する
余地もある。

### 実装範囲(見積 +200 行程度)

- Worker `/article` に `translate` パラメータ追加: ~50 行
- 翻訳 API クライアント統合: ~80 行
- KV キャッシュキー二重化: ~20 行
- フロントエンド: 言語切替 UI: ~60 行

### 翻訳 API 候補(優先度順)

1. **Cloudflare Workers AI** (`@cf/meta/m2m100-1.2b`): 同じ Cloudflare 網内で
   完結、10,000 Neurons/日 無料、binding 経由で呼び出し可能。**最有力候補**
   (Pages 移行後の同一プラットフォーム集約効果)
2. **DeepL API Free**: 50 万字/月無料、品質高い、$5.49/100 万字超過後
3. **Anthropic Claude API**: 文脈考慮で最高品質だがコスト高、技術記事向け

推奨構成: Workers AI を主、品質に不満があれば DeepL に切替検討。

### UI 設計

詳細ビューに `[原文][日本語訳]` トグルボタン。
言語自動検出で日本語サイトはトグル非表示。
ユーザー設定で「常に原文 / 常に翻訳」プリセット可能。

### 着手前のチェックリスト

- [x] 楽待が取得できるようになっている (update-009)
- [x] Worker /article が安定動作している (update-010/011/015)
- [x] Worker /article のキャッシュが動作している (cache_hit 観測済み)
- [x] `_anchor_title_text` が安定 (update-014)
- [x] エンティティ二重エンコード問題が解消 (update-015)
- [x] Slow-publish 系も visible (update-017)
- [x] Cloudflare Pages 移行完了(同一プラットフォーム化、binding 利用)Phase 0〜4 まで
- [ ] Phase 6 完了で repo + サイト共に private 化
- [ ] 月間翻訳量の試算(過去 30 日の英語記事数 × 平均字数)

## Phase 3 候補(未確定)

### マルチ token 対応

会社環境用の token と個人用 token を分離。会社用 token を漏洩させても、
ローカル環境(個人スマホ)に影響を与えない構造。

現状 `WORKER_TOKEN` を `SYNC_SECRET` と同値で運用しているのは、Phase 3 で
分離する余地を残すための設計判断。

### prune の TZ-aware 比較化

`fetch_feeds.py` の prune は ISO 文字列の lexicographic 比較で実装されており、
タイムゾーン offset 違いの文字列で正しく比較できない潜在 bug がある。
update-017 で RETENTION_DAYS=60 にしたことで実害は消えたが、根本対処として
TZ-aware datetime に変換してから比較するのが正しい。実装は ~10 行。

### 検索強化(D1)

現状: タイトル・カテゴリ・ソースの substring 検索のみ。

Cloudflare Pages 移行後は D1(SQLite + FTS5)が同一プラットフォームで利用可能:

- D1 に content_html を index
- Worker `/search?q=...` エンドポイントで FTS5 検索
- bindings 設定 1 行(`wrangler.toml` に `[[d1_databases]]` 追加)
- 無料枠 5GB ストレージ

着手規律: **実利用で検索が辛いと感じてから**。現状の substring 検索で困って
いない場合、技術的好奇心の発露でしかない。

### ML ベース推薦

過去の既読・お気に入り履歴から、未読記事に対する優先度スコアを付与。
Cloudflare Workers AI(Llama-3.1-70b 等)で edge スコアリング可能。
116 フィードで recommendation engine を回す動機は薄い、スルー推奨。

### 画像プロキシ(必要に応じて)

Referer や Cookie でホットリンク防止しているサイトの画像が、現状の
「URL を絶対化するだけ」のアプローチでは取れない可能性。発生時に
Worker `/img?url=X` プロキシエンドポイントを追加することで対応可能。
実装はシンプル(`/fetch` の image 版相当)で、~50 行程度。

### お気に入り記事の永続表示

現状、`fetch_feeds.py` の prune が 60 日経過記事を articles.json から削除
するため、お気に入りでも UI から消える(`40_KNOWN_ISSUES.md` 参照)。

改善案 A: prune 時に Worker `/state` から お気に入り集合を取得し、それらの id
を持つ記事は除外する特例を追加。実装は ~20 行 + 1 ネットワーク呼び出し。

改善案 B(より強力): R2 に「お気に入り記事の不変アーカイブ」を保存。Pages 移行
後は R2 が同一プラットフォームで利用可能、10GB 無料 + egress 無料。

着手規律: 60 日経って消えて困った事例が複数回起きてから。

### Android 初回ロード sync 反映

`docs/app.js` の `init()` 末尾で `performSync(true)` を呼んでいるが、Android
では UI に反映されない場合がある(visibility change が必要)。詳細は
`40_KNOWN_ISSUES.md` 参照。

候補対処:
- `init()` 末尾の `performSync(true)` 完了後に `renderArticleList()` を再呼び出し
- または `loadData()` → `performSync(true)` → `render` を直列で await

実用上はタブ切替で回復するので優先度は低め。Phase 5 で実害が頻繁に出るなら
別 update で対応。

### HTMLRewriter text chunk buffering

update-015 で entity preservation を入れたが、HTMLRewriter が稀に entity
reference を chunk 境界で分割する可能性はゼロにできない。実際に顕在化したら、
text chunk を element 単位で buffer して一括処理する版にリファクタする想定。

## 棚卸しとメンテナンス

### 定期メンテナンス(月 1 程度)

- `inspect_failures.py` で失敗フィード + サイレント失敗を確認、404 続きは無効化
- 新規候補フィードがないか、Tier 1〜5 の未着手項目をレビュー
- snapshot ZIP のサイズが肥大化していないか確認(20MB 超なら対応)
- KV ストレージ使用量確認(`cf_snapshot.py` の `kv_keys.by_prefix` でも見える)
- Cloudflare Pages の月次 build 数(500/月 Free 枠、現状想定 360)
- Cloudflare Access の認証ログ(Zero Trust → Logs)
- 月次 Actions minutes(2000/月 Free 枠、現状実測 ~1100)

### Worker 系の変更時のチェック

`20_OPERATIONS.md` の「Worker 変更時の smoke test」節を参照。`/ping` →
`/article` (健美家既知 URL) → `/fetch` (楽待) → CORS preflight の 4 点を
`wrangler deploy` 直後に必ず確認する運用。

### スクレイピング系の変更時のチェック

`20_OPERATIONS.md` の「スクレイピング系修正時は実 HTML を見てから」節を
参照。**listing パーサや `_anchor_title_text` を弄る前に Worker `/fetch` で
実 HTML を取り寄せて DOM を確認する**。

### 機密管理の定期確認

`40_KNOWN_ISSUES.md` 末尾の「機密管理」節のコマンドで、メアドや token が
履歴に混入していないか定期チェック。

## 「frozen 化」という選択肢

機能追加を停止し、現状維持のみとする判断はいつでも取れる。Phase 4 まで
来た kk-reader は十分に安定しており、これ以上機能追加しなければ運用は cron
が走るだけの状態に落ちる。月次メンテ時間ほぼゼロで回り続ける。

「これで完成」と宣言する判断も、Phase 2/3 を全て追う判断も、どちらも正当。
kk-reader はあくまで道具で、目的ではない。
