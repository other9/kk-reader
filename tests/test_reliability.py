import json
from unittest.mock import Mock

import pytest

import fetch_feeds as f
from adapters.kenbiya_scraper import KenbiyaColumnsAdapter


@pytest.mark.parametrize("payload", [
    {}, [], None, {"fav": []}, {"fav": {"a": {"state": 2, "ts": 1}}},
    {"fav": {"a": {"state": 1}}}, {"fav": {"a": {"state": 1, "ts": float("nan")}}},
])
def test_invalid_favorites_prevent_pruning(monkeypatch, payload):
    monkeypatch.setenv("WORKER_BASE_URL", "https://test.invalid")
    monkeypatch.setenv("WORKER_TOKEN", "dummy")
    response = Mock(status_code=200)
    response.json.return_value = payload
    monkeypatch.setattr(f.requests, "get", lambda *a, **k: response)
    assert f.fetch_fav_ids(retries=0) is None


@pytest.mark.parametrize("success,failed,previous", [
    (0, 0, {}), (0, 5, {}), (4, 6, {}),
    (6, 4, {"feeds_success": 10, "feeds_failed": 0}),
])
def test_collection_gate_rejects_outages(success, failed, previous):
    with pytest.raises(RuntimeError):
        f.check_fetch_health(success, failed, previous, {})


def test_collection_gate_allows_healthy_304s_and_small_fluctuations():
    f.check_fetch_health(9, 1, {"feeds_success": 10, "feeds_failed": 0}, {})


def test_all_failed_does_not_overwrite_data(monkeypatch, tmp_path):
    feed = {"id": "x", "title": "test", "category": "test", "active": True}
    articles = tmp_path / "articles.json"
    feeds = tmp_path / "feeds.json"
    articles.write_text('{"articles": [], "last_updated": "before"}')
    feeds.write_text('{"feeds": []}')
    monkeypatch.setattr(f, "load_feeds", lambda: {"feeds": [feed]})
    monkeypatch.setattr(f, "load_existing_articles", lambda: {"articles": []})
    monkeypatch.setattr(f, "fetch_one", lambda *args: (
        feed, [], {"last_error": "simulated outage", "error_count": 1}))
    monkeypatch.setattr(f, "DATA_DIR", tmp_path)
    monkeypatch.setattr(f, "ARTICLES_PATH", articles)
    monkeypatch.setattr(f, "FEEDS_PATH", feeds)
    with pytest.raises(RuntimeError):
        f.main()
    assert json.loads(articles.read_text())["last_updated"] == "before"
    assert json.loads(feeds.read_text()) == {"feeds": []}


@pytest.mark.parametrize("previous,count", [(0, 0), (20, 2)])
def test_scraper_empty_or_collapsed_page_is_not_success(monkeypatch, previous, count):
    adapter = KenbiyaColumnsAdapter()
    monkeypatch.setattr(adapter, "_fetch_html", lambda *args: ("<html></html>", None))
    monkeypatch.setattr(adapter, "parse_listing", lambda *args, **kwargs: [
        {"url": f"https://example.invalid/{i}", "title": "test"} for i in range(count)])
    feed = {"id": "x", "title": "test", "url": "https://example.invalid",
            "last_items_count": previous}
    articles, metadata = adapter.fetch(feed)
    assert articles == []
    assert metadata["health_error"]
    assert metadata["last_error"]
    assert "last_success" not in metadata
    with pytest.raises(RuntimeError):
        f.check_fetch_health(9, 1, {}, {"x": metadata})
