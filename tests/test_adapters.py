from bs4 import BeautifulSoup

from adapters.base import Article, make_article_id
from adapters.kenbiya_scraper import KenbiyaColumnsAdapter


def test_make_article_id_consistent():
    url = "https://example.com/article/1"
    assert make_article_id(url) == make_article_id(url)
    assert len(make_article_id(url)) == 16


def test_make_article_id_guid_overrides_url():
    by_url = make_article_id("https://x.com/a")
    by_guid = make_article_id("https://x.com/a", guid="unique-guid-123")
    assert by_url != by_guid


def test_article_to_dict_fields():
    a = Article(
        id="abc", feed_id="f1", feed_title="My Feed", category="tech",
        title="Hello World", url="https://example.com/hello",
        published=None, fetched="2026-01-01T00:00:00+00:00",
        summary="A test article", content_html=None,
        author=None, source_type="rss",
    )
    d = a.to_dict()
    assert d["id"] == "abc"
    assert d["source_type"] == "rss"
    assert d["published"] is None
    assert d["title"] == "Hello World"


# --- update-020: 健美家の本文抽出 (parse_article_body) ---

_KENBIYA_ARTICLE_HTML = """
<html><body>
  <section class="contents_detail_main">
    <div class="detail_col1">
      <div class="share">シェア ツイート 2026/6/18 掲載</div>
      <div id="box_entry">
        <p>本文の<strong>1段落目</strong>です。</p>
        <p>画像: <img src="/img/photo.jpg" alt="写真"></p>
        <p><a href="/ar/cl/foo/2.html" onclick="evil()">関連リンク</a></p>
        <script>window.tracker();</script>
        <p style="color:red" onmouseover="x()">スタイル付き段落。</p>
      </div>
    </div>
    <div class="column"><ul><li>関連記事リスト</li></ul></div>
  </section>
</body></html>
"""


def _ken_body():
    soup = BeautifulSoup(_KENBIYA_ARTICLE_HTML, "html.parser")
    return KenbiyaColumnsAdapter().parse_article_body(
        soup, "https://www.kenbiya.com/ar/cl/foo/1.html"
    )


def test_kenbiya_body_extracts_entry_not_related():
    body = _ken_body()
    assert body is not None
    assert "本文の" in body and "1段落目" in body
    # 共有ボタン・関連記事リストは含まれない
    assert "関連記事リスト" not in body
    assert "シェア ツイート" not in body


def test_kenbiya_body_is_sanitized():
    body = _ken_body()
    # script / イベントハンドラ / inline style は除去
    assert "<script" not in body.lower()
    assert "window.tracker" not in body
    assert "onclick" not in body.lower()
    assert "onmouseover" not in body.lower()
    assert "style=" not in body.lower()
    # 相対 URL は絶対化される
    assert "https://www.kenbiya.com/img/photo.jpg" in body
    assert "https://www.kenbiya.com/ar/cl/foo/2.html" in body


def test_kenbiya_body_none_when_missing():
    soup = BeautifulSoup("<html><body><p>no entry</p></body></html>", "html.parser")
    assert KenbiyaColumnsAdapter().parse_article_body(soup, "https://x") is None
