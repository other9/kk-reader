# kk-reader 既知の問題と対処

## 進行中の課題

### Phase 5 並行運用(2026-05-18 〜)

**目的**: Cloudflare Pages 移行の Phase 5 として、1〜2 週間の並行運用観察。

Phase 0〜4 が完了し、`kk-reader.pages.dev` と `other9.github.io/kk-reader/` の
両方が稼働中。Phase 5 期間中は、新サイトで通常運用しつつ:

- 端末固有の崩れ(タイポグラフィ、tap area、横スクロール等)
- 認証 OTP の摩擦頻度(1 ヶ月セッションが想定通り効くか)
- Pages の月間 build 数推移(500/月 Free 枠の確認)
- 同期挙動の安定性(特に Android 初回ロード時の visibility-trigger 依存)

を観察する。能動作業はほぼ無し、不具合があればその都度対応。

Phase 5 完了の判定: 1〜2 週間運用して大きな問題が出ないこと。

Phase 6 で旧サイト撤去 + repo private 化、月額 $0 維持で「層 1 + 層 2 完全
private 化」を達成して完了。詳細は `60_MIGRATION_RUNBOOK.md` 参照。

## 過去の解決済み課題

### Cloudflare Pages 移行 Phase 0〜4 完了(2026-05-17 〜 2026-05-18)

**目的**: 個人プロジェクトの完全 private 化(層 1 + 層 2)。

GitHub Pages は個人アカウントの private repo から publish しても live サイトが
public 配信になるため、live サイトの private 化は GitHub だけでは不可能。
Cloudflare Pages + Access により、追加コスト $0 で完全 private 化が達成できる。

実施した変更:

| Update | 内容 |
|---|---|
| update-019 | Worker の `ALLOWED_ORIGINS` に `https://kk-reader.pages.dev` を追加、preview deployments 用に regex `*.kk-reader.pages.dev` も対応 |
| update-020 → 022 | `docs/index.html` に URL fragment(`#token=<TOKEN>`)経由の token 投入 bootstrap を追加。最初 update-020 は localStorage key 名を `kk-sync-token` で書いていたが実装側は `kkreader.syncToken` を使うため不整合、update-022 で修正 + legacy key からの自動 migration を実装 |
| update-021 → 022 | `docs/debug.html` 追加。token と Worker 通信を可視化する独立ページ。bookmarklet や `javascript:` が塞がれた端末でも GUI で診断 + token 投入できる |
| update-024 | `scripts/cf_snapshot.py` 追加。CF API 経由で Worker / Pages / Access / KV の状態を ZIP 化(GitHub snapshot.py との対称) |
| Phase 4 commit | `.github/workflows/fetch-feeds.yml` から `[skip ci]` を 2 箇所(initial + retry 経路)削除 |

実機での確認:
- 2026-05-18 22:21 JST に Phase 4 後初の bot commit `f407b3d` が出て、Cloudflare
  Pages の auto-rebuild が走った(skip 無し)
- CF snapshot で `pages_deployments` を確認、Phase 4 commit `a8a5421` 自身は
  skip されたが、それ以降の bot commit は build されている

### Cloudflare Pages の `[skip ci]` substring match(2026-05-18 発覚)

**問題**: Phase 4 で `chore: remove [skip ci] to enable Cloudflare Pages
rebuild on cron` というメッセージで commit したら、**その commit 自身が Pages
で skip された**。

**原因**: Cloudflare Pages は commit message に `[skip ci]`(または `[ci skip]`
等のバリエーション)が**部分文字列として含まれていれば**、文脈を問わず build
を skip する。「skip を解除する」という意図の message でも、文字列としては
`[skip ci]` を含むため発火した。

**実害**: なし。Phase 4 commit は `.github/workflows/` だけの変更で `docs/` を
触っていないため、build しても出力は変わらず、skip されても何も失われていない。

**今後の対処**: commit message に `[skip ci]` の文字列リテラルを含めない。
言い換えで対応する。例:

