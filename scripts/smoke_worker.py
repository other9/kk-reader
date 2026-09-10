"""Authenticated operational checks; never print credentials or state contents."""
import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request


def canonical_hash(state):
    encoded = json.dumps(state, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


def main():
    token = os.environ["WORKER_TOKEN"]
    base = os.environ["WORKER_BASE_URL"].rstrip("/")
    origin = "https://kk-reader.pages.dev"

    def call(path, method="GET", payload=None):
        req = urllib.request.Request(base + path, method=method,
            headers={"Authorization": "Bearer " + token, "Origin": origin,
                     "Content-Type": "application/json"},
            data=json.dumps(payload).encode() if payload is not None else None)
        try:
            response = urllib.request.urlopen(req, timeout=30)
        except urllib.error.HTTPError as response_error:
            response = response_error
        with response:
            assert response.headers.get("Access-Control-Allow-Origin") == origin
            body = response.read()
            return response.status, json.loads(body) if body else None

    status, ping = call("/ping")
    assert status == 200 and ping["ok"]
    status, state = call("/state")
    assert status == 200 and isinstance(state.get("read"), dict) and isinstance(state.get("fav"), dict)
    fingerprint = canonical_hash(state)
    expected = os.environ.get("EXPECTED_STATE_SHA256", "")
    if expected:
        assert fingerprint == expected, "State fingerprint differs from the migration backup"
    print("State verified:", "read", len(state["read"]), "fav", len(state["fav"]), "sha256", fingerprint)
    maintenance = os.environ.get("EXPECT_MAINTENANCE") == "true"
    status, result = call("/state/diff", "POST", {"read": [], "fav": []})
    if maintenance:
        assert status == 503, "State writes were not paused"
    else:
        assert status == 200 and result["ok"], "State writes unavailable"
    status, _ = call("/state/diff", "OPTIONS")
    assert status in (200, 204)
    # Same /fetch contract used by joto; an upstream denial is not a Worker failure.
    target = urllib.parse.quote("https://www.kenbiya.com/", safe="")
    status, result = call("/fetch?url=" + target)
    assert status == 200 and isinstance(result.get("status"), int)
    assert "html" in result or "error" in result
    print("Shared fetch contract verified; upstream status", result["status"])
    print("PASS authenticated ping/state/write-mode/CORS/shared-fetch")


if __name__ == "__main__":
    main()
