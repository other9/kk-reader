# kk-reader 運用フロー

## ZIP 配信パターン(Claude → User)

Claude が更新を提供する際のフォーマット:

```
ファイル名: kk-reader-update-{NNN}-{内容}.zip
NNN: 連番(0 埋めなし、001 から)、サブパッチは 009.1, 009.2 のように小数
内容: 短い英字スラグ(例: fulltext-fetch, mobile-typography)
```

過去の主な例(update-018 までは旧 Knowledge 参照):

- `kk-reader-update-018-cron-push-retry.zip` (workflow rebase-retry)
- `kk-reader-update-019-pages-cors.zip` (Worker CORS 拡張)
- `kk-reader-update-020-token-via-url-hash.zip` (URL fragment 投入、key 名は後で修正)
- `kk-reader-update-021-debug-page.zip` (docs/debug.html)
- `kk-reader-update-022-correct-token-key.zip` (localStorage key 修正)
- `kk-reader-update-024-cf-snapshot.zip` (scripts/cf_snapshot.py)

(update-023 は途中まで構想したが Android の問題が別経路で解決したため未配信)

ZIP 内は**リポジトリルートを起点とした相対パス**。`unzip -o` で上書き展開可能。
`UPDATE.md` は適用手順を記述、適用後は削除する(.gitignore 済)。

## 標準的な適用フロー

```bash
cd /workspaces/kk-reader

# A. 最新化
git pull --rebase

# B. ZIP 展開(絶対パスで指定するのが安全)
unzip -o /workspaces/kk-reader/kk-reader-update-{NNN}-{内容}.zip

# C. パッチ適用(update に patch_*.py または migrate_*.py が含まれる場合)
python3 scripts/patch_NNN_*.py
# または python3 scripts/migrate_NNN_*.py

# D. Worker 変更がある場合
cd worker && wrangler deploy && cd ..

# D'. Worker smoke test(Worker 変更時は必ず)
#     詳細は下の「Worker 変更時の smoke test」節

# E. push
git add -A
git commit -m "<update 内容を要約>"
git pull --rebase
git push

# F. patch script の削除(あれば)+ 後処理 commit
rm -f scripts/patch_NNN_*.py
git add -A
git commit -m "chore: remove update-NNN migration script"
git push

# G. snapshot 生成
rm -f kk-reader-*.zip UPDATE.md
python3 scripts/snapshot.py

# H. 動作確認
# シークレットウィンドウで kk-reader.pages.dev を開く
# (CSS/JS キャッシュをバイパスするため)
```

## 適用時のよくある落とし穴

### ZIP のパスは絶対指定が安全

`~/` は Codespaces で `/home/codespace` を指すが、ZIP が
`/workspaces/kk-reader/` 直下にあるケースが多い。`~/kk-reader-update-*.zip` で
unzip して "cannot find or open" になるパターンは過去複数回発生している。
**`/workspaces/kk-reader/kk-reader-update-*.zip` のフルパスで指定する**のが
確実(または事前に `find /workspaces -name "kk-reader-update-*.zip"` で位置確認)。

### TOKEN を placeholder のまま使わない

ローカルで smoke test するときに環境変数 `TOKEN` を設定するが、
`export TOKEN='実際の SYNC_SECRET 値'` のような placeholder 文字列をそのまま
コピペして使ってしまうケースが過去複数回発生している。 placeholder のままだと:

- ASCII 範囲外文字を含むため `requests` が
  `UnicodeEncodeError: 'latin-1' codec can't encode characters` で死ぬ
- もしくは Worker が `{"error":"unauthorized"}` を返す

curl を叩く前に必ず以下のチェックを通す:

```bash
python3 -c "
import os
t = os.environ.get('TOKEN', '')
print('length:', len(t), '(should be long, e.g., 30+)')
print('all_ascii:', t.isascii(), '(should be True)')
print('not_placeholder:', not any(s in t for s in ['SYNC_SECRET', '本物', 'ここ']),
      '(should be True)')
"
```

実際の SYNC_SECRET 値の入手元:

1. **ブラウザの localStorage**(一番速い): ライブサイトを開いて DevTools →
   Application → Local Storage → キー `kkreader.syncToken` の value