- ✗ `chore: remove [skip ci] to enable rebuilds`
- ✓ `chore: enable Cloudflare Pages auto-rebuild on cron commits`

docs/ を変更しつつ skip 句を含む message を付けると、その変更が Pages に
届かない事故が起こりうる。

### localStorage key 名の不整合(2026-05-18 発覚 → update-022 で修正)

**問題**: 過去の Knowledge ドキュメント(20_OPERATIONS.md の旧版等)に
`kk-sync-token` という localStorage key 名が記載されていたが、これは
`docs/sync.js` の `SYNC_STORAGE.token` 定数の値 **`kkreader.syncToken`** と
不一致。update-020 と update-021 はこの誤った key 名で書いていたため、URL
fragment 経由の投入や debug.html での操作が sync.js に届かなかった。

**症状**: Android で debug.html の Test /state は status=200 で read keys=603
を返すのに、app.js は同期せず UI で全部未読のまま。

**原因**: PC は過去の経緯で `kk-sync-token` と `kkreader.syncToken` の両方に
同じ値が入っていたため、sync.js が `kkreader.syncToken` から読んで動作し、
不整合が顕在化しなかった。Android では update-020 経路で `kk-sync-token` に
だけ書き込まれ、sync.js が read できず enabled === false になっていた。

**対処(update-022)**:
- `docs/index.html` の bootstrap script を書き換え:
  - URL fragment 名: `#kk-sync-token=` → **`#token=`** に短縮
  - localStorage 書き込み先: `kk-sync-token` → **`kkreader.syncToken`** に修正
  - legacy `kk-sync-token` の値があれば `kkreader.syncToken` に自動 migration
    して legacy 側を削除
- `docs/debug.html` の KEY 定数を `kkreader.syncToken` に修正

**教訓**: 既存実装に依存する patch を書くときは、Knowledge の記述ではなく
**実コード(sync.js 等)を直接参照**する。Knowledge は人間が書いたメモなので
誤記がありえる。

### Android 初回ロードでの sync 未反映(2026-05-18 観察、未根本対応)

**症状**: Android Chrome で kk-reader.pages.dev を初回ロードしても、PC で
書き込んだ既読・お気に入り状態が UI に反映されない。tab を一度切替えて
戻すと反映される。

**原因の暫定推測**: `docs/app.js` の `init()` 末尾で `performSync(true)` を
呼んでおり、コード上は初回 pull するはずだが、Android の Chrome バージョン
固有のタイミング問題で初回 pull → render の連鎖がどこかで止まっている可能性。
debug.html での直接 /state 叩きは正常(API は完全に正常)なので、app.js
内部のロジックの問題。

**実用上の対処**: タブを一度切替えて戻す(visibilitychange イベント発火で
performSync(false) が走る)。これで既読状態が UI に降りてくる。一度同期が
走ると localStorage の `kkreader.read` / `kkreader.favs` が populated される
ので、次回以降のロードは local state から render され問題なく見える。

**根本対処の候補(未実施)**:
- `init()` 末尾の `performSync(true)` 後に `renderArticleList()` を強制呼び出し
- または `loadData()` 完了後に sync 完了を await して順序を整える

Phase 5 期間で実害が顕在化したら別 update で対応。優先度は低め(初回だけの
摩擦で、運用上は気にならない範囲)。

### KV の stale 状態(2026-05-18 観察、housekeeping)

**現状**:

```
state:                1    ← 同期データ、正常
article:v3:          44    ← 現役 cache
article:v2: (stale) 111    ← update-015 以前の二重エンコード入り、TTL 30日待ち
<other>              13    ← article:<hash> (version prefix 無し、update-011 以前)
```

`article:v2:*` 111 件は update-015 で v3 に bump したときに stale 化したが、
TTL 30 日で自然失効する設定なので放置で OK(おそらく 2026-06 中旬には消える)。

