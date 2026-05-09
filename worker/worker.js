/**
 * kk-reader sync Worker
 *
 * 機能:
 *   1. 既読/お気に入り状態の同期 (旧)
 *   2. 記事本文のon-demand取得+キャッシュ (update-007)
 *   3. 任意 URL の HTML プロキシ取得 (update-009)
 *
 * エンドポイント:
 *   GET  /state           - 全状態を返す
 *   POST /state/diff      - 差分を Last-Writer-Wins でマージ
 *   GET  /article?url=X   - 指定URLの記事を取得し、本文を抽出してキャッシュ
 *   GET  /fetch?url=X     - 指定URLの生HTMLを取得して JSON で返す(キャッシュなし)
 *   GET  /ping            - ヘルスチェック
 *
 * 認証: Authorization: Bearer <SYNC_SECRET>
 *
 * /article と /fetch の違い:
 *   /article は本文抽出 + KV キャッシュ。フロントエンドの詳細表示用。
 *   /fetch   は生HTMLをそのまま返すプロキシ。Python adapter の listing 取得用。
 *           Actions IP が WAF で弾かれるサイト(楽待等)対策。
 */

const ALLOWED_ORIGINS = [
  "https://other9.github.io",
  "http://localhost:8765",
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

// 記事キャッシュTTL: 30日
const ARTICLE_CACHE_TTL_SECONDS = 30 * 24 * 3600;

// HTMLフェッチ時の偽装UA(サイトのbot検出回避)
const FETCH_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36";

// /fetch で送信するブラウザ完全偽装ヘッダ(WAF 回避)
const PROXY_FETCH_HEADERS = {
  "User-Agent": FETCH_UA,
  "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
  "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
  "Accept-Encoding": "gzip, deflate, br",
  "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="121", "Google Chrome";v="121"',
  "Sec-Ch-Ua-Mobile": "?0",
  "Sec-Ch-Ua-Platform": '"Linux"',
  "Sec-Fetch-Dest": "document",
  "Sec-Fetch-Mode": "navigate",
  "Sec-Fetch-Site": "none",
  "Sec-Fetch-User": "?1",
  "Upgrade-Insecure-Requests": "1",
  "Cache-Control": "no-cache",
  "Pragma": "no-cache",
};

// =====================================================================
// 認証
// =====================================================================

function checkAuth(request, env) {
  const authHeader = request.headers.get("Authorization") || "";
  const token = authHeader.replace(/^Bearer\s+/i, "").trim();
  if (!env.SYNC_SECRET || !token || token !== env.SYNC_SECRET) {
    return false;
  }
  return true;
}

// =====================================================================
// 記事ID生成 (URL → sha256 hex)
// =====================================================================

async function urlHash(url) {
  const enc = new TextEncoder().encode(url);
  const buf = await crypto.subtle.digest("SHA-256", enc);
  return [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, "0")).join("").slice(0, 32);
}

// =====================================================================
// HTML抽出: サイト別本文セレクタ (/article 用)
// =====================================================================

function extractorFor(url) {
  const u = new URL(url);
  const host = u.hostname.replace(/^www\./, "");

  if (host === "kenbiya.com") {
    return {
      contentSelectors: ["div#contents", "div.article-body", "article", "div.entry-content"],
      removeSelectors: ["script", "style", "nav", "header", "footer", "aside",
                       ".sns-share", ".related", ".breadcrumb", ".pagenavi"],
    };
  }

  if (host === "rakumachi.jp") {
    return {
      contentSelectors: ["article.news-detail", "div.article-body", "article", "main", "div#main"],
      removeSelectors: ["script", "style", "nav", "header", "footer", "aside",
                       ".sns-share", ".related", ".author-info", ".breadcrumb", ".comment"],
    };
  }

  return {
    contentSelectors: ["article", "main", "div[role='main']", "div.entry-content", "div.post"],
    removeSelectors: ["script", "style", "nav", "header", "footer", "aside",
                     ".sns-share", ".related", ".breadcrumb"],
  };
}

