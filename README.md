# kk reader

Feedlyの代替として動作する、AI拡張可能な個人用RSSリーダー。

## 特徴

- **GitHub Actions主導**: 2時間ごとに全フィードを自動取得、無料枠で完結
- **静的サイト**: GitHub Pagesでホスト、サーバー管理不要
- **既読/お気に入り**: ブラウザのlocalStorageで永続化(端末ローカル)
- **エディトリアル風UI**: Noto Serif JP、3カラム、キーボード操作対応
- **キーボード操作**: `j`/`k` 移動、`m` 既読切替、`f` お気に入り、`o` 元記事、`u` 未読フィルタ切替、`/` 検索
- **将来拡張対応**: アダプター層により非RSSソース(メール、Cookie認証取得、スクレイピング等)を後から追加可能

## アーキテクチャ

```
┌─────────────────────┐
│  GitHub Actions     │ ← 2時間ごとcron
│  (fetch_feeds.py)   │
└──────────┬──────────┘
           │ 並列取得・正規化
           ↓
┌─────────────────────┐
│ docs/data/*.json    │ ← コミット
└──────────┬──────────┘
           │ GitHub Pages配信
           ↓
┌─────────────────────┐
│  ブラウザ(SPA)       │ ← localStorageで状態保持
└─────────────────────┘
```

## ディレクトリ構造

```
kk-reader/
├── .github/workflows/
│   ├── fetch-feeds.yml      # 取得ワークフロー（2時間ごと）
│   ├── ci.yml               # 品質チェック（push時）
│   └── dependabot.yml       # 依存関係自動更新
├── docs/                     # GitHub Pages公開ディレクトリ
│   ├── index.html
│   ├── app.js
│   ├── style.css
│   └── data/
│       ├── feeds.json       # フィード一覧(自動更新)
│       └── articles.json    # 記事キャッシュ(自動更新)
├── opml/
│   └── subscriptions.opml   # 購読リスト(編集可)
├── scripts/
│   ├── opml_to_feeds.py     # OPML → feeds.json 変換
│   ├── fetch_feeds.py       # 取得・正規化
│   └── adapters/            # ソース別アダプター
│       ├── base.py          # 基底クラス
│       └── rss_adapter.py   # RSS取得
├── tests/
│   └── test_adapters.py     # 単体テスト（3件）
├── worker/
│   ├── worker.js            # kk-sync Cloudflare Worker
│   └── wrangler.toml
├── pyproject.toml           # Ruff + pytest 設定
├── requirements.txt
└── SETUP.md                  # デプロイ手順
```

## 設定値の調整

`scripts/fetch_feeds.py` 上部で以下を変更できます:

| 設定 | 既定値 | 説明 |
|------|--------|------|
| `RETENTION_DAYS` | 30 | 何日分の記事を保持するか |
| `MAX_WORKERS` | 12 | 並列取得スレッド数 |
| `DISABLE_AFTER_FAILURES` | 10 | 連続失敗で自動無効化する閾値 |

## 品質チェック

```bash
pip install -r requirements.txt
ruff check .          # lint（F + E9 ルール）
pytest tests/ -v      # 単体テスト（3件）
```

push のたびに CI が自動実行されます（`docs/data/**` 更新時は除外）。

## 将来拡張: 非RSSソースの追加

```python
# scripts/adapters/email_adapter.py
from .base import SourceAdapter, Article

class EmailAdapter(SourceAdapter):
    source_type = "email"
    def fetch(self, feed):
        # IMAP接続してメッセージ取得 → Article化
        ...
```

`adapters/__init__.py` の `ADAPTERS` 辞書に登録するだけで自動処理されます。

## デプロイ手順

[SETUP.md](SETUP.md) 参照。