2. password manager のメモ
3. 失念した場合は `wrangler secret put SYNC_SECRET` で新しい長乱数を投入 →
   同じ値を GitHub Actions の `WORKER_TOKEN` secret にも反映

過去の Knowledge には誤って `kk-sync-token` というキー名が記載されていたが、
実装と不一致。正しいキー名は **`kkreader.syncToken`**。

### feeds.json の構造を実物確認してから migration を書く

`docs/data/feeds.json` の top-level は **`{"feeds": [...]}` の dict 構造** で、
直接 list ではない。

正しいパターン:

```python
with FEEDS_PATH.open("r", encoding="utf-8") as f:
    data = json.load(f)
feeds = data["feeds"]
for feed in feeds:
    ...
# 書き戻すときも data 全体を書く
with FEEDS_PATH.open("w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
```

### commit message に `[skip ci]` の文字列を含めない(Phase 4 で発覚)

Cloudflare Pages は commit message に **substring match で `[skip ci]` を検出**
して build を skip する。これは意図的(自己 referential な commit でも skip
される)。Phase 4 で `chore: remove [skip ci] to enable Cloudflare Pages
rebuild on cron` というメッセージで commit したら、その commit 自身が skip
された。

回避策: `[skip ci]` の文字列を message に含めない。説明的に書くなら
`chore: enable Cloudflare Pages auto-rebuild on cron commits` のような言い換え。

実害は限定的(workflow ファイル変更だけの場合 docs/ が変わっていないので
build しても結果が同じ)。ただし docs/ を変更しつつ skip 句を含む message を
付けると、その変更が Pages に届かない事故が起こりうるので注意。

## スクレイピング系修正時は実 HTML を見てから(重要)

Worker `/article` または adapter の listing パーサに修正を入れる際、
**まず Worker `/fetch` で実 HTML を取り寄せて DOM 構造を確認する**こと。
DOM を推測ベースで heuristic 化すると、複数ターン修正を繰り返す羽目になる。

```bash
# SYNC_SECRET 値を環境変数にセット(履歴に残らないよう先頭スペース付き)
 export TOKEN='実際の SYNC_SECRET 値'

# listing ページの HTML を取り寄せて、該当する記事 anchor の DOM を出力
LISTING_URL='https://www.rakumachi.jp/news/practical'
ARTICLE_PATTERN='/news/practical/\d+$'

curl -s -H "Authorization: Bearer $TOKEN" \
  "https://kk-sync.other9.workers.dev/fetch?url=$LISTING_URL" \
  | python3 -c "
import sys, json, re
from bs4 import BeautifulSoup
d = json.load(sys.stdin)
soup = BeautifulSoup(d['html'], 'html.parser')
for a in soup.find_all('a', href=re.compile(r'$ARTICLE_PATTERN')):
    print(repr(a)[:600])
    print()
" | head -50
```

## Worker 変更時の smoke test(必須)

Worker のコード変更後は必ず以下を実行:

```bash
# SYNC_SECRET 値を環境変数にセット
 export TOKEN='実際の SYNC_SECRET 値'

# 上の「TOKEN を placeholder のまま使わない」節のチェックを通すこと

# 1. /ping で疎通
curl -s -H "Authorization: Bearer $TOKEN" https://kk-sync.other9.workers.dev/ping
# 期待: {"ok":true,"ts":...}

# 2. /article で本文抽出を確認
ARTICLE_URL='https://www.kenbiya.com/ar/ns/region/osaka/10066.html'
curl -s -H "Authorization: Bearer $TOKEN" "https://kk-sync.other9.workers.dev/article?url=$ARTICLE_URL" \
  | python3 -c "
import sys, json, re
d = json.load(sys.stdin)
print('error:       ', d.get('error'))
print('cache_hit:   ', d.get('cache_hit'))
print('content_len: ', len(d.get('content_html','')))
bad = re.findall(r'&amp;(?:nbsp|gt|lt|amp|quot|#\d+|#x[0-9a-fA-F]+);', d.get('content_html',''))
print(f'double-encoded entities: {len(bad)}')
imgs = re.findall(r'<img[^>]*>', d.get('content_html',''))
print(f'images:      {len(imgs)}')
if imgs:
    print(f'first img:    {imgs[0][:200]}')
"

# 3. CORS allowlist の確認(update-019 で追加)
curl -s -D - -o /dev/null -X OPTIONS "https://kk-sync.other9.workers.dev/ping" \
  -H "Origin: https://kk-reader.pages.dev" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: authorization" \
  | grep -i "access-control-allow-origin"
# 期待: access-control-allow-origin: https://kk-reader.pages.dev

# 4. /fetch で楽待プロキシを確認
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://kk-sync.other9.workers.dev/fetch?url=https://www.rakumachi.jp/news/column" \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print('status:',d.get('status'));print('html_len:',len(d.get('html','')))"
```

