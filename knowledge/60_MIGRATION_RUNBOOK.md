# kk-reader Cloudflare 移行 Runbook(Phase 0〜4 完了記録 + 残作業)

このドキュメントは kk-reader を GitHub Pages 配信から Cloudflare Pages + Access
配信に移行する手順書 + 実施記録。**2026-05-17〜2026-05-18 に Phase 0〜4 まで
完了**。残るは Phase 5(並行運用観察、1〜2 週間)と Phase 6(旧サイト撤去 +
private 化)。

## 全体像

```
[到達点]
  ・GitHub repo: public(Phase 6 で private 化予定、other9/kk-reader)
  ・サイト配信: Cloudflare Pages (kk-reader.pages.dev)
  ・認証ゲート: Cloudflare Access (メール OTP、Phase 3 で構築済)
  ・Worker / KV: 既存のまま無変更
  ・3 端末すべて新 URL 経由(Phase 3 で初回認証済)
  ・月額: $0

[累計所要時間]
  Phase 0-3: 集中作業 約 2 時間(2026-05-17)
  Phase 4:   約 30 分(2026-05-18)
  Phase 5:   1〜2 週間並行運用(2026-05-18 〜 進行中)
  Phase 6:   未着手(Phase 5 完了後)
```

## 設計上の判断

### Pattern B(並行運用)を採用

| パターン | repo | Worker | KV | 配信先 | データ | 工数 |
|---|---|---|---|---|---|---|
| A: 完全フォーク | 別 repo | 別 Worker | 別 namespace | 別 Pages | 別系 | 大(同期地獄) |
| **B: 別配信のみ追加** | **同じ repo** | **同じ Worker** | **同じ KV** | 別 Pages 追加 | **共通** | 小 |
| C: 別ブランチ | 同じ repo の別ブランチ | 同じ Worker | 同じ KV | 別 Pages | 共通 | 中 |

Pattern B の利点:
- 本番(GitHub Pages)と並行運用が即成立する
- 同じ Worker / 同じ KV を読むため、新旧サイト間で **データ整合性が自動的に保証**
  される(既読 / お気に入りが両方に即反映)
- 3 端末で随時 A/B 比較できる
- rollback が trivial(Pages の Custom domain を外せば旧 URL に戻る)
- コード fork による merge 競合が発生しない

### 並行構成図

```
┌────────────────────────────────────────────────────────────┐
│  GitHub repo: other9/kk-reader (main)                     │
│  └─ docs/, scripts/, worker/, opml/, ...                   │
└─────────────┬──────────────────────────┬───────────────────┘
              │ deploy                   │ deploy
              ▼                          ▼
   ┌──────────────────────┐    ┌────────────────────────────┐
   │ GitHub Pages         │    │ Cloudflare Pages           │
   │ other9.github.io/    │    │ kk-reader.pages.dev        │
   │ kk-reader/           │    │ ← Cloudflare Access 認証   │
   │ (旧、Phase 6 撤去予定)│    │ (新、3 端末で稼働中)        │
   └──────────┬───────────┘    └───────────┬────────────────┘
              │                            │
              │ /state, /article, /fetch   │ /state, /article, /fetch
              ▼                            ▼
        ┌────────────────────────────────────────┐
        │  kk-sync.other9.workers.dev (共通)     │
        │  CORS allowlist: 両 origin + preview   │
        │  KV: STATE namespace (共通)            │
        └────────────────────────────────────────┘
```

## Phase 0: 事前準備 ✓ 完了(2026-05-17)

### 実施内容

PC ブラウザで旧サイトの localStorage から `kkreader.syncToken`(過去 Knowledge
では誤って `kk-sync-token` と表記されていた)の値を取得して保存。

### 検証(済)

- 旧サイトが完全に動作している ✓
- token 値をテキストファイル等で保持 ✓

## Phase 1: Cloudflare Pages デプロイ ✓ 完了(2026-05-17)

### 実施内容

1. Cloudflare ダッシュボード → Workers & Pages → Create application
2. Pages の "Get started" → Import an existing Git repository → GitHub 連携
3. Cloudflare Workers and Pages アプリのインストール、`other9/kk-reader` のみ選択
4. Build configuration 確定:
   - Project name: `kk-reader`
   - Production branch: `main`
   - Build command: 空
   - Build output directory: `docs`
   - Root directory: 空
