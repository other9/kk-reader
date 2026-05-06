/* ========================================
   kk reader — frontend logic
   ======================================== */

const STORAGE = {
  read: "kkreader.read",
  favs: "kkreader.favs",
  settings: "kkreader.settings",
};

const PAGE_SIZE = 100;

// ---- State ----
const state = {
  feeds: [],
  feedsById: {},
  categories: [],
  articles: [],
  read: new Set(),
  favs: new Set(),
  filters: {
    unreadOnly: true,
    favOnly: false,
    category: "__all", // __all, __fav, or category name
    search: "",
  },
  visible: [],     // filtered articles (full)
  rendered: 0,     // number currently shown
  selectedId: null,
  meta: {},        // articles.json meta
};

// ---- Persistence ----
function loadFromStorage() {
  try {
    const r = JSON.parse(localStorage.getItem(STORAGE.read) || "[]");
    state.read = new Set(r);
  } catch { state.read = new Set(); }
  try {
    const f = JSON.parse(localStorage.getItem(STORAGE.favs) || "[]");
    state.favs = new Set(f);
  } catch { state.favs = new Set(); }
  try {
    const s = JSON.parse(localStorage.getItem(STORAGE.settings) || "{}");
    if (typeof s.unreadOnly === "boolean") state.filters.unreadOnly = s.unreadOnly;
    if (typeof s.favOnly === "boolean") state.filters.favOnly = s.favOnly;
    if (s.theme) document.body.dataset.theme = s.theme;
  } catch {}
}

function saveRead() {
  localStorage.setItem(STORAGE.read, JSON.stringify([...state.read]));
}
function saveFavs() {
  localStorage.setItem(STORAGE.favs, JSON.stringify([...state.favs]));
}
function saveSettings() {
  const s = {
    unreadOnly: state.filters.unreadOnly,
    favOnly: state.filters.favOnly,
    theme: document.body.dataset.theme,
  };
  localStorage.setItem(STORAGE.settings, JSON.stringify(s));
}

// ---- Data loading ----
async function loadData() {
  const status = document.getElementById("status");
  status.textContent = "loading…";
  try {
    const [feedsRes, articlesRes] = await Promise.all([
      fetch("data/feeds.json", { cache: "no-cache" }),
      fetch("data/articles.json", { cache: "no-cache" }),
    ]);
    if (!feedsRes.ok || !articlesRes.ok) throw new Error("fetch failed");
    const feedsData = await feedsRes.json();
    const articlesData = await articlesRes.json();
    state.feeds = feedsData.feeds || [];
    state.feedsById = Object.fromEntries(state.feeds.map(f => [f.id, f]));
    state.categories = feedsData.categories || [];
    state.articles = articlesData.articles || [];
    state.meta = {
      lastUpdated: articlesData.last_updated,
      stats: articlesData.stats || {},
    };
    status.textContent = `${state.articles.length} 件`;
    renderFetchStatus();
    return true;
  } catch (e) {
    status.textContent = "読み込みエラー";
    document.getElementById("list-empty").textContent =
      "データの読み込みに失敗しました。GitHub Actions が一度実行されているか確認してください。";
    console.error(e);
    return false;
  }
}

