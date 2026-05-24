from adapters.base import Article, make_article_id


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