`article:<hash>` の 13 件は update-011 以前の最初期 cache(version prefix
すら無い時代)で、おそらく TTL なしで KV に置かれた。自動失効せず KV に残り
続ける。実害ゼロ(Worker は `article:v3:` で lookup するので参照しない)、
気にしないなら無視で OK。気になるなら手動削除:

```bash
# 該当キー一覧確認(CF snapshot の raw/kv_keys.json で見れる)
wrangler kv key list --namespace-id bcc0dd025aa34897b44a83f13ce88973 \
  | python3 -c "import sys,json; [print(k['name']) for k in json.load(sys.stdin) if not (k['name'].startswith('state:') or k['name'].startswith('article:v'))]"

# 個別削除
wrangler kv key delete --namespace-id bcc0dd025aa34897b44a83f13ce88973 'article:<hash>'
```

Phase 6 直前のクリーンアップ候補。

### Actions cron push レース対策(2026-05-16 update-018)

**問題**: GitHub Actions の cron(`fetch-feeds.yml`)が走っている最中に user が
push すると、bot の `git push` が non-fast-forward で reject されて workflow
が exit 1 で失敗する。

**対処**: `.github/workflows/fetch-feeds.yml` の `Commit updated data` ステップ
に retry-with-rebase ロジックを追加(最大 3 回試行)。push reject 時の挙動:

1. データファイル(`feeds.json` / `articles.json`)を一時退避
2. `git fetch origin main` → `git reset --hard origin/main` で remote 最新を
   取り込む(自分の commit は捨てる)
3. 退避したデータファイルで上書き
4. 再 commit + push

データファイルは bot が「現時点の真」を生成するため上書き優先、user の code
変更は reset で取り込まれるため保持される。

**復旧手段**: 既に失敗した workflow は GitHub の Actions UI から **Re-run
failed jobs** で復旧。

### RETENTION_DAYS 30 → 60 への拡大(2026-05-16 update-017)

**問題**: update-016 で CFA Society Japan ブログを購読追加した後、articles.json
内に CFA 記事が **0 件** であることが判明。原因は ISO 文字列の lexicographic
比較で JST→UTC 変換の境界差により、月 2〜3 本ペースの slow-publishing 系が
完全に prune されること。

**対処**: `scripts/fetch_feeds.py:28` の `RETENTION_DAYS` を 30 → 60 に変更。

効果:
- articles.json は 493 → 564 件(+71、+14%)
- CFA は最近半年分の posts(~12 件)が visible に
- 副次的に本石町日記、CFA学習方法 Tips 等の他の低頻度系も恩恵
- 内部 ISO 文字列比較のタイムゾーン境界 bug は未修正(将来の TZ-aware 比較化
  が課題、ただし 60 日 retention で実害は消えた)

### CFA Society Japan ブログ追加(2026-05-16 update-016 + 016.1)

CFA Society Japan の公式ブログ
(`https://www.cfasociety.org/japan/society-news-resources/blog`)を購読先に
追加。Higher Logic + Cloudflare CDN 構成、RSS なし。新規 adapter
`scripts/adapters/cfajapan_scraper.py` で listing をスクレイプ、`via_worker:
true` で Worker proxy 経由。

update-016.1 hotfix: 同梱の migration script が feeds.json の構造
(top-level が `{"feeds": [...]}` の dict)を誤推定して `AttributeError` で
死亡。修正済。**教訓**: 既存のデータ形式は migration script を書く前に必ず
実物確認する。

### HTML エンティティの二重エンコード(2026-05-16 update-015)

**問題**: 楽待・健美家の記事詳細を表示すると、本文中に `&nbsp;` や `&gt;`
が文字列としてそのまま表示されることがあった。

**原因**: Cloudflare Workers の HTMLRewriter は `text(t)` ハンドラに渡される
text chunk を**デコードせず生のまま**渡してくる仕様。`worker.js` の
`escapeText` が単純な `& → &amp;` 置換を行っていたため、`&nbsp;` →
`&amp;nbsp;` に二重エンコードされていた。

