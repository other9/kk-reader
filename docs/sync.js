/* ========================================
   kk reader — 同期クライアント
   2026-05-06: Cloudflare Worker と localStorage の橋渡し
   ======================================== */

const SYNC_STORAGE = {
  token: "kkreader.syncToken",
  url: "kkreader.syncUrl",
  pendingDiff: "kkreader.pendingDiff",
  lastSync: "kkreader.lastSync",
};

const DEFAULT_SYNC_URL = "https://kk-sync.other9.workers.dev";
const FLUSH_DEBOUNCE_MS = 3000;

class SyncClient {
  constructor() {
    this.token = localStorage.getItem(SYNC_STORAGE.token) || "";
    this.url = localStorage.getItem(SYNC_STORAGE.url) || DEFAULT_SYNC_URL;
    this.pending = this._loadPending();
    this.flushTimer = null;
    this.lastError = null;
    this.lastSync = localStorage.getItem(SYNC_STORAGE.lastSync) || null;
    this.onMergeCallback = null;
    this.statusListeners = [];
  }

  get enabled() {
    return !!(this.token && this.url);
  }

  // ---- 設定 ----

  setToken(token) {
    this.token = (token || "").trim();
    if (this.token) localStorage.setItem(SYNC_STORAGE.token, this.token);
    else localStorage.removeItem(SYNC_STORAGE.token);
    this._notifyStatus();
  }

  setUrl(url) {
    this.url = (url || "").replace(/\/$/, "") || DEFAULT_SYNC_URL;
    if (this.url !== DEFAULT_SYNC_URL) {
      localStorage.setItem(SYNC_STORAGE.url, this.url);
    } else {
      localStorage.removeItem(SYNC_STORAGE.url);
    }
    this._notifyStatus();
  }

  // ---- 通信 ----

  async pull() {
    if (!this.enabled) return null;
    try {
      const resp = await fetch(`${this.url}/state`, {
        headers: { Authorization: `Bearer ${this.token}` },
      });
      if (!resp.ok) {
        this._setError(`取得失敗: HTTP ${resp.status}`);
        return null;
      }
      const data = await resp.json();
      this._setSuccess();
      return data;
    } catch (e) {
      this._setError(`接続エラー: ${e.message}`);
      return null;
    }
  }

  async pushDiff(diff) {
    if (!this.enabled) return null;
    if (!diff || (!diff.read?.length && !diff.fav?.length)) return null;
    try {
      const resp = await fetch(`${this.url}/state/diff`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${this.token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(diff),
      });
      if (!resp.ok) {
        this._setError(`送信失敗: HTTP ${resp.status}`);
        return null;
      }
      const data = await resp.json();
      this._setSuccess();
      return data.state;
    } catch (e) {
      this._setError(`接続エラー: ${e.message}`);
      return null;
    }
  }

  async testConnection() {
    if (!this.enabled) return { ok: false, error: "token または URL が未設定" };
    try {
      const resp = await fetch(`${this.url}/state`, {
        headers: { Authorization: `Bearer ${this.token}` },
      });
      if (resp.ok) return { ok: true };
      if (resp.status === 401) return { ok: false, error: "認証失敗(token が誤っているか、Worker と一致しない)" };
      return { ok: false, error: `HTTP ${resp.status}` };
    } catch (e) {
      return { ok: false, error: `接続エラー: ${e.message}` };
    }
  }

  // ---- 記事本文の on-demand 取得 ----

  async fetchArticle(articleUrl) {
    if (!this.enabled) {
      return { ok: false, error: "同期が無効です。設定画面でtokenを設定してください。" };
    }
    try {
      const u = new URL(`${this.url}/article`);
      u.searchParams.set("url", articleUrl);
      const resp = await fetch(u.toString(), {
        headers: { Authorization: `Bearer ${this.token}` },
      });
      if (!resp.ok) {
        let msg = `HTTP ${resp.status}`;
        try {
          const j = await resp.json();
          if (j.error) msg = j.error;
        } catch {}
        return { ok: false, error: msg };
      }
      const data = await resp.json();
      return { ok: true, data };
    } catch (e) {
      return { ok: false, error: `接続エラー: ${e.message}` };
    }
  }

  // ---- 差分キュー ----

  queueDiff(type, entry) {
    if (!this.enabled) return;
    if (!this.pending) this.pending = { read: [], fav: [] };
    if (!Array.isArray(this.pending[type])) this.pending[type] = [];
    // 同一IDの古いエントリを除去
    this.pending[type] = this.pending[type].filter((e) => e.id !== entry.id);
    this.pending[type].push(entry);
    this._savePending();
    this._scheduleFlush();
  }

  _scheduleFlush() {
    if (this.flushTimer) clearTimeout(this.flushTimer);
    this.flushTimer = setTimeout(() => this.flush(), FLUSH_DEBOUNCE_MS);
  }

  async flush() {
    this.flushTimer = null;
    if (!this.pending) return;
    if (!this.pending.read?.length && !this.pending.fav?.length) {
      this.pending = null;
      this._savePending();
      return;
    }
    const toSend = this.pending;
    this.pending = null;
    this._savePending();
    const result = await this.pushDiff(toSend);
    if (!result) {
      // 失敗時は再キュー
      this.pending = toSend;
      this._savePending();
    }
  }

  _loadPending() {
    try {
      return JSON.parse(localStorage.getItem(SYNC_STORAGE.pendingDiff) || "null");
    } catch {
      return null;
    }
  }

  _savePending() {
    if (this.pending && (this.pending.read?.length || this.pending.fav?.length)) {
      localStorage.setItem(SYNC_STORAGE.pendingDiff, JSON.stringify(this.pending));
    } else {
      localStorage.removeItem(SYNC_STORAGE.pendingDiff);
    }
  }

  // ---- 状態通知 ----

  _setSuccess() {
    this.lastError = null;
    this.lastSync = new Date().toISOString();
    localStorage.setItem(SYNC_STORAGE.lastSync, this.lastSync);
    this._notifyStatus();
  }

  _setError(msg) {
    this.lastError = msg;
    this._notifyStatus();
  }

  onStatus(listener) {
    this.statusListeners.push(listener);
  }

  _notifyStatus() {
    const status = {
      enabled: this.enabled,
      lastSync: this.lastSync,
      lastError: this.lastError,
      pendingCount:
        (this.pending?.read?.length || 0) + (this.pending?.fav?.length || 0),
    };
    this.statusListeners.forEach((cb) => {
      try {
        cb(status);
      } catch {}
    });
  }
}

// ---- URL からの token 取込 (マジックリンク方式) ----

function extractTokenFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const token = params.get("token");
  if (token) {
    localStorage.setItem(SYNC_STORAGE.token, token);
    params.delete("token");
    const newUrl =
      window.location.pathname +
      (params.toString() ? "?" + params.toString() : "") +
      window.location.hash;
    window.history.replaceState({}, "", newUrl);
    return token;
  }
  return null;
}

// グローバル(app.js から参照)
window.kkSync = {
  client: null,
  init() {
    extractTokenFromUrl();
    this.client = new SyncClient();
    return this.client;
  },
};