5. Save and Deploy → 初回ビルド成功

### 検証(済)

- https://kk-reader.pages.dev/ で旧サイトと同じ画面が表示 ✓
- localStorage に token 投入後、記事一覧が表示される ✓

### この Phase で発見した UI 変更点

- Cloudflare のリブランディングで「Zero Trust」が「Cloudflare One」表記に
- 「Pages タブ」の UI は無くなっており、Workers の "Create" 画面下部の
  "Looking to deploy Pages? Get started" リンクから入る形に変わった

## Phase 2: バックエンド連動の検証 ✓ 完了(2026-05-17)

### 想定外: CORS 問題が発覚 → update-019 で対応

**問題**: 新サイトから Worker への API 呼び出しが全て CORS preflight で弾かれた。
Worker の `ALLOWED_ORIGINS` 配列に `https://kk-reader.pages.dev` が含まれて
おらず、preflight が `https://other9.github.io` を返すため。

**update-019 で対処**: `worker/worker.js` 先頭の CORS 関連定義を拡張。
`ALLOWED_ORIGINS` に pages.dev を追加、`ALLOWED_ORIGIN_PATTERNS` を新設
(preview deployments の wildcard 対応)、`isAllowedOrigin()` 関数で統合。

### その後の検証(済)

- /state 同期(双方向、新→旧、旧→新) ✓
- /article 本文取得(楽待・健美家・CFA Society Japan) ✓
- データ整合(記事総数、フィード状態) ✓
- モバイル幅(380px)、検索フィルタ ✓

## Phase 3: Cloudflare Access 認証ゲート ✓ 完了(2026-05-17)

### 実施内容

1. Zero Trust(Cloudflare One)初期化、Team domain 設定、Free プラン選択
2. **production 用 Application**:
   - Type: Self-hosted → Public DNS(`pages.dev` は公開 DNS にあるため)
   - Application domain: subdomain 空 + `kk-reader.pages.dev`
   - Session Duration: 1 month (730h)
   - Policy: Owner only / Allow / Include Emails / 自分のメアド
3. **preview 用 Application**:
   - Subdomain: `*`(wildcard)
   - 他は同上

### Phase 3 で発見した UI 変更点

- Application 作成画面が「Self-hosted and private」配下に4サブタブ
  (Private destinations / Workers / Public DNS / Service auth)
- pages.dev のような Cloudflare 自身のドメインは Domain ドロップダウンに
  出ないので「Switch to custom input」で自由入力モードに切り替え
- Application 名は auto-generated でドメイン名が入る(ラベル違いで動作上
  問題なし)

### 検証(済)

- シークレットウィンドウで OTP 認証画面 → メアド → 6 桁コード → 通過 ✓
- 3 端末(PC / iPhone / Android)初回認証完了 ✓

### Android の token 投入で詰まった経緯(update-020〜022 + 021)

Cloudflare Access 認証は通過したが、`kkreader.syncToken` を Android に
投入する経路で詰まった。当初は bookmarklet 経由を試したが、Android Chrome
の最近の版で `javascript:` URL が omnibox + bookmark の両方で塞がれていた。

**update-020 で URL fragment 経由を実装**:
- `docs/index.html` の `<head>` 直下に bootstrap script を追加
- URL `https://kk-reader.pages.dev/#token=<TOKEN>` で開くと token が
  localStorage に投入され、URL バーからは fragment が消える
- fragment はサーバに送信されないため、server log や Referer に token は残らない

**update-021 で debug.html を追加**:
- `https://kk-reader.pages.dev/debug.html` で:
  - 現在の token 状態を可視化
  - フォームから直接 token 投入(URL fragment 経由が失敗してもこの経路で投入可)
  - /ping、/state テストボタン
- Cloudflare Access ゲートの内側で配信されるため、認証済みユーザーのみ到達可

**update-022 で localStorage key 名を修正**:
- update-020/021 は誤って `kk-sync-token` という key 名で書いていたが、
  `docs/sync.js` の実装は `kkreader.syncToken` を使う
