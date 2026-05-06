# kk-sync Worker

3端末間で既読・お気に入り状態を同期するための Cloudflare Worker。

## デプロイ手順(初回のみ)

### 1. KV namespace を作成

```bash
cd worker
wrangler kv namespace create STATE
```

出力例:
```
🌀 Creating namespace with title "kk-sync-STATE"
✨ Success!
Add the following to your configuration file in your kv_namespaces array:
{ binding = "STATE", id = "abc123def456789..." }
```

この `id` をメモして、`wrangler.toml` の `REPLACE_WITH_KV_ID` を置き換える。

### 2. 同期用の secret token を生成

PCのターミナルで:

```bash
openssl rand -hex 32
# 例: 7f3a9d2c8b1e4f5a6d8c9e0f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b
```

このランダム文字列が「合言葉」になる。**メモを取る**(後で各端末の設定画面に入力する)。

### 3. Worker に secret を登録

```bash
wrangler secret put SYNC_SECRET
```

プロンプトが出たら、ステップ2で生成した文字列を貼り付ける。
これは Cloudflare 側で暗号化保管され、コードや設定ファイルには現れない。

### 4. Worker をデプロイ

```bash
wrangler deploy
```

成功すると以下のような URL が表示される:
```
https://kk-sync.other9.workers.dev
```

### 5. 動作確認

```bash
# 401 が返ることを確認(認証なしのアクセスを拒否)
curl -i https://kk-sync.other9.workers.dev/state

# 200 が返ることを確認(認証ありのアクセスを許可)
curl -i -H "Authorization: Bearer <SYNC_SECRETの値>" \
  https://kk-sync.other9.workers.dev/state
# {"read":{},"fav":{}} が返ればOK
```

### 6. 各端末で設定画面に token を入力

PC・iPhone・Android のブラウザで kk-reader を開き、右上の歯車アイコン(⚙)から
設定画面を開いて、ステップ2で生成した token を貼り付ける。

または以下のような URL に1度アクセスすると自動設定される:
```
https://other9.github.io/kk-reader/?token=<SYNC_SECRETの値>
```

## 運用

### secret token のローテーション

漏洩疑いがあれば、新しい token を生成して再登録:

```bash
openssl rand -hex 32  # 新しい token を生成
wrangler secret put SYNC_SECRET  # 上書き
```

その後、各端末の設定画面で token を更新する。

### Worker のログを見る

```bash
wrangler tail
```

リアルタイムで Worker のリクエストログが流れる。

### ローカルテスト

```bash
wrangler dev
```

ローカルで `http://localhost:8787` で Worker が起動する。

### 状態のバックアップ

```bash
wrangler kv key get --binding=STATE "state:default" > state-backup.json
```

KVから現在の同期状態を取り出してファイル保存。

## アーキテクチャ

```
[PC/iPhone/Android Browser]
  ↓ 状態変更時に debounce 3秒で diff を POST
  ↓ 起動時 / タブ可視化時に GET
[Cloudflare Worker]
  ↓ Last-Writer-Wins マージ
  ↓ JSON 1個として保存(キー: "state:default")
[Cloudflare KV]
```

データサイズの目安: 1万記事を操作しても 400KB 程度。KV の値1MB上限内に余裕で収まる。
