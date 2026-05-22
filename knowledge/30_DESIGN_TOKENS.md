# kk-reader UI 設計トークン

## カラーパレット(2026-05 時点 確定)

緑アクセントテーマ。emerald 系を採用、白/暗黒基調を切替可能。

### Light モード

```css
--bg:        #ffffff;
--bg-sunken: #f8f9f8;
--ink:       #14181a;
--ink-mid:   #4a5258;
--ink-dim:   #7c858b;
--accent:    #166534;  /* emerald-800 */
--gold:      #9a7e3a;  /* お気に入り星マーク等 */
--rule:      #e5e8e6;
--rule-strong: #c8d0cc;
```

### Dark モード

```css
--bg:        #0d100e;
--bg-sunken: #161a17;
--ink:       #e5e8e6;
--ink-mid:   #aab2af;
--ink-dim:   #6f7874;
--accent:    #4ade80;  /* emerald-400(明度を上げて読みやすく) */
--gold:      #c2a35b;
--rule:      #2a2f2c;
--rule-strong: #3a413d;
```

## タイポグラフィ

### フォントファミリー

```css
--mono: "SF Mono", "Menlo", "Consolas", "Liberation Mono", monospace;
/* 本文・UI は system font stack */
```

### モバイル文字サイズ(update-006 で確定)

経緯: 初期実装は PC で適切でもモバイルで小さすぎ、可読性に難があった。
スマホでの読みやすさを重視して以下に確定:

```css
/* 通常モバイル(380px 超) */
.row-title       { font-size: 18px; }
.row-summary     { font-size: 14.5px; -webkit-line-clamp: 3; }  /* 2→3 行に拡張 */
.detail-body     { font-size: 17px; }
.detail-title    { font-size: 26px; }

/* 極小モバイル(≤380px) */
@media (max-width: 380px) {
  .row-title     { font-size: 17px; }
  .row-summary   { font-size: 14px; }
}
```

### デスクトップ

```css
.row-title       { font-size: 16px; }
.row-summary     { font-size: 13.5px; -webkit-line-clamp: 2; }
.detail-body     { font-size: 16px; }
.detail-title    { font-size: 28px; }
```

## レイアウト

### 3 ペイン構成(デスクトップ)

```
┌─────────┬──────────────┬────────────────────────┐
│ Sidebar │  Article     │  Detail                │
│ ~240px  │  list        │  view                  │
│         │  ~480px      │  flex: 1               │
└─────────┴──────────────┴────────────────────────┘
```

### モバイル

幅 ≤900px で 1 ペインに切替、画面遷移で表示を出し分け。

## インタラクション

### キーボード操作

```
j / k: 次/前の記事
m: 既読切替
f: お気に入り切替
o: 元記事を新タブで開く
u: 未読のみフィルタ
/ : 検索フォーカス
```

### スマホでの優先操作

- リスト → 記事タップ → 詳細フルスクリーン → 戻るボタンでリストに戻る
- 既読/お気に入り/元記事ボタンは詳細ビューの上部に配置

## トップバー

2 段構成を維持(モバイルでも):

- 上段: ロゴ "kk reader"、フィルタボタン群、件数
- 下段: 検索ボックス

折り返さないよう padding を最小化。

## ステータス表示(サイドバー下部)

```
ステータス
2026/5/18 22:21:31
取得: 81 / 失敗: 35
2 時間ごとに自動取得
```

リアルタイムにフィード状態を可視化。`feeds.json` の statistics から計算。

## アイコン

- お気に入り: `★` (満) / `☆` (空)
- 既読切替: `●` (未読) / `○` (既読)

絵文字は使わない。テキスト記号のみ。

## ローディング・エラー状態(update-007 で追加)

詳細ビューで本文を Worker から取得中の表示:

```css
.spinner {
  width: 28px;
  height: 28px;
  border: 3px solid var(--rule);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: kk-spin 0.8s linear infinite;
}

.lazy-error {
  border-left: 3px solid #c0392b;  /* ← 警告のみここだけ赤系 */
  background: var(--bg-sunken);
  padding: 20px;
}
```

メッセージは日本語、テキストは Mono フォントで「本文を取得中…」と統一。

## docs/debug.html(update-021/022)のトークン

`/debug.html` はメインアプリと同じ CSS variables を使う独立ページ。
追加の design token は持たない:

- `.section` / `.row` / `.row-h` / `.stat` のフラットな block 構成
- 状態 badge: `.badge.ok`(accent 背景)/ `.badge.err`(エラー赤背景)/
  `.badge.idle`(rule-strong 背景)
- 入力欄は `--mono` font、12px、`--rule-strong` border
- ボタンは 13px、`min-height: 36px`(モバイルタッチ対応)
- pre 出力は `--mono`、11px、`max-height: 280px` + overflow

dark mode は `@media (prefers-color-scheme: dark)` で自動切替、システム設定に
追従。
