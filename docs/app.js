/* ========================================
   kk reader — frontend logic
   2026-05-06: ソース別フィルタ + モバイル対応
   ======================================== */

const STORAGE = {
  read: "kkreader.read",
  favs: "kkreader.favs",
  settings: "kkreader.settings",
  expanded: "kkreader.expandedCategories",
};

const PAGE_SIZE = 100;

// ---- State ----
const state = {
  feeds: [],
  feedsById: {},
  feedsByCategory: {},
  categories: [],
  articles: [],
  read: new Set(),
  favs: new Set(),
  expandedCategories: new Set(),
  filters: {
    unreadOnly: true,
    favOnly: false,
    category: "__all",   // "__all", "__fav", or category name
    feedId: null,        // 特定フィードのみ
    search: "",
  },
  visible: [],
  rendered: 0,
  selectedId: null,
  meta: {},
};

// ---- Persistence ----
function loadFromStorage() {
  try {
    state.read = new Set(JSON.parse(localStorage.getItem(STORAGE.read) || "[]"));
  } catch { state.read = new Set(); }
  try {
    state.favs = new Set(JSON.parse(localStorage.getItem(STORAGE.favs) || "[]"));
  } catch { state.favs = new Set(); }
  try {
    state.expandedCategories = new Set(JSON.parse(localStorage.getItem(STORAGE.expanded) || "[]"));
  } catch { state.expandedCategories = new Set(); }
  try {
    const s = JSON.parse(localStorage.getItem(STORAGE.settings) || "{}");
    if (typeof s.unreadOnly === "boolean") state.filters.unreadOnly = s.unreadOnly;
    if (typeof s.favOnly === "boolean") state.filters.favOnly = s.favOnly;
    if (s.theme) document.body.dataset.theme = s.theme;
  } catch {}
}

function saveRead() { localStorage.setItem(STORAGE.read, JSON.stringify([...state.read])); }
function saveFavs() { localStorage.setItem(STORAGE.favs, JSON.stringify([...state.favs])); }
function saveExpanded() {
  localStorage.setItem(STORAGE.expanded, JSON.stringify([...state.expandedCategories]));
}
function saveSettings() {
  localStorage.setItem(STORAGE.settings, JSON.stringify({
    unreadOnly: state.filters.unreadOnly,
    favOnly: state.filters.favOnly,
    theme: document.body.dataset.theme,
  }));
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
    state.feedsByCategory = {};
    for (const f of state.feeds) {
      const c = f.category || "未分類";
      (state.feedsByCategory[c] ||= []).push(f);
    }
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
    status.textContent = "読込エラー";
    document.getElementById("list-empty").textContent =
      "データの読み込みに失敗しました。GitHub Actions が一度実行されているか確認してください。";
    console.error(e);
    return false;
  }
}