// ---- Filtering ----
function applyFilters() {
  const { unreadOnly, favOnly, category, search } = state.filters;
  const q = search.trim().toLowerCase();

  state.visible = state.articles.filter(a => {
    if (unreadOnly && state.read.has(a.id)) return false;
    if (favOnly && !state.favs.has(a.id)) return false;
    if (category === "__fav" && !state.favs.has(a.id)) return false;
    if (category && category !== "__all" && category !== "__fav" && a.category !== category) return false;
    if (q) {
      const hay = `${a.title} ${a.feed_title} ${a.category}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
  state.rendered = 0;
}

// ---- Rendering ----
function fmtDate(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    const now = new Date();
    const diffMs = now - d;
    const diffH = diffMs / 36e5;
    if (diffH < 1) return Math.max(1, Math.round(diffMs / 60000)) + "分前";
    if (diffH < 24) return Math.round(diffH) + "時間前";
    if (diffH < 24 * 7) return Math.round(diffH / 24) + "日前";
    return d.toLocaleDateString("ja-JP", { year: "2-digit", month: "2-digit", day: "2-digit" });
  } catch { return "—"; }
}

function renderCategoryList() {
  const list = document.getElementById("category-list");
  list.innerHTML = "";
  const tpl = document.getElementById("tpl-cat-row");

  // Count unread per category
  const unreadByCat = {};
  let totalUnread = 0;
  let favUnread = 0;
  for (const a of state.articles) {
    if (state.read.has(a.id)) continue;
    totalUnread++;
    unreadByCat[a.category] = (unreadByCat[a.category] || 0) + 1;
    if (state.favs.has(a.id)) favUnread++;
  }

  document.getElementById("count-all").textContent = totalUnread;
  // For favorites, show total favs count (read or unread)
  document.getElementById("count-fav").textContent = state.favs.size;

  // Sort: defined categories first (in OPML order), then others by count desc
  const orderHint = ["不動産", "金融・経済・投資", "ブログ", "Fx", "未分類"];
  const allCats = state.categories.length ? state.categories : Object.keys(unreadByCat);
  const sorted = [...allCats].sort((a, b) => {
    const ai = orderHint.indexOf(a);
    const bi = orderHint.indexOf(b);
    if (ai !== -1 && bi !== -1) return ai - bi;
    if (ai !== -1) return -1;
    if (bi !== -1) return 1;
    return (unreadByCat[b] || 0) - (unreadByCat[a] || 0);
  });

  for (const cat of sorted) {
    const node = tpl.content.cloneNode(true);
    const btn = node.querySelector(".cat-row");
    btn.dataset.cat = cat;
    btn.querySelector(".cat-name").textContent = cat;
    btn.querySelector(".cat-count").textContent = unreadByCat[cat] || 0;
    if (state.filters.category === cat) btn.dataset.active = "true";
    btn.addEventListener("click", () => selectCategory(cat));
    list.appendChild(node);
  }

  // Update top-level rows
  document.querySelectorAll('.sidebar-section .cat-row').forEach(el => {
    if (el.dataset.cat === state.filters.category) {
      el.dataset.active = "true";
    } else {
      el.dataset.active = "false";
    }
  });
}

function renderArticleList() {
  const list = document.getElementById("article-list");
  list.innerHTML = "";

  if (state.visible.length === 0) {
    const empty = document.createElement("div");
    empty.className = "list-empty";
    empty.textContent = state.filters.unreadOnly
      ? "未読の記事はありません"
      : "該当する記事がありません";
    list.appendChild(empty);
    return;
  }

  appendArticleRows();
}

function appendArticleRows() {
  const list = document.getElementById("article-list");
  const tpl = document.getElementById("tpl-article-row");
  const start = state.rendered;
  const end = Math.min(state.visible.length, start + PAGE_SIZE);

  // Remove existing load-more if present
  const existingMore = list.querySelector(".load-more-wrap");
  if (existingMore) existingMore.remove();

  for (let i = start; i < end; i++) {
    const a = state.visible[i];
    const node = tpl.content.cloneNode(true);
    const row = node.querySelector(".row");
    row.dataset.id = a.id;
    row.dataset.read = state.read.has(a.id) ? "true" : "false";
    row.dataset.fav = state.favs.has(a.id) ? "true" : "false";
    row.dataset.selected = state.selectedId === a.id ? "true" : "false";

    row.querySelector(".row-source").textContent = a.feed_title;
    row.querySelector(".row-cat").textContent = a.category;
    row.querySelector(".row-date").textContent = fmtDate(a.published || a.fetched);
    row.querySelector(".row-title").textContent = a.title;
    row.querySelector(".row-summary").textContent = a.summary || "";
    row.querySelector(".row-fav").textContent = state.favs.has(a.id) ? "★" : "☆";

    row.addEventListener("click", (e) => {
      if (e.target.classList.contains("row-fav")) {
        e.stopPropagation();
        toggleFav(a.id);
      } else if (e.target.classList.contains("row-read")) {
        e.stopPropagation();
        toggleRead(a.id);
      } else {
        selectArticle(a.id);
      }
    });

    list.appendChild(node);
  }

  state.rendered = end;

  if (state.rendered < state.visible.length) {
    const wrap = document.createElement("div");
    wrap.className = "load-more-wrap";
    const btn = document.createElement("button");
    btn.className = "load-more";
    btn.textContent = `さらに読み込む（残り ${state.visible.length - state.rendered} 件）`;
    btn.addEventListener("click", () => appendArticleRows());
    wrap.appendChild(btn);
    list.appendChild(wrap);
  }
}

function renderArticleDetail(id) {
  const detail = document.getElementById("article-detail");
  detail.classList.add("show");

  const a = state.articles.find(x => x.id === id);
  if (!a) {
    detail.innerHTML = '<div class="detail-empty">記事が見つかりません</div>';
    return;
  }

  const isFav = state.favs.has(id);
  const isRead = state.read.has(id);
  const dateStr = a.published
    ? new Date(a.published).toLocaleString("ja-JP")
    : "公開日不明";

  detail.innerHTML = `
    <div class="detail-meta">
      <span class="accent">${escapeHtml(a.feed_title)}</span> · ${escapeHtml(a.category)} · ${dateStr}
    </div>
    <h2 class="detail-title">${escapeHtml(a.title)}</h2>
    <div class="detail-source">
      <a href="${escapeAttr(a.url)}" target="_blank" rel="noopener noreferrer">元記事を開く ↗</a>
      ${a.author ? ` · ${escapeHtml(a.author)}` : ""}
    </div>
    <div class="detail-toolbar">
      <button id="btn-fav" data-active="${isFav}">${isFav ? "★ お気に入り" : "☆ お気に入り"}</button>
      <button id="btn-read">${isRead ? "未読に戻す" : "既読にする"}</button>
      <button id="btn-open">元記事を開く</button>
    </div>
    <div class="detail-body" id="detail-body"></div>
  `;

  const body = document.getElementById("detail-body");
  if (a.content_html) {
    body.innerHTML = a.content_html;
    // Force external links
    body.querySelectorAll("a").forEach(link => {
      link.target = "_blank";
      link.rel = "noopener noreferrer";
    });
  } else {
    body.innerHTML = `<p>${escapeHtml(a.summary || "本文プレビューがありません。")}</p>
      <p style="color:var(--ink-dim);font-style:italic;">完全な記事内容は元記事でご覧ください。</p>`;
  }

  document.getElementById("btn-fav").addEventListener("click", () => {
    toggleFav(id);
    renderArticleDetail(id);
  });
  document.getElementById("btn-read").addEventListener("click", () => {
    toggleRead(id);
    renderArticleDetail(id);
  });
  document.getElementById("btn-open").addEventListener("click", () => {
    window.open(a.url, "_blank", "noopener,noreferrer");
  });
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));
}
function escapeAttr(s) { return escapeHtml(s); }

function renderFetchStatus() {
  const el = document.getElementById("fetch-status");
  if (!state.meta.lastUpdated) {
    el.textContent = "未取得";
    return;
  }
  const d = new Date(state.meta.lastUpdated);
  const stats = state.meta.stats || {};
  const okCount = stats.feeds_success ?? "?";
  const failCount = stats.feeds_failed ?? "?";
  el.innerHTML = `
    <div>${d.toLocaleString("ja-JP")}</div>
    <div style="margin-top:4px">取得: ${okCount} / 失敗: ${failCount}</div>
  `;
}

// ---- Actions ----
function selectCategory(cat) {
  state.filters.category = cat;
  applyFilters();
  renderCategoryList();
  renderArticleList();
  // Mobile: close sidebar after selection
  document.getElementById("sidebar").classList.remove("show");
}

function selectArticle(id) {
  state.selectedId = id;
  // Mark read on view
  if (!state.read.has(id)) {
    state.read.add(id);
    saveRead();
  }
  // Update DOM
  document.querySelectorAll(".row").forEach(row => {
    row.dataset.selected = row.dataset.id === id ? "true" : "false";
    if (row.dataset.id === id) {
      row.dataset.read = "true";
    }
  });
  renderArticleDetail(id);
  updateAllCounts();
}

function toggleRead(id) {
  if (state.read.has(id)) state.read.delete(id);
  else state.read.add(id);
  saveRead();
  // Update row
  const row = document.querySelector(`.row[data-id="${id}"]`);
  if (row) row.dataset.read = state.read.has(id) ? "true" : "false";
  updateAllCounts();
  // If unreadOnly is on and we just marked read, it should disappear from list — but we keep it visible until next filter pass
}

function toggleFav(id) {
  if (state.favs.has(id)) state.favs.delete(id);
  else state.favs.add(id);
  saveFavs();
  const row = document.querySelector(`.row[data-id="${id}"]`);
  if (row) {
    row.dataset.fav = state.favs.has(id) ? "true" : "false";
    const btn = row.querySelector(".row-fav");
    if (btn) btn.textContent = state.favs.has(id) ? "★" : "☆";
  }
  updateAllCounts();
}

function markAllReadInView() {
  if (!confirm(`表示中の ${state.visible.length} 件をすべて既読にしますか？`)) return;
  for (const a of state.visible) state.read.add(a.id);
  saveRead();
  applyFilters();
  renderCategoryList();
  renderArticleList();
}

function updateAllCounts() {
  // Recompute and re-render category list (cheap; <50 categories)
  renderCategoryList();
}

// ---- Keyboard ----
function moveSelection(delta) {
  const idx = state.visible.findIndex(a => a.id === state.selectedId);
  let next = idx + delta;
  if (next < 0) next = 0;
  if (next >= state.visible.length) next = state.visible.length - 1;
  if (next === idx || next < 0) return;
  // Ensure rendered up to next
  while (state.rendered <= next && state.rendered < state.visible.length) {
    appendArticleRows();
  }
  const a = state.visible[next];
  if (a) {
    selectArticle(a.id);
    const el = document.querySelector(`.row[data-id="${a.id}"]`);
    if (el) el.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
}

function handleKeydown(e) {
  // Ignore when typing in input
  if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") {
    if (e.key === "Escape") e.target.blur();
    return;
  }
  if (e.metaKey || e.ctrlKey || e.altKey) return;

  switch (e.key) {
    case "j": e.preventDefault(); moveSelection(1); break;
    case "k": e.preventDefault(); moveSelection(-1); break;
    case "m":
      if (state.selectedId) { e.preventDefault(); toggleRead(state.selectedId); }
      break;
    case "M":
      if (e.shiftKey) { e.preventDefault(); markAllReadInView(); }
      break;
    case "f":
      if (state.selectedId) { e.preventDefault(); toggleFav(state.selectedId); }
      break;
    case "o":
      if (state.selectedId) {
        e.preventDefault();
        const a = state.articles.find(x => x.id === state.selectedId);
        if (a) window.open(a.url, "_blank", "noopener,noreferrer");
      }
      break;
    case "u":
      e.preventDefault();
      toggleUnreadFilter();
      break;
    case "/":
      e.preventDefault();
      document.getElementById("search").focus();
      break;
    case "Escape":
      document.getElementById("article-detail").classList.remove("show");
      break;
  }
}

function toggleUnreadFilter() {
  state.filters.unreadOnly = !state.filters.unreadOnly;
  document.getElementById("filter-unread").dataset.active = state.filters.unreadOnly;
  saveSettings();
  applyFilters();
  renderArticleList();
}

function toggleFavFilter() {
  state.filters.favOnly = !state.filters.favOnly;
  document.getElementById("filter-fav").dataset.active = state.filters.favOnly;
  saveSettings();
  applyFilters();
  renderArticleList();
}

function toggleTheme() {
  const cur = document.body.dataset.theme || "auto";
  const next = cur === "auto" ? "light" : cur === "light" ? "dark" : "auto";
  document.body.dataset.theme = next;
  saveSettings();
}

// ---- Init ----
async function init() {
  loadFromStorage();

  document.getElementById("filter-unread").dataset.active = state.filters.unreadOnly;
  document.getElementById("filter-fav").dataset.active = state.filters.favOnly;

  document.getElementById("filter-unread").addEventListener("click", toggleUnreadFilter);
  document.getElementById("filter-fav").addEventListener("click", toggleFavFilter);
  document.getElementById("mark-all-read").addEventListener("click", markAllReadInView);
  document.getElementById("theme-toggle").addEventListener("click", toggleTheme);
  document.getElementById("toggle-sidebar").addEventListener("click", () => {
    document.getElementById("sidebar").classList.toggle("show");
  });

  document.getElementById("search").addEventListener("input", (e) => {
    state.filters.search = e.target.value;
    applyFilters();
    renderArticleList();
  });

  // Top-level "all" and "fav" rows
  document.querySelectorAll('.sidebar-section .cat-row[data-cat="__all"]').forEach(el => {
    el.addEventListener("click", () => selectCategory("__all"));
  });
  document.querySelectorAll('.sidebar-section .cat-row[data-cat="__fav"]').forEach(el => {
    el.addEventListener("click", () => selectCategory("__fav"));
  });

  document.addEventListener("keydown", handleKeydown);

  const ok = await loadData();
  if (!ok) return;
  applyFilters();
  renderCategoryList();
  renderArticleList();
}

init();