**対処**: `escapeText` を「既存の有効なエンティティ参照は保持し、エンティティを
構成しない bare な `&` のみ `&amp;` に置換」する方式に変更。KV cache key を
`article:v2:` → `article:v3:` に bump して古いキャッシュを実質無効化。

### `_anchor_title_text` の段階的修正(2026-05-09 update-012〜014)

楽待実践大家・編集部の listing で title 先頭にランキング数字が貼り付く問題。
3 ターンかけて解消(update-012 → 013 → 014)。

**教訓**: スクレイピング系修正は **実 HTML 確認 → 修正案** の順を運用ルール化
(`20_OPERATIONS.md` の「スクレイピング系修正時は実 HTML を見てから」節)。

### Cron 実行の遅延・スキップ(2026-05-09 update-012 で緩和)

GitHub Actions の `schedule:` イベントは公式に best-effort と明記、特に
`HH:00` は混雑帯のため、`cron: "7 */2 * * *"` に変更して回避。update-018 で
push reject 時の自動 rebase-retry を加え、race condition への耐性を上げた。
それでも skip / 遅延ゼロにはならない(best-effort の本質)。

### お気に入り記事の表示制限(設計仕様、update-017 で 60 日に変更)

`fetch_feeds.py:28` の `RETENTION_DAYS = 60` により、`published` または
`fetched` が 60 日より古い記事は articles.json から prune される。
お気に入り状態自体は localStorage(`kkreader.favs`)+ Cloudflare KV(`/state`)
に永続保存されるが、UI 表示は articles.json に依存するため、お気に入り記事も
60 日経つと表示できなくなる("二層永続"構造)。

| レイヤ | 永続性 | 仕組み |
|---|---|---|
| お気に入り状態 `{state:1, ts:...}` | 永続 | localStorage + KV |
| お気に入り記事の UI 表示 | 60 日まで | articles.json prune |

将来の改善案: `fetch_feeds.py` の prune ロジックで「お気に入り(KV から取得)
に入っている記事は除外」する特例を入れる。優先度は低め。

### 楽待 HTTP 403(2026-05-06 検出 → 2026-05-09 解決)

**問題**: 楽待 3 フィードが GitHub Actions 環境から HTTP 403。WAF / IP
allowlist による拒否。

**対処(update-009)**: Cloudflare Worker proxy 経由(`GET /fetch?url=X`)で
取得する経路を実装。同パターンは update-016 の CFA Society Japan でも再利用。

### Worker `/article` エンドポイントの初期バグ群(update-010, 011)

- void-element の onEndTag で throw(update-010)
- 画像の相対 URL 解決(update-011、`<img src="/news_img/...">` を絶対化)

**教訓**: Worker 側のコード変更は必ず curl smoke test を回す
(`20_OPERATIONS.md` の "Worker 変更時の smoke test" 節)。

### 健美家アダプターのサイレント失敗(2026-05-09 解決)

update-007 で実装した健美家スクレイパーが thumbnail link + title link の
dedup ロジックで title link を捨てていた。`scrape_base.extract_listing_links()`
共通ヘルパーで「URL → 最も長いリンクテキスト」集約に変更(update-009)。
`inspect_failures.py` にサイレント失敗検出(`last_items_count == 0`)も追加。

### opml_to_feeds.py が via_worker を wipe する問題(2026-05-09 解決)

update-009 適用後、`opml_to_feeds.py` rebuild で `via_worker: true` が消えて
いた。OPML が source of truth として持つ field 以外を保持する denylist 方式
に変更(update-009.1)。

### .wrangler キャッシュのリポジトリ混入(2026-05-06 解決)

