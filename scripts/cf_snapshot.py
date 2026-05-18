#!/usr/bin/env python3
"""
cf_snapshot.py: Cloudflare-side state snapshot for kk-reader.

Parallels scripts/snapshot.py, but captures the deploy-side state on
Cloudflare instead of the source-side state on GitHub. Produces
kk-reader-cf-snapshot-YYYYMMDD-HHMMSS.zip with:

  - CF_STATE.json : aggregated summary (read this first)
  - README.txt    : explanation
  - raw/          : individual section dumps from CF API

Authentication:
  Set CLOUDFLARE_API_TOKEN as an env var. In Codespaces, this is provided
  via Settings -> Codespaces -> Secrets (already configured for wrangler).
  The token needs read scope for: Workers Scripts, Workers KV Storage,
  Cloudflare Pages, Access Apps and Policies. If any section's scope is
  missing, that section will record an error and the script continues.

Security:
  - Worker secrets: only names are recorded, never values
  - KV: keys are listed and counted, values are NOT fetched
  - Account email / user IDs in API responses are masked in CF_STATE.json
    summary (the raw/*.json files retain unmasked data for completeness;
    you may want to inspect raw/ before sharing the ZIP externally)
"""

from __future__ import annotations

import datetime
import json
import os
import pathlib
import re
import shutil
import sys
import tempfile
import zipfile
from collections import Counter
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SCHEMA_VERSION = 1

ACCOUNT_ID = "3fbbef709acd9608e64302bc0dec48a7"
WORKER_NAME = "kk-sync"
PAGES_PROJECT = "kk-reader"
KV_NAMESPACE_ID = "bcc0dd025aa34897b44a83f13ce88973"

API_BASE = "https://api.cloudflare.com/client/v4"
HTTP_TIMEOUT = 30
KV_KEY_PAGE_SIZE = 1000
KV_KEY_PAGE_MAX = 10  # cap at 10,000 keys to avoid runaway

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")


def env_token() -> str:
    t = os.environ.get("CLOUDFLARE_API_TOKEN")
    if not t:
        print("ERROR: CLOUDFLARE_API_TOKEN is not set in the environment.",
              file=sys.stderr)
        print("In Codespaces: this is normally set via Settings -> Codespaces "
              "-> Secrets. Confirm it is present (gh codespace ssh -- env "
              "| grep CLOUDFLARE) and re-run.", file=sys.stderr)
        sys.exit(1)
    return t


def cf_get(path: str, token: str, params: dict[str, Any] | None = None) -> Any:
    """GET a Cloudflare API endpoint. Returns the `result` field on success,
    or a {"_error": ...} dict on failure."""
    url = API_BASE + path
    if params:
        url += "?" + urlencode(params)
    req = Request(url, headers={
        "Authorization": "Bearer " + token,
        "Content-Type": "application/json",
        "Accept": "application/json",
    })
    try:
        with urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            body = resp.read()
    except HTTPError as e:
        try:
            err_body = e.read().decode("utf-8", "replace")[:1000]
        except Exception:
            err_body = ""
        return {"_error": f"HTTP {e.code}", "body": err_body, "path": path}
    except URLError as e:
        return {"_error": "URLError", "reason": str(e.reason), "path": path}
    except Exception as e:
        return {"_error": "Exception", "msg": str(e), "path": path}
    try:
        data = json.loads(body)
    except json.JSONDecodeError as e:
        return {"_error": "JSONDecodeError", "msg": str(e), "path": path}
    if not isinstance(data, dict) or not data.get("success"):
        return {"_error": "api_success=false",
                "errors": (data.get("errors") if isinstance(data, dict) else None),
                "path": path}
    return data.get("result", data)


