# セットアップ手順

このドキュメントの手順に従えば、コーディング不要でデプロイできます。
所要時間: 10〜15分。

## 前提

- GitHubアカウント(無料で可)
- Webブラウザのみ(ローカルでのコマンド実行不要)

## ステップ1: GitHubリポジトリを作る

1. [github.com](https://github.com) にログイン
2. 右上 `+` → `New repository`
3. 設定:
   - **Repository name**: `kk-reader`(任意の名前)
   - **Visibility**: **Private**(購読リストが含まれるので非公開推奨)
   - **Initialize this repository with**: 何もチェックしない
4. `Create repository` をクリック

## ステップ2: ZIPをアップロード

このプロジェクトのZIPファイルを展開してから、リポジトリにアップロードします。

### 方法A: ブラウザからドラッグ&ドロップ(推奨)

1. ZIPをローカルで展開する
2. 作ったリポジトリのページで、`uploading an existing file` リンクをクリック
   (リポジトリが空の場合、画面中央に表示されます)
3. 展開したフォルダの **中身を全選択**(`.github`、`docs`、`opml`、`scripts`、`README.md`、`SETUP.md`、`requirements.txt`)してドロップ

   重要: フォルダ自体ではなく **中身** をアップロードしてください。
   `.github` のような隠しフォルダも忘れずに含めてください。

4. 一番下にスクロールして `Commit changes` をクリック

### 方法B: GitHub Codespacesで展開(ZIPが大きい場合)

1. リポジトリページで `<> Code` ボタン → `Codespaces` タブ → `Create codespace on main`
2. Codespaces起動後、ZIPをエクスプローラー(左側)にドラッグ&ドロップ
3. ターミナルで:
   ```bash
   unzip kk-reader.zip
   mv kk-reader/* kk-reader/.[!.]* .
   rmdir kk-reader
   git add -A
   git commit -m "initial setup"
   git push
   ```

## ステップ3: GitHub Pagesを有効化

1. リポジトリページの上部メニュー → **Settings**
2. 左サイドバー → **Pages**
3. `Build and deployment` セクション:
   - **Source**: `Deploy from a branch`
   - **Branch**: `main` を選び、フォルダは `/docs` を選ぶ
4. `Save` をクリック
5. 数十秒待つと、ページ上部に `Your site is live at https://[ユーザー名].github.io/kk-reader/` のような表示が出ます

⚠️ **Privateリポジトリでも GitHub Pages は無料プランで公開URLになります。**
URLを知っている人は誰でもアクセス可能です。完全な非公開が必要な場合は、
GitHub Pro($4/月)で `Private` 設定の Pages を使うか、Cloudflare Pages 等への移行が必要です。

ただし、URLは推測困難な形式なので、**実質的に隠れている** 状態にはなります。

## ステップ4: GitHub Actions の権限設定

1. リポジトリ → **Settings** → 左 **Actions** → **General**
2. ページ下部の **Workflow permissions** セクションで:
   - **Read and write permissions** を選択
   - **Allow GitHub Actions to create and approve pull requests** にチェック
3. `Save` をクリック

## ステップ5: 初回フェッチを実行

1. リポジトリ上部 **Actions** タブ
2. 左サイドバー → **Fetch RSS feeds**
3. 右側 **Run workflow** ボタン → **Run workflow**(緑のボタン)
4. 30秒〜数分待つと完了する
5. 完了後、再度 **Actions** タブを開いて `chore: update feeds` のコミットがあることを確認

## ステップ6: 動作確認

1. ブラウザで `https://[ユーザー名].github.io/kk-reader/` を開く
2. サイドバーにカテゴリ(不動産、金融・経済・投資 等)が表示される
3. 中央に記事リストが表示される
4. 記事をクリックすると右側に詳細表示
5. ★ボタンでお気に入り、●ボタンで未読/既読の切替

## 操作方法

### マウス
- カテゴリクリック: そのカテゴリのみ表示
- 記事クリック: 詳細表示 + 自動既読化
- ★クリック: お気に入り切替
- 「未読のみ」ボタン: 既読を非表示
- 「既読化」ボタン: 表示中をすべて既読

### キーボード
| キー | 動作 |
|------|------|
| `j` / `k` | 次/前の記事へ |
| `m` | 選択中記事の既読/未読切替 |
| `Shift`+`M` | 表示中をすべて既読 |
| `f` | 選択中記事のお気に入り切替 |
| `o` | 選択中記事を新タブで開く |
| `u` | 「未読のみ」フィルタ切替 |
| `/` | 検索ボックスにフォーカス |
| `Esc` | 詳細表示を閉じる(モバイル) |

## トラブルシューティング

### Actionsが失敗する
- `Settings` → `Actions` → `General` で **Read and write permissions** が選択されているか確認
- `Actions` タブで失敗したワークフローを開き、エラーログを確認
- 多くは `git push` 権限不足が原因

### 記事が表示されない
- `Actions` タブで `Fetch RSS feeds` が成功しているか確認
- ブラウザの開発者ツール(F12)→ Network タブで `articles.json` の取得状況を確認
- 強制リロード(`Ctrl+Shift+R`)で キャッシュをクリア

### 一部のフィードが取得できない
- これは正常です。OPMLには10年以上前のフィードも含まれており、サイトが消滅している場合があります
- サイドバー下の **ステータス** 表示で、成功/失敗件数を確認できます
- 連続10回失敗したフィードは自動的に無効化されます
- `docs/data/feeds.json` を編集して `active: false` にすると、明示的に無効化できます

### 既読/お気に入りが消えた
- これらはブラウザのlocalStorageに保存されています
- ブラウザのデータクリアで消える可能性があります
- 同じブラウザでも端末が異なれば共有されません
- 複数端末同期が必要なら、Cloudflare D1等への移行が必要(将来の拡張)

## カスタマイズ

### 取得頻度を変える
`.github/workflows/fetch-feeds.yml` の `cron` を編集:

```yaml
- cron: "0 */2 * * *"   # 2時間ごと(初期値)
- cron: "*/30 * * * *"  # 30分ごと
- cron: "0 7,12,19 * * *"  # 朝7時、昼12時、夜19時(UTC)
```

⚠️ あまり頻繁すぎると相手サーバーに負荷をかけます。30分以下は推奨しません。

### 保持期間を変える
`scripts/fetch_feeds.py` 上部:
```python
RETENTION_DAYS = 30   # 30 → 60 など
```

### 購読を追加・削除
`opml/subscriptions.opml` を編集してコミットすると、次回のActions実行時に自動で `feeds.json` が再構築されます。

簡単な編集例(末尾の `</body>` の直前に追加):
```xml
<outline type="rss"
         text="新しいフィード"
         title="新しいフィード"
         xmlUrl="https://example.com/feed.xml"
         htmlUrl="https://example.com"/>
```