- key 名不整合のため Android で sync が enabled にならなかった
- update-022 で両ファイルの key 名を修正、`kk-sync-token` の legacy 値が
  あれば自動 migration するロジックも追加

## Phase 4: cron 連動の修正 ✓ 完了(2026-05-18)

### 実施内容

`.github/workflows/fetch-feeds.yml` の commit message 2 箇所(initial commit +
retry-with-rebase 経路、update-018 で追加された)から `[skip ci]` を削除。

```bash
sed -i.bak 's/ \[skip ci\]//g' .github/workflows/fetch-feeds.yml
rm .github/workflows/fetch-feeds.yml.bak
```

### Phase 4 で発覚したサブ問題: Cloudflare Pages の skip ci substring match

Phase 4 の commit message `chore: remove [skip ci] to enable Cloudflare Pages
rebuild on cron` は **Cloudflare Pages 側で文字列としての `[skip ci]` を
検出して** skip された。`docs/` を変更していないので実害ゼロだが、教訓として
`40_KNOWN_ISSUES.md` に記録。

### 検証(済)

Phase 4 commit `a8a5421` 後、次の cron(2026-05-18 22:21 JST)で bot commit
`f407b3d` が出て:
- commit message: `chore: update feeds`(`[skip ci]` 無し)✓
- Cloudflare Pages → Deployments で `f407b3d` 対応の build が **deploy/success** ✓

これで「cron → bot commit → Pages auto-rebuild → 新サイト更新」の連鎖が
完全に機能している実機確認完了。

### CF snapshot で検証可能(update-024)

`scripts/cf_snapshot.py` で生成した snapshot の `pages_deployments.items[]`
を見れば、`f407b3d` 以降の bot commit が **`is_skipped: false`** で全て
deploy 成功していることを確認できる。

## 残作業

### Phase 5: 3 端末への並行運用観察(現在進行中、1〜2 週間)

PC / iPhone / Android すべてで新サイトを使用中。能動作業はほぼ無く、以下を
記録・観察する:

```text
□ 認証 OTP の頻度(1 ヶ月セッションが想定通りに効くか、月 1 回程度)
□ 端末固有の崩れ(タイポグラフィ、tap area、横スクロール等)
□ Pages の月間 build 数(500/月 Free 枠の確認、想定 ~370/月)
□ Cloudflare Access の認証ログ(Zero Trust → Logs)
□ Android の初回ロード時 sync 反映の安定性
```

Phase 5 期間中に Phase 2 翻訳機能の前提条件は揃うので、希望すれば並行して
着手可能。

### Phase 6: 旧サイト撤去 + private 化(Phase 5 完了後、30 分作業 + 1 週間放置)

#### 前提条件

```text
□ Phase 5 で 3 端末すべて新サイトで安定稼働して 1 週間以上経過
□ 大きな不具合がない
□ 月間 Pages builds 数が許容範囲(450 以下が望ましい)
```

#### 6-A: 旧サイトの publish 停止

```text
1. GitHub repo → Settings → Pages
2. Source → "Deploy from a branch" → "None" に変更 → Save
3. https://other9.github.io/kk-reader/ が 404 になることを確認
4. 3 端末の古いブックマーク/ショートカットを削除
```

#### 6-B: 1 週間放置(任意だが推奨)

```text
□ 1 週間、新サイト一本で運用継続
□ 想定外の依存(他人にシェアしていた URL 等)が発覚しないことを確認
```

#### 6-C: repo を private 化

```text
1. GitHub repo → Settings → General → 一番下までスクロール
2. Danger Zone → "Change repository visibility" → "Make private"
3. 確認ダイアログで "other9/kk-reader" をタイプして確定
4. Make private
```

#### 6-D: 動作確認(repo private 化後)

```text
□ Cloudflare Pages が依然として GitHub から build できる
   - Pages → Deployments → 直近の build が success
   - cron による次回 build も成功する
□ GitHub Actions が動作する(2000 min/月 Free 枠内)
□ 新サイトが通常通り動作
```

#### 6-E: ドキュメント更新

Knowledge ドキュメントの記述を整合化(本ドキュメント自身も "Phase 6 完了"
として書き換え)。

#### 6-F: 最終 snapshot