// ---- Filtering ----
function applyFilters() {
  const { unreadOnly, favOnly, category, feedId, search } = state.filters;
  const q = search.trim().toLowerCase();
  const isFavView = favOnly || category === "__fav";

  state.visible = state.articles.filter(a => {
    // 未読フィルタ
    if (unreadOnly && state.read.has(a.id)) return false;

    // フィードレベル(優先)
    if (feedId) {
      if (a.feed_id !== feedId) return false;
    } else {
      // カテゴリレベル
      if (category && category !== "__all" && category !== "__fav") {
        if (a.category !== category) return false;
      }
    }

    // お気に入り(全レベルに重ねがけ)
    if (isFavView && !state.favs.has(a.id)) return false;

    // 検索
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
    const diffMs = new Date() - d;
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
  const catTpl = document.getElementById("tpl-cat-row");
  const feedTpl = document.getElementById("tpl-feed-row");

  // 未読数集計(カテゴリ別、フィード別)
  const unreadByCat = {};
  const unreadByFeed = {};
  let totalUnread = 0;
  for (const a of state.articles) {
    if (state.read.has(a.id)) continue;
    totalUnread++;
    unreadByCat[a.category] = (unreadByCat[a.category] || 0) + 1;
    unreadByFeed[a.feed_id] = (unreadByFeed[a.feed_id] || 0) + 1;
  }
  document.getElementById("count-all").textContent = totalUnread;
  document.getElementById("count-fav").textContent = state.favs.size;

  // カテゴリ並び順
  const orderHint = ["金融・経済・投資", "不動産", "ブログ", "Fx", "未分類"];
  const allCats = state.categories.length ? state.categories : Object.keys(unreadByCat);
  const sorted = [...allCats].sort((a, b) => {
    const ai = orderHint.indexOf(a), bi = orderHint.indexOf(b);
    if (ai !== -1 && bi !== -1) return ai - bi;
    if (ai !== -1) return -1;
    if (bi !== -1) return 1;
    return (unreadByCat[b] || 0) - (unreadByCat[a] || 0);
  });

  for (const cat of sorted) {
    // カテゴリ行
    const node = catTpl.content.cloneNode(true);
    const btn = node.querySelector(".cat-row");
    btn.dataset.cat = cat;
    const isExpanded = state.expandedCategories.has(cat);
    btn.dataset.expanded = isExpanded ? "true" : "false";

    btn.querySelector(".cat-caret").textContent = "▶";
    btn.querySelector(".cat-name").textContent = cat;
    btn.querySelector(".cat-count").textContent = unreadByCat[cat] || 0;

    if (state.filters.category === cat && !state.filters.feedId) {
      btn.dataset.active = "true";
    }

    btn.addEventListener("click", (e) => {
      // 展開トグル + カテゴリフィルタ適用
      const wasExpanded = state.expandedCategories.has(cat);
      const isCurrentCat = state.filters.category === cat && !state.filters.feedId;

      if (isCurrentCat && wasExpanded) {
        // 既に選択済みかつ展開済み → 折り畳む(フィルタは維持)
        state.expandedCategories.delete(cat);
      } else {
        // それ以外 → 展開して選択
        state.expandedCategories.add(cat);
        selectCategory(cat);
      }
      saveExpanded();
      renderCategoryList();
    });

    list.appendChild(node);

    // 展開されている場合、フィード一覧を出す
    if (isExpanded) {
      const feedListWrap = document.createElement("div");
      feedListWrap.className = "feed-list";

      const feeds = (state.feedsByCategory[cat] || []).slice().sort((a, b) =>
        (unreadByFeed[b.id] || 0) - (unreadByFeed[a.id] || 0) ||
        a.title.localeCompare(b.title, "ja")
      );

      for (const f of feeds) {
        const fnode = feedTpl.content.cloneNode(true);
        const fbtn = fnode.querySelector(".feed-row");
        fbtn.dataset.feedId = f.id;
        if (state.filters.feedId === f.id) {
          fbtn.dataset.active = "true";
        }
        if (!f.active) {
          fbtn.dataset.inactive = "true";
          fbtn.title = "無効化されたフィード(取得対象外)";
        }
        fbtn.querySelector(".feed-name").textContent = f.title;
        fbtn.querySelector(".feed-count").textContent = unreadByFeed[f.id] || 0;
        fbtn.addEventListener("click", () => selectFeed(f.id));
        feedListWrap.appendChild(fnode);
      }
      list.appendChild(feedListWrap);
    }
  }

  // top rows のアクティブ状態
  document.querySelectorAll('.top-row').forEach(el => {
    el.dataset.active = (el.dataset.cat === state.filters.category && !state.filters.feedId)
      ? "true" : "false";
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
  const content = document.getElementById("detail-content");
  const mobileTitle = document.getElementById("detail-mobile-title");
  detail.classList.add("show");

  const a = state.articles.find(x => x.id === id);
  if (!a) {
    content.innerHTML = '<div class="detail-empty">記事が見つかりません</div>';
    if (mobileTitle) mobileTitle.textContent = "";
    return;
  }

  if (mobileTitle) mobileTitle.textContent = a.feed_title;

  const isFav = state.favs.has(id);
  const isRead = state.read.has(id);
  const dateStr = a.published
    ? new Date(a.published).toLocaleString("ja-JP")
    : "公開日不明";

  content.innerHTML = `
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

  // モバイルでは詳細表示時に詳細スクロール位置を上に戻す
  content.scrollTop = 0;
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
  state.filters.feedId = null;
  applyFilters();
  renderCategoryList();
  renderArticleList();
  closeSidebarOnMobile();
}

function selectFeed(feedId) {
  state.filters.feedId = feedId;
  // カテゴリも同期(視覚的にフィードが属するカテゴリを選択状態にする)
  const feed = state.feedsById[feedId];
  if (feed) {
    state.filters.category = feed.category;
  }
  applyFilters();
  renderCategoryList();
  renderArticleList();
  closeSidebarOnMobile();
}

function selectArticle(id) {
  state.selectedId = id;
  if (!state.read.has(id)) {
    state.read.add(id);
    saveRead();
  }
  document.querySelectorAll(".row").forEach(row => {
    row.dataset.selected = row.dataset.id === id ? "true" : "false";
    if (row.dataset.id === id) row.dataset.read = "true";
  });
  renderArticleDetail(id);
  updateAllCounts();
}

function toggleRead(id) {
  if (state.read.has(id)) state.read.delete(id);
  else state.read.add(id);
  saveRead();
  const row = document.querySelector(`.row[data-id="${id}"]`);
  if (row) row.dataset.read = state.read.has(id) ? "true" : "false";
  updateAllCounts();
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
  renderCategoryList();
}

function closeSidebarOnMobile() {
  if (window.innerWidth <= 720) {
    document.getElementById("sidebar").classList.remove("show");
    document.getElementById("sidebar-backdrop").classList.remove("show");
  }
}

function openSidebar() {
  document.getElementById("sidebar").classList.add("show");
  document.getElementById("sidebar-backdrop").classList.add("show");
}

function closeSidebar() {
  document.getElementById("sidebar").classList.remove("show");
  document.getElementById("sidebar-backdrop").classList.remove("show");
}

function toggleSidebar() {
  const sb = document.getElementById("sidebar");
  if (sb.classList.contains("show")) closeSidebar();
  else openSidebar();
}

function backToList() {
  document.getElementById("article-detail").classList.remove("show");
}

// ---- Keyboard ----
function moveSelection(delta) {
  const idx = state.visible.findIndex(a => a.id === state.selectedId);
  let next = idx + delta;
  if (next < 0) next = 0;
  if (next >= state.visible.length) next = state.visible.length - 1;
  if (next === idx || next < 0) return;
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
    case "u": e.preventDefault(); toggleUnreadFilter(); break;
    case "/": e.preventDefault(); document.getElementById("search").focus(); break;
    case "Escape":
      backToList();
      closeSidebar();
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
  document.getElementById("toggle-sidebar").addEventListener("click", toggleSidebar);
  document.getElementById("sidebar-backdrop").addEventListener("click", closeSidebar);

  const backBtn = document.getElementById("back-to-list");
  if (backBtn) backBtn.addEventListener("click", backToList);

  document.getElementById("search").addEventListener("input", (e) => {
    state.filters.search = e.target.value;
    applyFilters();
    renderArticleList();
  });

  document.querySelectorAll('.top-row').forEach(el => {
    el.addEventListener("click", () => selectCategory(el.dataset.cat));
  });

  document.addEventListener("keydown", handleKeydown);

  // モバイル: ウィンドウリサイズ時にサイドバーをリセット
  window.addEventListener("resize", () => {
    if (window.innerWidth > 720) closeSidebar();
  });

  const ok = await loadData();
  if (!ok) return;
  applyFilters();
  renderCategoryList();
  renderArticleList();
}

init();
