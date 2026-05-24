// update-022-correct-token-key: Token activation via URL fragment + legacy migration.
  // Usage: https://kk-reader.pages.dev/#token=<TOKEN>
  // Fragment (#) is used instead of query (?) so the token never appears in
  // server logs, CDN access logs, or Referer headers. After capture, we strip
  // the token from the address bar via history.replaceState.
  // Writes to kkreader.syncToken (the key sync.js actually reads).
  (function () {
    try {
      var KEY = "kkreader.syncToken";
      var LEGACY = "kk-sync-token";
      // Migrate any value left in the legacy key (introduced briefly by
      // update-020) into the correct key, then remove the legacy entry.
      var legacy = localStorage.getItem(LEGACY);
      if (legacy) {
        if (!localStorage.getItem(KEY)) {
          localStorage.setItem(KEY, legacy);
        }
        localStorage.removeItem(LEGACY);
      }
      var hash = window.location.hash || "";
      var m = hash.match(/(?:^#|&)token=([^&]+)/);
      if (!m) return;
      var token = decodeURIComponent(m[1]);
      if (token && token.length >= 16) {
        localStorage.setItem(KEY, token);
      }
      var rest = hash
        .replace(/(?:^#|&)token=[^&]*/, "")
        .replace(/^#?&/, "#")
        .replace(/^#$/, "");
      var cleanUrl =
        window.location.pathname + window.location.search + rest;
      window.history.replaceState(null, "", cleanUrl);
    } catch (e) {
      // Silent fail; let the app continue normal load.
    }
  })();