GitHub snapshot + CF snapshot の両方を取って保存。次回チャットでの reference
material として。

### Rollback トリガと手順

| Phase | rollback コスト | 方法 |
|---|---|---|
| 1 | 1分 | Pages プロジェクト Delete |
| 2 | 1分 | Phase 1 と同じ |
| 3 | 2分 | Zero Trust → Applications → Delete |
| 4 | 5分 | workflow の `[skip ci]` を戻して push |
| 6-A | 1クリック | GitHub Pages の Source を main 等に戻す |
| 6-C | 1クリック | repo を public に戻す |

Pre-flight の snapshot ZIP があれば、最悪のケースでも数日前の状態に復元可能。

## 今回の集中作業で得られた教訓

1. **Knowledge ドキュメントは実装と照合してから信用する**
   - `kk-sync-token` という誤った key 名を Knowledge から拾って patch を書き、
     update-020/021 が動かなかった
   - 既存実装に依存する patch を書く前に `cat docs/sync.js` 等で実コードを確認
2. **commit message に `[skip ci]` の文字列を含めない**
   - Cloudflare Pages は substring match で skip 判定する(意図的な仕様)
   - 説明的に言い換える
3. **Cloudflare の UI は頻繁に変わる**
   - 「Zero Trust」→「Cloudflare One」リブランド
   - Application 作成画面のサブタブ追加(Public DNS 等)
   - Knowledge / runbook 上の UI 説明は陳腐化しやすいので「画面が違ったら
     スクショ送って」を recovery path にしておく
4. **API token の scope は最小権限から始める**
   - 既存の `CLOUDFLARE_API_TOKEN` には Access scope が無く、cf_snapshot.py で
     一部 section が取れなかった
   - 必要になった都度追加するスタイルが安全(過剰権限を持たせない)
5. **diagnostic page (debug.html) は早めに用意する価値がある**
   - bookmarklet / `javascript:` が塞がれた端末でも GUI で診断できる
   - 端末追加・障害切り分けの両方で再利用できる
   - 1 ファイル ~10KB の追加で長期的に投資効果が高い

## なぜやったか(動機の再確認)

1. **「より少ない金額で、より強い private 化」が達成できる珍しい構造**
   - GitHub Pro $4/月: 層 1 のみ private(live サイトは public)
   - Cloudflare Pages + Access $0/月: 層 1 + 層 2 完全 private
2. **URL 変更コストは時間とともに増える** — 3 端末で済む今のうちに
3. **Phase 2 翻訳機能を Cloudflare 同一プラットフォームで実装できる** —
   Workers AI binding が Pages Functions から直接呼べる、外部 API key 管理不要
4. **GitHub Pro $4/月の継続課金を回避** — 年 $48、5 年で $240

## やらない判断もある

Phase 5/6 を進めない判断も完全に正当。Phase 4 まで完了している現状でも、

- 旧サイト撤去せずに「両方稼働させ続ける」運用は可能(月 0 円のままで継続可能)
- repo を private 化しない判断も可能(機能的には差が無い)

「完全 private 化」というゴールに価値を感じない場合、Phase 5/6 は無理に進めない。
「実利用での痛みが出てから着手する」規律(`00_README.md` の self-check 節)を
ここでも適用可能。

## 進捗記録

```text
[x] Phase 0 完了 (2026-05-17 ~20:00 JST): SYNC_SECRET 取得
[x] Phase 1 完了 (2026-05-17 ~20:15 JST): Pages デプロイ
[x] Phase 2 完了 (2026-05-17 ~21:00 JST): 検証(CORS問題で update-019 発生)
[x] Phase 3 完了 (2026-05-17 ~23:00 JST): Access 認証ゲート(端末投入で update-020~022 発生)
[x] Phase 4 完了 (2026-05-18 22:21 JST): cron commit から [skip ci] 削除、実機確認済
[ ] Phase 5 (進行中、2026-05-18 〜): 並行運用観察
[ ] Phase 6 (未着手): 旧サイト撤去 + repo private 化
```

進行中の Phase で詰まった場合、Phase 番号と症状を Claude に伝えれば個別対応
可能。本ドキュメントを Knowledge に置いたまま、新しい chat で Phase を進める
形でも回せる。