これを scripts/ 配下にシェルスクリプトとしてまとめるのが良い候補
(`scripts/smoke_test_worker.sh`、未実装)。

## 新規 adapter 追加時のローカルテスト

新しいスクレイパー adapter を追加した時、本番に push する前にローカルで
fetch を試せる:

```bash
cd /workspaces/kk-reader
 export TOKEN='実際の SYNC_SECRET 値'
WORKER_BASE_URL='https://kk-sync.other9.workers.dev' WORKER_TOKEN="$TOKEN" \
python3 -c "
from scripts.adapters import ADAPTERS
ad = ADAPTERS['scrape_cfajapan']
feed = {
    'id': 'test',
    'title': '<feed title>',
    'url': '<listing url>',
    'category': '<category>',
    'via_worker': True,
}
articles, meta = ad.fetch(feed)
print(f'items: {len(articles)}')
print(f'last_error: {meta.get(\"last_error\")}')
for a in articles[:5]:
    print(f'  {a.published or \"(no date)\"} | {a.title[:60]}')
"
```

## 新端末を kk-reader.pages.dev に追加(update-022 以降)

3 つの経路:

### 経路 A: URL fragment(推奨、PC + メールで完結)

1. PC ブラウザで kk-reader.pages.dev を開いて Console:
   ```javascript
   copy(localStorage.getItem("kkreader.syncToken"))
   ```
   実 token がクリップボードに入る
2. URL を組み立て:
   ```
   https://kk-reader.pages.dev/#token=<TOKEN>
   ```
3. 自分宛メール、または iCloud Keychain Notes 等で新端末に送る
4. 新端末で URL を開く → Cloudflare Access OTP 通過 → bootstrap script が
   fragment を読み取り localStorage に投入、URL バーから fragment を消す
5. リロード → 既読・お気に入りが同期される
6. **メールの履歴とブラウザ履歴から該当 URL を削除**(fragment はサーバに
   送信されないが、端末履歴には短時間残る)

### 経路 B: /debug.html フォームから貼り付け

bookmarklet や `javascript:` URL が動かない端末(Android Chrome の最近の版
等)で有用。

1. 新端末で `https://kk-reader.pages.dev/debug.html` を開く
2. Cloudflare Access OTP 通過
3. **Token セクション**の入力欄に PC から取得した token を貼り付け
4. **Set token** ボタン
5. **Test /state** で 200 + read keys ≥ 0 を確認
6. 「← kk-reader へ」で `/` に戻り、同期確認

### 経路 C: DevTools 直接書き込み(緊急時)

```javascript
localStorage.setItem("kkreader.syncToken", "<TOKEN>"); location.reload();
```

## debug.html での同期障害切り分け

Android などで同期が動かない場合の標準診断手順:

1. `https://kk-reader.pages.dev/debug.html` を開く
2. **Token セクション**:
   - `UNSET` → localStorage に token が無い → フォームから設定
   - `SET length=64 ascii=true ...` → 値は正しい
3. **Test /ping**:
   - `status=200 {"ok":true,...}` → Worker 通信 OK
   - `status=401` → token 値が誤り、または Worker SYNC_SECRET と不一致
4. **Test /state**:
   - `status=200 read keys=N fav keys=M` → KV から正常取得
   - これが OK ならアプリ側の UI 反映だけの問題 → サイトデータクリア + リロード
5. **Environment** で origin / userAgent を確認

切り分け結果と次の手:

| 状態 | 原因 | 対処 |
|---|---|---|
| Token SET、/ping OK、/state OK、UI に未反映 | app.js のキャッシュ問題 | Chrome 設定 → サイト設定 → kk-reader.pages.dev → ストレージとキャッシュをクリア |
| Token SET、/state OK だが render 後しばらく反映されない(Android) | visibility-trigger 待ち(未解決の挙動) | タブを一度切り替えて戻す |
| Token UNSET | bootstrap が動かなかった or 経路 A の URL に問題 | 経路 B(debug.html フォーム)で直接投入 |
| /ping 401 | token 値違い | PC で値を取り直して貼り直す |

## CF snapshot の取得(update-024 以降)

```bash
cd /workspaces/kk-reader
python3 scripts/cf_snapshot.py
```

生成: `kk-reader-cf-snapshot-YYYYMMDD-HHMMSS.zip`

内容:
- `CF_STATE.json` — 集約サマリ(メアドは redact 済み)
- `README.txt` — 各 section の取得成否 + 統計
- `raw/*.json` — Cloudflare API レスポンス verbatim

各 section の status が `ok` であることを README で確認。`error` の場合は
API token の scope 不足の可能性が高い。Cloudflare ダッシュボード → My Profile
→ API Tokens → 該当 token を Edit して scope を追加:

| section | 必要な scope |
|---|---|
| worker_deployments | Account: Workers Scripts: Edit / Read |
| worker_settings | 同上 |
| worker_secrets | 同上 |
| kv_keys | Account: Workers KV Storage: Edit / Read |
| pages_project | Account: Cloudflare Pages: Edit / Read |
| pages_deployments | 同上 |
| access_apps | Account: Access: Apps and Policies: Read |
| access_policies | 同上 |

CF snapshot は適宜取って次チャットの冒頭に GitHub snapshot と並べて添付する
運用(両側の整合した checkpoint として)。

## snapshot.py の挙動

```bash
python3 scripts/snapshot.py
```

実行すると `kk-reader-snapshot-YYYYMMDD-HHMMSS.zip` が生成される。
中身:
- `STATE.json`: git head commit, feeds 状態統計, 直近記事サンプル
- `source/`: INCLUDE_PATHS で指定されたファイル群
- `README.txt`: snapshot 説明

INCLUDE_PATHS:
- `docs/`(全体だが `articles.json` の `content_html` は除外)
- `worker/`
- `scripts/`
- `opml/`
- `.github/workflows/fetch-feeds.yml`
- `requirements.txt`
- `.gitignore`

EXCLUDE_TOKENS で `.wrangler`, `__pycache__` 等を除外。

snapshot は Claude のチャット冒頭にアップロードする運用。Knowledge には置かない
(古くなる)。

## Actions Bot との rebase 競合(update-018 で workflow 側に自動化済み)

update-018 以前の手動 rebase dance はもう不要。workflow 側で:

1. 通常 push 試行
2. reject されたら、データファイルを退避 → `git fetch origin main` →
   `git reset --hard origin/main` → データファイル復元 → 再 commit
3. 再 push 試行(最大 3 回)

ローカル作業中の `git pull --rebase` で稀に競合する可能性はゼロにはならない
が、update-012 で cron を `HH:07` にずらして混雑帯回避済みで発生頻度は低い。

ローカルで作業中に bot push を pull した場合、git push が rejected されたら
普通に `git pull --rebase && git push` で復旧する。データファイルの上書き
合戦にはならない(workflow 側 retry が user push の commit を保持する設計
なため)。

## Cloudflare Worker のデプロイ

### 通常更新

```bash
cd worker
wrangler deploy
```

### secret 設定(初回のみ)

```bash
cd worker
echo "<長い乱数>" | wrangler secret put SYNC_SECRET
```

### KV namespace 確認

```bash
wrangler kv namespace list
# STATE namespace が表示されるはず
```

### Codespaces で wrangler login が OAuth 失敗する場合

API Token 方式に切り替える:
1. Cloudflare ダッシュボードで API Token 発行(Workers / KV 権限)
2. GitHub Codespaces の Secrets に `CLOUDFLARE_API_TOKEN` として保存
3. wrangler が環境変数経由で認証する

scope は `10_ARCHITECTURE.md` の「CLOUDFLARE_API_TOKEN に必要な scope」表参照。

## Cloudflare Pages の運用

### デプロイ

GitHub repo `other9/kk-reader` の `main` branch から自動デプロイ。設定は
Phase 1 で確定済:

- Production branch: `main`
- Build command: (空欄)
- Build output directory: `docs`
- Root directory: (空欄、リポジトリ root)