def cf_kv_keys_all(token: str) -> dict[str, Any]:
    """List all KV keys via cursor pagination, capped at KV_KEY_PAGE_MAX pages."""
    keys: list[dict[str, Any]] = []
    cursor: str | None = None
    pages = 0
    truncated = False
    while True:
        params: dict[str, Any] = {"limit": KV_KEY_PAGE_SIZE}
        if cursor:
            params["cursor"] = cursor
        # Cursor-based KV listing uses the same endpoint but returns
        # result_info.cursor for pagination; we fetch the raw envelope.
        url = (API_BASE
               + f"/accounts/{ACCOUNT_ID}/storage/kv/namespaces/{KV_NAMESPACE_ID}/keys"
               + "?" + urlencode(params))
        req = Request(url, headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
        })
        try:
            with urlopen(req, timeout=HTTP_TIMEOUT) as r:
                env = json.loads(r.read())
        except Exception as e:
            return {"_error": str(e), "partial_count": len(keys),
                    "keys": keys}
        if not env.get("success"):
            return {"_error": "api_success=false",
                    "errors": env.get("errors"),
                    "partial_count": len(keys), "keys": keys}
        batch = env.get("result", []) or []
        keys.extend(batch)
        pages += 1
        cursor = (env.get("result_info") or {}).get("cursor")
        if not cursor or pages >= KV_KEY_PAGE_MAX or len(batch) == 0:
            if cursor and pages >= KV_KEY_PAGE_MAX:
                truncated = True
            break
    return {"total": len(keys), "truncated": truncated,
            "pages_fetched": pages, "keys": keys}


def mask_emails(obj: Any) -> Any:
    """Recursively replace email addresses with <email-redacted>."""
    if isinstance(obj, str):
        return EMAIL_RE.sub("<email-redacted>", obj)
    if isinstance(obj, list):
        return [mask_emails(x) for x in obj]
    if isinstance(obj, dict):
        return {k: mask_emails(v) for k, v in obj.items()}
    return obj


def summarize_worker_deployments(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict) and "_error" in payload:
        return {"status": "error", "detail": payload}
    if not isinstance(payload, dict):
        return {"status": "unexpected_shape"}
    deployments = payload.get("deployments") or payload.get("items") or []
    if isinstance(deployments, dict):
        deployments = deployments.get("items", [])
    summary_items = []
    for d in deployments[:10]:
        if not isinstance(d, dict):
            continue
        summary_items.append({
            "id": d.get("id"),
            "number": d.get("number"),
            "created_on": d.get("created_on"),
            "annotations": d.get("annotations"),
            "author_email": EMAIL_RE.sub("<redacted>", str(d.get("author_email", ""))) or None,
            "source": d.get("source"),
            "strategy": d.get("strategy"),
        })
    return {"status": "ok", "count": len(deployments), "recent": summary_items}


def summarize_worker_settings(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict) and "_error" in payload:
        return {"status": "error", "detail": payload}
    if not isinstance(payload, dict):
        return {"status": "unexpected_shape"}
    bindings = payload.get("bindings") or []
    binding_summary = []
    for b in bindings:
        if not isinstance(b, dict):
            continue
        binding_summary.append({
            "name": b.get("name"),
            "type": b.get("type"),
            "namespace_id": b.get("namespace_id"),
        })
    return {
        "status": "ok",
        "compatibility_date": payload.get("compatibility_date"),
        "compatibility_flags": payload.get("compatibility_flags"),
        "usage_model": payload.get("usage_model"),
        "logpush": payload.get("logpush"),
        "placement": payload.get("placement"),
        "bindings": binding_summary,
    }


def summarize_worker_secrets(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict) and "_error" in payload:
        return {"status": "error", "detail": payload}
    if not isinstance(payload, list):
        return {"status": "unexpected_shape"}
    names = [s.get("name") for s in payload if isinstance(s, dict)]
    return {"status": "ok", "count": len(names), "names": names}


def summarize_kv_keys(payload: dict[str, Any]) -> dict[str, Any]:
    if "_error" in payload:
        return {"status": "error", "detail": payload}
    keys = payload.get("keys", [])
    prefixes: Counter[str] = Counter()
    state_keys: list[str] = []
    sample_article: list[str] = []
    for k in keys:
        if not isinstance(k, dict):
            continue
        name = k.get("name", "")
        if name.startswith("state:"):
            state_keys.append(name)
            prefixes["state:"] += 1
        elif name.startswith("article:v3:"):
            prefixes["article:v3:"] += 1
            if len(sample_article) < 5:
                sample_article.append(name)
        elif name.startswith("article:v2:"):
            prefixes["article:v2: (stale)"] += 1
        elif name.startswith("article:v1:"):
            prefixes["article:v1: (stale)"] += 1
        else:
            prefixes["<other>"] += 1
    return {
        "status": "ok",
        "total_keys": payload.get("total", len(keys)),
        "truncated": payload.get("truncated", False),
        "pages_fetched": payload.get("pages_fetched"),
        "by_prefix": dict(prefixes),
        "state_keys": state_keys,
        "sample_article_keys": sample_article,
    }