async function extractContent(html, url) {
  const config = extractorFor(url);
  let title = "";
  let collected = "";
  let foundContainer = false;

  // タイトル抽出
  let titleCollecting = false;
  const rewriterTitle = new HTMLRewriter()
    .on("title", {
      element() { titleCollecting = true; },
      text(t) { if (titleCollecting) title += t.text; }
    })
    .on("h1", {
      element() {
        if (!title) titleCollecting = true;
      },
      text(t) {
        if (titleCollecting && !title.includes(t.text)) title += t.text;
      }
    });

  const responseForTitle = new Response(html);
  await rewriterTitle.transform(responseForTitle).text();
  titleCollecting = false;

  for (const selector of config.contentSelectors) {
    let buf = "";
    let inside = false;

    const rewriter = new HTMLRewriter()
      .on(selector, {
        element() {
          if (!inside) {
            inside = true;
          }
        }
      })
      .on(`${selector} *`, {
        element(el) {
          if (!inside) return;
          for (const rm of config.removeSelectors) {
            if (matchesSimpleSelector(el, rm)) {
              el.remove();
              return;
            }
          }
          const tag = el.tagName.toLowerCase();
          if (["script", "style", "iframe", "noscript", "form", "input", "button"].includes(tag)) {
            el.remove();
            return;
          }
          let attrs = "";
          if (tag === "a") {
            const href = el.getAttribute("href");
            if (href) attrs += ` href="${escapeAttr(href)}"`;
          } else if (tag === "img") {
            const src = el.getAttribute("src");
            const alt = el.getAttribute("alt");
            if (src) attrs += ` src="${escapeAttr(src)}"`;
            if (alt) attrs += ` alt="${escapeAttr(alt)}"`;
          }
          buf += `<${tag}${attrs}>`;
          // HTMLRewriter throws if onEndTag() is called on a void element,
          // so gate registration by tag name. (update-010)
          if (!VOID_ELEMENTS.has(tag)) {
            el.onEndTag(() => {
              buf += `</${tag}>`;
            });
          }
        },
        text(t) {
          if (inside) buf += escapeText(t.text);
        }
      });

    const response = new Response(html);
    await rewriter.transform(response).text();

    if (buf && buf.trim().length > 200) {
      collected = buf;
      foundContainer = true;
      break;
    }
  }

  if (!foundContainer) {
    collected = "<p>本文の自動抽出に失敗しました。元記事リンクから読んでください。</p>";
  }

  return {
    title: title.trim(),
    content_html: collected,
  };
}

// HTML void elements (no end tag, self-closing). Used for tag-emission logic
// during HTMLRewriter content extraction. Calling onEndTag() on these throws
// in Cloudflare Workers HTMLRewriter, so we MUST gate registration by tag name.
const VOID_ELEMENTS = new Set([
  "area", "base", "br", "col", "embed", "hr", "img",
  "input", "link", "meta", "param", "source", "track", "wbr",
]);

function matchesSimpleSelector(el, selector) {
  if (selector.startsWith(".")) {
    const cls = selector.slice(1);
    const elClass = el.getAttribute("class") || "";
    return elClass.split(/\s+/).includes(cls);
  }
  if (selector.startsWith("#")) {
    return el.getAttribute("id") === selector.slice(1);
  }
  return el.tagName.toLowerCase() === selector.toLowerCase();
}

function escapeAttr(s) {
  return String(s).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
}