`main` への push のたびに Cloudflare Pages が自動 build。月次 build 数は
500/月 Free 枠で、cron commit 12回/日 × 30日 = 360 builds + 手動 ~10 builds
= ~370 builds で枠内。

### Pages の手動 rebuild

```text
Cloudflare ダッシュボード → Workers & Pages → kk-reader → Deployments
→ 直近の successful build の三点メニュー → "Retry deployment"
```

### Pages の build ログ確認

```text
ダッシュボード → kk-reader → Deployments → 該当 build → "View build log"
```

### Pages の builds カウント監視

月次の build 数が 450 を超えそうな場合は警戒が必要(500/月 Free 枠超過寸前):

```text
ダッシュボード → kk-reader → Deployments → "All deployments" で月内件数確認
```

または `python3 scripts/cf_snapshot.py` で取った CF snapshot の
`pages_deployments.count`(直近 25 件内)で頻度を把握できる。

超過しそうな場合の対処:
- 一時的に `.github/workflows/fetch-feeds.yml` の commit message に
  `[skip ci]` を戻す(cron 由来の build を抑制)
- ただし新サイトに最新 articles.json が反映されなくなるので、定期的に手動
  retry deployment が必要になる

## Cloudflare Access の運用

### 認証期間切れの対処

session duration を 1 month(730h)に設定済。期限切れ時:

1. ブラウザでサイトを開く → Cloudflare Access のメール OTP 画面
2. メアド入力 → 6 桁コードがメール到着
3. コード入力 → 通過、その後 1 ヶ月有効

### 認証 Application の構成

2 つの Application で kk-reader.pages.dev 配下を保護:

| Application 名 | Subdomain | Domain | 用途 |
|---|---|---|---|
| `kk-reader.pages.dev`(または `kk-reader-production`) | (空) | `kk-reader.pages.dev` | production 配信 |
| `*.kk-reader.pages.dev`(または `kk-reader-preview`) | `*` | `kk-reader.pages.dev` | preview deployments |

両方とも policy: Allow / Include Emails / 自分のメアドのみ。

### Identity provider

メール OTP のみ使用(追加 IdP 設定なし)。OTP メールが届かない場合の対処:

- spam フォルダ確認
- Cloudflare Zero Trust → Logs → Access で認証試行が記録されているか確認
- メアドの typo がないか policy 設定で確認

### Access の追加デバイス対応

新しい端末を使う場合は初回認証が必要(session cookie がないため)。1 回 OTP
通過すれば以降 1 ヶ月有効。

## 3 つの secret store の区別

GitHub の secret 関連は 3 つの異なるストアがあって、用途別に使い分け。
Codespaces secret は Actions runner からは見えない、逆も同様。

| Secret 名 | 保存場所(GitHub UI のパス) | 用途 | 設定方法 |
|---|---|---|---|
| `CLOUDFLARE_API_TOKEN` | Settings → Codespaces → Secrets | Codespaces 内で `wrangler deploy` 時の認証、`cf_snapshot.py` の認証 | Web UI または `gh secret set --user` |
| `WORKER_TOKEN` | Settings → Secrets and variables → **Actions** | GitHub Actions runner が Worker `/fetch` を Bearer で叩く | Web UI が確実 |
| `SYNC_SECRET` | (Cloudflare 側、wrangler 経由) | Worker のすべてのエンドポイントの Bearer 認証 | `wrangler secret put SYNC_SECRET` |

`WORKER_TOKEN` は SYNC_SECRET と同値で運用。

## Codespaces デフォルト `GITHUB_TOKEN` の権限不足

Codespaces 環境の `gh` は `GITHUB_TOKEN` を継承しているが、これには以下の権限が
ない:

- `secrets:write` → `gh secret set` / `gh secret list` が 403
- `workflows:write` → `gh workflow run` が 403

回避策:

| やりたいこと | 経路 |
|---|---|
| Actions secret 設定 | Web UI: `Settings → Secrets and variables → Actions → New repository secret` |
| 手動で workflow 実行 | Web UI: `Actions → Fetch RSS feeds → Run workflow` |
| 失敗 workflow の再実行 | Web UI: `Actions → 失敗した run → Re-run failed jobs` |
| `gh` でやりたい場合 | `gh auth refresh -h github.com -s repo,admin:repo_hook` で scope 拡張 |