def summarize_pages_project(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict) and "_error" in payload:
        return {"status": "error", "detail": payload}
    if not isinstance(payload, dict):
        return {"status": "unexpected_shape"}
    build_cfg = payload.get("build_config", {}) or {}
    deploy_cfg = payload.get("deployment_configs", {}) or {}
    source = payload.get("source", {}) or {}
    source_cfg = source.get("config", {}) or {}
    return {
        "status": "ok",
        "name": payload.get("name"),
        "subdomain": payload.get("subdomain"),
        "domains": payload.get("domains"),
        "production_branch": payload.get("production_branch"),
        "build_config": {
            "build_command": build_cfg.get("build_command"),
            "destination_dir": build_cfg.get("destination_dir"),
            "root_dir": build_cfg.get("root_dir"),
            "build_caching": build_cfg.get("build_caching"),
        },
        "source": {
            "type": source.get("type"),
            "owner": source_cfg.get("owner"),
            "repo_name": source_cfg.get("repo_name"),
            "production_branch": source_cfg.get("production_branch"),
            "deployments_enabled": source_cfg.get("deployments_enabled"),
        },
        "deployment_configs_keys": list(deploy_cfg.keys()),
        "created_on": payload.get("created_on"),
        "canonical_deployment_url": (payload.get("canonical_deployment") or {}).get("url"),
        "latest_deployment_url": (payload.get("latest_deployment") or {}).get("url"),
    }


def summarize_pages_deployments(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict) and "_error" in payload:
        return {"status": "error", "detail": payload}
    items: list[Any] = []
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = payload.get("result") or payload.get("items") or []
    if not isinstance(items, list):
        return {"status": "unexpected_shape"}
    summary_items = []
    env_counts: Counter[str] = Counter()
    stage_status_counts: Counter[str] = Counter()
    auto_build_count = 0
    manual_count = 0
    for d in items:
        if not isinstance(d, dict):
            continue
        env = d.get("environment", "?")
        env_counts[env] += 1
        deploy_trigger = (d.get("deployment_trigger") or {})
        trigger_type = deploy_trigger.get("type", "?")
        if trigger_type == "ad_hoc":
            manual_count += 1
        else:
            auto_build_count += 1
        latest_stage = (d.get("latest_stage") or {})
        stage_status_counts[f"{latest_stage.get('name','?')}/{latest_stage.get('status','?')}"] += 1
        meta = deploy_trigger.get("metadata") or {}
        summary_items.append({
            "id": d.get("id"),
            "short_id": d.get("short_id"),
            "url": d.get("url"),
            "environment": env,
            "created_on": d.get("created_on"),
            "modified_on": d.get("modified_on"),
            "trigger_type": trigger_type,
            "branch": meta.get("branch"),
            "commit_hash": meta.get("commit_hash"),
            "commit_message": (meta.get("commit_message") or "")[:120],
            "latest_stage_name": latest_stage.get("name"),
            "latest_stage_status": latest_stage.get("status"),
            "is_skipped": d.get("is_skipped"),
        })
    return {
        "status": "ok",
        "count": len(summary_items),
        "by_environment": dict(env_counts),
        "by_stage_status": dict(stage_status_counts),
        "auto_build_count": auto_build_count,
        "manual_count": manual_count,
        "items": summary_items,
    }


def summarize_access_apps(payload: Any) -> tuple[dict[str, Any], list[str]]:
    if isinstance(payload, dict) and "_error" in payload:
        return {"status": "error", "detail": payload}, []
    if not isinstance(payload, list):
        return {"status": "unexpected_shape"}, []
    apps_summary = []
    app_ids = []
    for a in payload:
        if not isinstance(a, dict):
            continue
        app_ids.append(a.get("id"))
        apps_summary.append({
            "id": a.get("id"),
            "name": a.get("name"),
            "domain": a.get("domain"),
            "type": a.get("type"),
            "session_duration": a.get("session_duration"),
            "auto_redirect_to_identity": a.get("auto_redirect_to_identity"),
            "allowed_idps": a.get("allowed_idps"),
            "created_at": a.get("created_at"),
            "updated_at": a.get("updated_at"),
        })
    return {"status": "ok", "count": len(apps_summary), "items": apps_summary}, app_ids


