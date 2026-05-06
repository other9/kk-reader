/**
 * kk-reader sync Worker
 *
 * 既読状態とお気に入り状態を3端末間で同期するための最小APIサーバ。
 *
 * エンドポイント:
 *   GET  /state          - 全状態を返す
 *   POST /state/diff     - 差分を Last-Writer-Wins でマージ
 *
 * 認証: Authorization: Bearer <SYNC_SECRET>
 *   SYNC_SECRET は wrangler secret put で設定する。コードには含まない。
 *
 * データ形状:
 *   {
 *     read: { "<articleId>": {state: 0|1, ts: <unix ms>}, ... },
 *     fav:  { "<articleId>": {state: 0|1, ts: <unix ms>}, ... }
 *   }
 *   state: 1 = 既読/お気に入り, 0 = 明示的に取り消した
 *   登録なし = 一度も触っていない(=未読/未お気に入り)
 */

const ALLOWED_ORIGINS = [
  "https://other9.github.io",
  "http://localhost:8765",  // ローカル開発用
];

function corsHeaders(origin) {
  const allowedOrigin = ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0];
  return {
    "Access-Control-Allow-Origin": allowedOrigin,
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Authorization, Content-Type",
    "Access-Control-Max-Age": "86400",
    "Vary": "Origin",
  };
}

function jsonResponse(data, status, origin) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      ...corsHeaders(origin),
    },
  });
}

const STATE_KEY = "state:default";

export default {
  async fetch(request, env) {
    const origin = request.headers.get("Origin") || "";

    // CORS preflight
    if (request.method === "OPTIONS") {
      return new Response(null, { headers: corsHeaders(origin) });
    }

    // 認証
    const authHeader = request.headers.get("Authorization") || "";
    const token = authHeader.replace(/^Bearer\s+/i, "").trim();
    if (!env.SYNC_SECRET || !token || token !== env.SYNC_SECRET) {
      return jsonResponse({ error: "unauthorized" }, 401, origin);
    }

    const url = new URL(request.url);

    // GET /state
    if (request.method === "GET" && url.pathname === "/state") {
      const data = (await env.STATE.get(STATE_KEY, "json")) || { read: {}, fav: {} };
      return jsonResponse(data, 200, origin);
    }

    // POST /state/diff
    if (request.method === "POST" && url.pathname === "/state/diff") {
      let incoming;
      try {
        incoming = await request.json();
      } catch {
        return jsonResponse({ error: "invalid json" }, 400, origin);
      }

      const current = (await env.STATE.get(STATE_KEY, "json")) || { read: {}, fav: {} };
      const merged = {
        read: { ...current.read },
        fav: { ...current.fav },
      };

      for (const type of ["read", "fav"]) {
        const entries = incoming[type];
        if (!Array.isArray(entries)) continue;
        for (const e of entries) {
          if (
            !e || typeof e.id !== "string" ||
            (e.state !== 0 && e.state !== 1) ||
            typeof e.ts !== "number" || !isFinite(e.ts)
          ) continue;
          const existing = merged[type][e.id];
          if (!existing || e.ts > existing.ts) {
            merged[type][e.id] = { state: e.state, ts: e.ts };
          }
        }
      }

      await env.STATE.put(STATE_KEY, JSON.stringify(merged));
      return jsonResponse({ ok: true, state: merged }, 200, origin);
    }

    // health check (no auth needed for this would be nicer, but keeping it simple)
    if (request.method === "GET" && url.pathname === "/ping") {
      return jsonResponse({ ok: true, ts: Date.now() }, 200, origin);
    }

    return jsonResponse({ error: "not found" }, 404, origin);
  },
};