## ブラウザキャッシュ問題

特に Android Chrome は CSS/JS を `cache-control: max-age=600` で数時間保持する。
更新後の動作確認は:

1. **シークレットウィンドウ**で開く
2. または URL に `?v=<commit_hash>` クエリを付ける
3. または「サイト固有データを削除」(設定 → サイト設定 → 該当ドメイン)

debug.html を活用して切り分けるのが Phase 0〜4 で確立した方法
(`/debug.html` で `Test /state` を叩いて API が 200 を返すのに UI 未反映なら、
ほぼ確定的にキャッシュ問題)。

## .gitignore 維持(重要)

機密情報の commit を防ぐため、以下は必ず .gitignore に入れる:

```
# wrangler のローカル認証キャッシュ(メールアドレス等が含まれる)
.wrangler/
worker/.wrangler/

# 開発中の ZIP / 説明
kk-reader-update-*.zip
kk-reader-snapshot-*.zip
kk-reader-cf-snapshot-*.zip
kk-sync-diagnostics-*.zip
UPDATE.md

# Python
__pycache__/
*.pyc

# Node
node_modules/
```

過去の事故: `worker/.wrangler/cache/wrangler-account.json`(メールアドレス
含む)が public リポジトリに commit されてしまい、`git filter-repo` で全 23
commit から履歴削除する事態になった(2026-05-06)。

snapshot.py の EXCLUDE_TOKENS に `.wrangler` を追加済み、再発防止済み。

## フィードの取得失敗対応

```bash
python3 scripts/inspect_failures.py
```

直近の失敗フィードと最後のエラーが一覧表示される。`last_items_count == 0` の
**サイレント失敗**(成功扱いだが items が抽出されていない)も検出する。

典型対処:

| エラー | 対処 |
|---|---|
| HTTP 404 | URL が変わった/サイト消滅。OPML から削除または `active: false` |
| HTTP 403 | bot 検出 / IP allowlist。feeds.json で `via_worker: true` を設定して Worker proxy 経由で改善する場合あり |
| connection / timeout | 一時的。次回サイクルで自動回復することが多い |
| ssl: ... | 証明書問題。`verify_ssl: false` を feeds.json で設定 |
| parse error | RSS 形式不正。多くは `parse_with_recovery=True` で救える |
| サイレント失敗(items 0) | スクレイパーのセレクタが現実の DOM 構造と合っていない。adapter の修正が必要 |

## 既存フィード数の目安(2026-05-18 時点)

- 総数: 116 フィード
- アクティブ: 81
- 取得成功: 81
- 取得失敗: 35
- 記事総数: 625

詳細は `50_ROADMAP.md` の「現状の分布」参照。

## GitHub Actions cron の信頼性に関するメモ

GitHub Actions の `schedule:` イベントは公式に best-effort と明記されており、
特に `HH:00` は全世界の cron が殺到するため、遅延・スキップが頻発する。
kk-reader は update-012 で `7 */2 * * *` に変更して混雑帯から外し、
update-018 で push reject 時の自動 rebase-retry を組み込んだ。

緩和策のステップ:
- (a) 分をずらす(`7 */2 * * *`) ← **適用済み (update-012)**
- (b) push reject の自動 retry ← **適用済み (update-018)**
- (c) 倍頻度 + 冪等ガード(`7,47 */2 * * *`) ← 必要なら追加可能
- (d) Cloudflare Cron Trigger 経由で `repository_dispatch`(数秒精度) ← 過剰
- (e) 受け入れる ← (a)(b) 後はほぼこれで十分

bot commit 間隔は `git log --author=github-actions[bot] --pretty="%aI %h"` で
モニタ可能。

## 移行後の Actions 無料枠(Phase 6 で repo private 化後)

private 化すると、Actions の billing 計算が変わる。

- 旧(public): 時間無制限無料
- 新(private、Free プラン): **2000 min/月** 無料

実測使用量(update-018 まで):
- cron: 12 runs/日 × 30 日 = 360 runs/月
- 各 run: 約 3 分
- 合計: **約 1100 min/月**

Free 枠 2000 min/月の **55%程度** で収まる。Pro 加入($4/月)は不要。