def summarize_access_policies(policies_by_app: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for app_id, raw in policies_by_app.items():
        if isinstance(raw, dict) and "_error" in raw:
            out[app_id] = {"status": "error", "detail": raw}
            continue
        if not isinstance(raw, list):
            out[app_id] = {"status": "unexpected_shape"}
            continue
        items = []
        for p in raw:
            if not isinstance(p, dict):
                continue
            items.append({
                "id": p.get("id"),
                "name": p.get("name"),
                "decision": p.get("decision"),
                "precedence": p.get("precedence"),
                "rule_count": {
                    "include": len(p.get("include") or []),
                    "exclude": len(p.get("exclude") or []),
                    "require": len(p.get("require") or []),
                },
                "session_duration": p.get("session_duration"),
            })
        out[app_id] = {"status": "ok", "count": len(items), "items": items}
    return out


def write_zip(out_path: pathlib.Path, raw: dict[str, Any], summary: dict[str, Any],
              generated_at: datetime.datetime) -> None:
    with tempfile.TemporaryDirectory() as td:
        td_path = pathlib.Path(td)
        # Raw dumps (verbatim from API)
        raw_dir = td_path / "raw"
        raw_dir.mkdir()
        for name, payload in raw.items():
            (raw_dir / f"{name}.json").write_text(
                json.dumps(payload, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
        # Aggregated summary (emails masked)
        (td_path / "CF_STATE.json").write_text(
            json.dumps(mask_emails(summary), indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        # Human-readable header
        (td_path / "README.txt").write_text(make_readme(summary, generated_at),
                                            encoding="utf-8")
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for entry in td_path.rglob("*"):
                if entry.is_file():
                    zf.write(entry, entry.relative_to(td_path))


def make_readme(summary: dict[str, Any], generated_at: datetime.datetime) -> str:
    pages = summary.get("pages_deployments", {})
    worker = summary.get("worker_deployments", {})
    apps = summary.get("access_apps", {})
    kv = summary.get("kv_keys", {})
    lines = [
        "# kk-reader Cloudflare Snapshot",
        "",
        f"Generated: {generated_at.isoformat()}",
        f"Schema:    {SCHEMA_VERSION}",
        "",
        "## ファイル構成",
        "",
        "- CF_STATE.json : 集約サマリ(まずこれを読む。メールアドレスは redaction 済み)",
        "- raw/          : Cloudflare API のレスポンス verbatim",
        "                  (raw 配下にはメールアドレスや内部 ID が残る、外部に",
        "                   出すときは内容確認すること)",
        "",
        "## 取得セクション(成功/失敗)",
        "",
    ]
    for key in ("worker_deployments", "worker_settings", "worker_secrets",
                "kv_keys", "pages_project", "pages_deployments",
                "access_apps", "access_policies"):
        section = summary.get(key, {})
        if key == "access_policies" and isinstance(section, dict):
            substatuses = [v.get("status", "?") for v in section.values()
                           if isinstance(v, dict)]
            if not substatuses:
                status = "(no apps)"
            elif all(s == "ok" for s in substatuses):
                status = f"ok ({len(section)} app(s))"
            else:
                status = ", ".join(substatuses)
            lines.append(f"- {key}: {status}")
        elif isinstance(section, dict):
            status = section.get("status", "?")
            lines.append(f"- {key}: {status}")
    lines.extend([
        "",
        "## サマリ統計",
        "",
        f"- Worker deployments (recent): {worker.get('count', '?')}",
        f"- Pages deployments (in window): {pages.get('count', '?')}",
        f"  - by trigger: auto={pages.get('auto_build_count','?')}, manual={pages.get('manual_count','?')}",
        f"  - by env:     {pages.get('by_environment', {})}",
        f"  - by stage:   {pages.get('by_stage_status', {})}",
        f"- Access apps: {apps.get('count', '?')}",
        f"- KV keys total: {kv.get('total_keys', '?')}"
        + (" (truncated)" if kv.get('truncated') else ""),
        f"- KV by prefix: {kv.get('by_prefix', {})}",
        "",
        "## 含まないもの(意図的)",
        "",
        "- Worker secrets の値(名前のみ、SYNC_SECRET 等)",
        "- KV values(state:default の中身、article cache の中身)",
        "- Worker のソースコード(repo にある)",
        "- Cloudflare アカウントのメール、課金情報",
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    token = env_token()
    generated_at = datetime.datetime.now(datetime.timezone.utc)
    stamp = generated_at.strftime("%Y%m%d-%H%M%S")

    print("== fetching Cloudflare state ==")

    raw: dict[str, Any] = {}

    print("  worker deployments ...", end=" ", flush=True)
    raw["worker_deployments"] = cf_get(
        f"/accounts/{ACCOUNT_ID}/workers/deployments",
        token,
        {"script": WORKER_NAME},
    )
    print("ok" if "_error" not in (raw["worker_deployments"] if isinstance(raw["worker_deployments"], dict) else {}) else "err")

    print("  worker settings    ...", end=" ", flush=True)
    raw["worker_settings"] = cf_get(
        f"/accounts/{ACCOUNT_ID}/workers/scripts/{WORKER_NAME}/settings",
        token,
    )
    print("ok" if "_error" not in (raw["worker_settings"] if isinstance(raw["worker_settings"], dict) else {}) else "err")

    print("  worker secrets     ...", end=" ", flush=True)
    raw["worker_secrets"] = cf_get(
        f"/accounts/{ACCOUNT_ID}/workers/scripts/{WORKER_NAME}/secrets",
        token,
    )
    print("ok" if isinstance(raw["worker_secrets"], list) else "err")

    print("  kv keys (paginated)...", end=" ", flush=True)
    raw["kv_keys"] = cf_kv_keys_all(token)
    print("ok" if "_error" not in raw["kv_keys"] else "err")

    print("  pages project      ...", end=" ", flush=True)
    raw["pages_project"] = cf_get(
        f"/accounts/{ACCOUNT_ID}/pages/projects/{PAGES_PROJECT}",
        token,
    )
    print("ok" if "_error" not in (raw["pages_project"] if isinstance(raw["pages_project"], dict) else {}) else "err")

    print("  pages deployments  ...", end=" ", flush=True)
    raw["pages_deployments"] = cf_get(
        f"/accounts/{ACCOUNT_ID}/pages/projects/{PAGES_PROJECT}/deployments",
        token,
        {"per_page": 25},
    )
    print("ok" if not (isinstance(raw["pages_deployments"], dict) and "_error" in raw["pages_deployments"]) else "err")

    print("  access apps        ...", end=" ", flush=True)
    raw["access_apps"] = cf_get(
        f"/accounts/{ACCOUNT_ID}/access/apps",
        token,
    )
    apps_ok = isinstance(raw["access_apps"], list)
    print("ok" if apps_ok else "err")

    raw["access_policies"] = {}
    if apps_ok:
        print("  access policies    ...", end=" ", flush=True)
        for app in raw["access_apps"]:
            if not isinstance(app, dict):
                continue
            aid = app.get("id")
            if not aid:
                continue
            raw["access_policies"][aid] = cf_get(
                f"/accounts/{ACCOUNT_ID}/access/apps/{aid}/policies",
                token,
            )
        print("ok")

    # Build summary
    print()
    print("== summarizing ==")
    summary: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at.isoformat(),
        "account_id": ACCOUNT_ID,
        "worker_name": WORKER_NAME,
        "pages_project": PAGES_PROJECT,
        "kv_namespace_id": KV_NAMESPACE_ID,
    }
    summary["worker_deployments"] = summarize_worker_deployments(raw["worker_deployments"])
    summary["worker_settings"] = summarize_worker_settings(raw["worker_settings"])
    summary["worker_secrets"] = summarize_worker_secrets(raw["worker_secrets"])
    summary["kv_keys"] = summarize_kv_keys(raw["kv_keys"])
    summary["pages_project"] = summarize_pages_project(raw["pages_project"])
    summary["pages_deployments"] = summarize_pages_deployments(raw["pages_deployments"])
    apps_summary, _ = summarize_access_apps(raw["access_apps"])
    summary["access_apps"] = apps_summary
    summary["access_policies"] = summarize_access_policies(raw["access_policies"])

    # Print compact stdout summary
    print()
    pages = summary["pages_deployments"]
    worker = summary["worker_deployments"]
    kv = summary["kv_keys"]
    apps = summary["access_apps"]
    print(f"Worker deployments recent: {worker.get('count', '?')}")
    print(f"Pages deployments (window): {pages.get('count', '?')}")
    print(f"  auto/manual: {pages.get('auto_build_count','?')}/{pages.get('manual_count','?')}")
    print(f"  by env: {pages.get('by_environment', {})}")
    print(f"Access apps: {apps.get('count', '?')}")
    print(f"KV total keys: {kv.get('total_keys', '?')}  by_prefix: {kv.get('by_prefix', {})}")

    out_path = pathlib.Path(f"kk-reader-cf-snapshot-{stamp}.zip")
    write_zip(out_path, raw, summary, generated_at)
    print()
    print(f"OK: wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
