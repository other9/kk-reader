"""fetch_feeds.py の prune ロジックのテスト(update-021)。

お気に入り記事が保持期間(RETENTION_DAYS)を過ぎても articles.json に
残ることを検証する。
"""
from unittest import mock

import fetch_feeds


CUTOFF = "2026-07-13T00:00:00+00:00"

OLD_FAV = {"id": "aaa", "published": "2026-06-01T00:00:00+00:00"}
OLD_PLAIN = {"id": "bbb", "published": "2026-06-01T00:00:00+00:00"}
NEW_PLAIN = {"id": "ccc", "published": "2026-08-01T00:00:00+00:00"}
OLD_NO_PUBLISHED = {"id": "ddd", "published": None, "fetched": "2026-06-01T00:00:00+00:00"}


def test_prune_keeps_recent_articles():
    kept, pruned, fav_exempt = fetch_feeds.prune_articles([NEW_PLAIN], CUTOFF, set())
    assert kept == [NEW_PLAIN]
    assert pruned == 0
    assert fav_exempt == 0


def test_prune_removes_old_non_fav():
    kept, pruned, fav_exempt = fetch_feeds.prune_articles(
        [OLD_PLAIN, OLD_NO_PUBLISHED], CUTOFF, set()
    )
    assert kept == []
    assert pruned == 2
    assert fav_exempt == 0


def test_prune_exempts_old_favorites():
    kept, pruned, fav_exempt = fetch_feeds.prune_articles(
        [OLD_FAV, OLD_PLAIN, NEW_PLAIN], CUTOFF, {"aaa"}
    )
    assert kept == [OLD_FAV, NEW_PLAIN]
    assert pruned == 1
    assert fav_exempt == 1


def test_prune_fav_within_retention_not_counted_as_exempt():
    # 保持期間内のお気に入りは通常の保持であって免除カウントしない
    kept, pruned, fav_exempt = fetch_feeds.prune_articles([NEW_PLAIN], CUTOFF, {"ccc"})
    assert kept == [NEW_PLAIN]
    assert fav_exempt == 0


def _mock_response(status=200, payload=None):
    r = mock.Mock()
    r.status_code = status
    r.json.return_value = payload if payload is not None else {}
    return r


def test_fetch_fav_ids_returns_state1_only(monkeypatch):
    monkeypatch.setenv("WORKER_BASE_URL", "https://example.workers.dev")
    monkeypatch.setenv("WORKER_TOKEN", "tok")
    payload = {
        "read": {"xxx": {"state": 1, "ts": 1}},
        "fav": {
            "aaa": {"state": 1, "ts": 1},
            "bbb": {"state": 0, "ts": 2},  # 解除済みは含めない
        },
    }
    with mock.patch.object(fetch_feeds.requests, "get", return_value=_mock_response(200, payload)):
        assert fetch_feeds.fetch_fav_ids() == {"aaa"}


def test_fetch_fav_ids_empty_fav_is_empty_set(monkeypatch):
    # お気に入りゼロは「取得成功・空」であり None(失敗)と区別する
    monkeypatch.setenv("WORKER_BASE_URL", "https://example.workers.dev")
    monkeypatch.setenv("WORKER_TOKEN", "tok")
    with mock.patch.object(
        fetch_feeds.requests, "get",
        return_value=_mock_response(200, {"read": {}, "fav": {}}),
    ):
        assert fetch_feeds.fetch_fav_ids() == set()


def test_fetch_fav_ids_none_when_unconfigured(monkeypatch):
    monkeypatch.delenv("WORKER_BASE_URL", raising=False)
    monkeypatch.delenv("WORKER_TOKEN", raising=False)
    assert fetch_feeds.fetch_fav_ids() is None


def test_fetch_fav_ids_none_on_http_error(monkeypatch):
    monkeypatch.setenv("WORKER_BASE_URL", "https://example.workers.dev")
    monkeypatch.setenv("WORKER_TOKEN", "tok")
    with mock.patch.object(fetch_feeds.requests, "get", return_value=_mock_response(500)):
        assert fetch_feeds.fetch_fav_ids(retries=1, retry_delay=0) is None


def test_fetch_fav_ids_none_on_network_error(monkeypatch):
    monkeypatch.setenv("WORKER_BASE_URL", "https://example.workers.dev")
    monkeypatch.setenv("WORKER_TOKEN", "tok")
    with mock.patch.object(
        fetch_feeds.requests, "get",
        side_effect=fetch_feeds.requests.exceptions.ConnectionError("boom"),
    ):
        assert fetch_feeds.fetch_fav_ids(retries=1, retry_delay=0) is None