function escapeText(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// =====================================================================
// /article: 記事フェッチ + 本文抽出 + KV キャッシュ
// =====================================================================

async function handleArticle(request, env, origin) {
  const url = new URL(request.url);
  const target = url.searchParams.get("url");
  if (!target) {
    return jsonResponse({ error: "url parameter required" }, 400, origin);
  }

  let parsed;
  try {
    parsed = new URL(target);
  } catch {
    return jsonResponse({ error: "invalid url" }, 400, origin);
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    return jsonResponse({ error: "invalid scheme" }, 400, origin);
  }

  const cacheKey = `article:${await urlHash(target)}`;

  const cached = await env.STATE.get(cacheKey, "json");
  if (cached && cached.content_html) {
    return jsonResponse({
      ...cached,
      cache_hit: true,
    }, 200, origin);
  }

  let html;
  try {
    const r = await fetch(target, {
      headers: {
        "User-Agent": FETCH_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
      },
      cf: { cacheTtl: 300 },
    });
    if (!r.ok) {
      return jsonResponse({ error: `fetch failed: ${r.status}` }, 502, origin);
    }
    html = await r.text();
  } catch (e) {
    return jsonResponse({ error: `fetch error: ${e.message}` }, 502, origin);
  }

  let extracted;
  try {
    extracted = await extractContent(html, target);
  } catch (e) {
    return jsonResponse({ error: `extract error: ${e.message}` }, 500, origin);
  }

  const result = {
    url: target,
    title: extracted.title,
    content_html: extracted.content_html,
    fetched_at: new Date().toISOString(),
    cache_hit: false,
  };

  try {
    await env.STATE.put(cacheKey, JSON.stringify(result), {
      expirationTtl: ARTICLE_CACHE_TTL_SECONDS,
    });
  } catch {}

  return jsonResponse(result, 200, origin);
}

// =====================================================================
// /fetch: 任意 URL の生 HTML プロキシ取得 (update-009)
// =====================================================================

/**
 * 任意 URL を Cloudflare 網経由で取得し、生 HTML を JSON で返す。
 * 用途: Python adapter が Actions 環境から WAF で弾かれるサイト
 * (楽待 rakumachi.jp 等)を取得するためのプロキシ。
 *
 * 認証: SYNC_SECRET(共通の Bearer)
 *
 * レスポンス形式:
 *   成功: 200 { url, status, html, content_type, fetched_at }
 *   origin が 4xx/5xx: 200 { url, status, error, body_snippet, fetched_at }
 *     ↑ Worker 自体は成功している(payload で upstream の失敗を伝える)
 *   Worker から origin に到達不可: 502 { url, error, fetched_at }
 *
 * ノート:
 *   - キャッシュは付けない(listing は更新頻度が高く、cache stale を避ける)
 *   - body サイズの上限はかけない(現状)。将来必要なら調整。
 */
async function handleFetch(request, env, origin) {
  const url = new URL(request.url);
  const target = url.searchParams.get("url");
  if (!target) {
    return jsonResponse({ error: "url parameter required" }, 400, origin);
  }

  let parsed;
  try {
    parsed = new URL(target);
  } catch {
    return jsonResponse({ error: "invalid url" }, 400, origin);
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    return jsonResponse({ error: "invalid scheme" }, 400, origin);
  }

  const fetchedAt = new Date().toISOString();
  let r;
  try {
    r = await fetch(target, {
      headers: PROXY_FETCH_HEADERS,
      redirect: "follow",
    });
  } catch (e) {
    return jsonResponse({
      url: target,
      error: `fetch error: ${e.message}`,
      fetched_at: fetchedAt,
    }, 502, origin);
  }

  let body;
  try {
    body = await r.text();
  } catch (e) {
    return jsonResponse({
      url: target,
      status: r.status,
      error: `read error: ${e.message}`,
      fetched_at: fetchedAt,
    }, 502, origin);
  }

  const result = {
    url: target,
    status: r.status,
    content_type: r.headers.get("content-type") || "",
    fetched_at: fetchedAt,
  };

  if (r.status >= 200 && r.status < 400) {
    result.html = body;
  } else {
    // upstream が 4xx/5xx の場合: Worker は健全なので 200 を返し、
    // payload の status / error で client 側に判断材料を与える
    result.error = `upstream HTTP ${r.status}`;
    result.body_snippet = body.slice(0, 500);
  }

  return jsonResponse(result, 200, origin);
}

// =====================================================================
// メインルーティング
// =====================================================================

export default {
  async fetch(request, env) {
    const origin = request.headers.get("Origin") || "";

    if (request.method === "OPTIONS") {
      return new Response(null, { headers: corsHeaders(origin) });
    }

    if (!checkAuth(request, env)) {
      return jsonResponse({ error: "unauthorized" }, 401, origin);
    }

    const url = new URL(request.url);

    if (request.method === "GET" && url.pathname === "/state") {
      const data = (await env.STATE.get(STATE_KEY, "json")) || { read: {}, fav: {} };
      return jsonResponse(data, 200, origin);
    }

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

    if (request.method === "GET" && url.pathname === "/article") {
      return handleArticle(request, env, origin);
    }

    if (request.method === "GET" && url.pathname === "/fetch") {
      return handleFetch(request, env, origin);
    }

    if (request.method === "GET" && url.pathname === "/ping") {
      return jsonResponse({ ok: true, ts: Date.now() }, 200, origin);
    }

    return jsonResponse({ error: "not found" }, 404, origin);
  },
};