`worker/.wrangler/cache/wrangler-account.json` に user メールアドレスが
保存され、それが public repo の 23 commit に混入。`git filter-repo` で履歴
書き換え。`.gitignore` に `worker/.wrangler/` 追加、snapshot.py の
EXCLUDE_TOKENS に `.wrangler` 追加で再発防止済。

## 既知の制約・許容している問題

### TOKEN placeholder のまま smoke test を回してしまう

過去複数回発生。`export TOKEN='実際の SYNC_SECRET 値'` のような placeholder
込みの例をそのままコピペ → `UnicodeEncodeError` または `unauthorized`。

対策(20_OPERATIONS.md に記載):

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

### ISO 文字列の lexicographic 比較によるタイムゾーン境界

`fetch_feeds.py` の prune は `published` と `cutoff` を ISO 文字列のまま
lexicographic 比較しているため、タイムゾーン offset が異なる文字列の比較で
誤判定する余地がある。update-017 で RETENTION_DAYS=60 に拡大したことで実害は
ほぼ消えたが、根本対処としては TZ-aware datetime に変換してから比較するのが
正しい。優先度低、Phase 3 候補。

### 楽待ランキング widget の `published: null`

楽待実践大家・編集部の listing で、ランキング(1〜5 位)widget 由来の記事は
listing ページに日付が露出されていないため、`published: null` のまま
articles.json に入る。ソート順は `fetched`(初出時刻)で代替されるので運用上
問題ない。

### `_anchor_title_text` の case 2 限界

`<a>5築より立地。</a>` のように rank と title が同一 NavigableString 内で
連結されている DOM は構造的に分離不可能(update-014 既知の限界)。

### Android Chrome の CSS キャッシュ

`cache-control: max-age=600` で CSS/JS が数時間キャッシュされる。
明示的にキャッシュバスティングする手段は実装していない。更新後の動作確認は
**シークレットウィンドウ**または `/debug.html` で行う運用。

### URBANSPRAWL の重複(楽待連載追加後)

URBANSPRAWL は既に直接購読している。楽待連載コラムを追加すると、
同氏の記事が両フィードから流入する可能性。URL ハッシュで dedup するが、
URL が少しでも違うと両方表示される(許容)。

### Actions の遅延・スキップ(緩和済みだが完全には消えない)

update-012 で cron を `HH:07` に移して混雑帯回避、update-018 で push reject
時の自動 rebase-retry を組み込んだが、best-effort 性自体は変わらない。
リアルタイム性は妥協前提。

### Worker /fetch のレート制限なし

`/fetch` エンドポイントは認証 + scheme 検証はあるが、token が漏れると open
proxy として使われる可能性がある。SYNC_SECRET / WORKER_TOKEN の管理は厳重に。

### srcset 未対応

Worker `/article` の本文抽出は `<img src>` のみ扱い、`srcset` 属性は無視する。
`src` が空 + srcset のみのケース(極めて稀)では画像が出ない。

### ホットリンク防止サイトの画像

サイト側が Referer または Cookie 必須のホットリンク防止を入れている場合、
画像 URL を絶対化しても 403/404 になる可能性。健美家・楽待・CFA では問題
なさそうだが、別サイトで顕在化した場合は Worker 側で `/img?url=X` プロキシを
追加することで対応可能(未実装)。

## 機密管理

絶対にリポジトリに置かない:
- SYNC_SECRET(wrangler secret put 経由)
- WORKER_TOKEN(GitHub Actions Repository Secret 経由、SYNC_SECRET と同値)
- メールアドレス
- Cloudflare API Token(GitHub Codespaces Secrets で管理)
- 個人用デバッグログ(kk-sync-diagnostics-*.zip 等)

確認方法:
```bash
# メアドが履歴に残っていないか定期確認
git log -S "@" --all --oneline | head
git log -p --all | grep -i "secret\|password\|token" | head
```

CF snapshot ZIP は `raw/*.json` にメアドや内部 ID を含む可能性があるため
(`CF_STATE.json` 側は redact 済)、外部にシェアする際は内容確認すること。
