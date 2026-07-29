// ==UserScript==
// @name         DK Pick6 Player Name Harvester
// @namespace    betcouncil
// @version      1.1
// @description  Intercepts DraftKings Pick6 API responses to harvest dkId→name mappings and push them to a GitHub Gist for the BetCouncil dashboard.
// @match        https://pick6.draftkings.com/*
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_xmlhttpRequest
// @grant        GM_registerMenuCommand
// @connect      api.github.com
// @connect      raw.githubusercontent.com
// @run-at       document-start
// ==/UserScript==

(function () {
  'use strict';

  const GIST_ID   = '7e52e1c2c2054847c7c4663a157386c5';
  const GIST_FILE = 'betcouncil_player_names.json';
  // Minimum number of unique players before we push to the gist.
  const MIN_PUSH  = 10;

  // ── Token management ────────────────────────────────────────────────────────
  function getToken() {
    let t = GM_getValue('gist_token', '');
    if (!t) {
      t = prompt(
        'BetCouncil Pick6 Harvester\n\n' +
        'Enter your GitHub Gist token (needs "gist" scope).\n' +
        'This is stored locally in Tampermonkey — never sent anywhere except GitHub.',
        ''
      );
      if (t) GM_setValue('gist_token', t.trim());
    }
    return t ? t.trim() : null;
  }

  GM_registerMenuCommand('🔑 Update Gist token', () => {
    GM_setValue('gist_token', '');
    getToken();
  });
  GM_registerMenuCommand('📤 Force push names now', pushNames);

  // ── Accumulated name map ─────────────────────────────────────────────────────
  const nameMap = {};  // dkId (number) → displayName (string)
  let lastPushSize = 0;

  function addNames(data) {
    let added = 0;
    // Walk any array in the response tree, however nested
    function walk(obj) {
      if (!obj || typeof obj !== 'object') return;
      if (Array.isArray(obj)) { obj.forEach(walk); return; }
      // Check if this object has a dkId-like field and a name-like field
      const id   = obj.dkId ?? obj.playerId ?? obj.draftableId ?? obj.entityId;
      const name = obj.displayName ?? obj.fullName ?? obj.name ?? obj.shortName ??
                   ((obj.firstName || obj.lastName)
                     ? `${obj.firstName || ''} ${obj.lastName || ''}`.trim()
                     : null);
      if (id && name && typeof name === 'string' && name.length > 1 && !/^dkId_/.test(name)) {
        const numId = Number(id);
        if (!nameMap[numId]) {
          nameMap[numId] = name;
          added++;
        }
      }
      Object.values(obj).forEach(walk);
    }
    walk(data);
    if (added > 0) {
      console.log(`[Pick6 Harvester] +${added} names (total ${Object.keys(nameMap).length})`);
      maybeAutoPush();
    }
  }

  function maybeAutoPush() {
    const size = Object.keys(nameMap).length;
    if (size >= MIN_PUSH && size > lastPushSize) pushNames();
  }

  // ── Gist push ────────────────────────────────────────────────────────────────
  function pushNames() {
    const token = getToken();
    if (!token) { console.warn('[Pick6 Harvester] No token — skipping push'); return; }
    const count = Object.keys(nameMap).length;
    if (count === 0) { console.log('[Pick6 Harvester] Nothing to push yet'); return; }

    const payload = JSON.stringify({
      updated_at: new Date().toISOString(),
      count,
      names: nameMap,
    });

    GM_xmlhttpRequest({
      method: 'PATCH',
      url: `https://api.github.com/gists/${GIST_ID}`,
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'application/vnd.github+json',
        'Content-Type': 'application/json',
      },
      data: JSON.stringify({ files: { [GIST_FILE]: { content: payload } } }),
      onload(res) {
        if (res.status === 200 || res.status === 201) {
          console.log(`[Pick6 Harvester] ✅ Pushed ${count} player names to gist`);
          lastPushSize = count;
          showToast(`✅ ${count} Pick6 player names synced to BetCouncil`);
        } else {
          console.error('[Pick6 Harvester] Push failed:', res.status, res.responseText.slice(0, 200));
        }
      },
      onerror(err) {
        console.error('[Pick6 Harvester] Network error:', err);
      },
    });
  }

  // ── Intercept fetch ──────────────────────────────────────────────────────────
  const _fetch = window.fetch;
  window.fetch = async function (...args) {
    const res = await _fetch.apply(this, args);
    const url = typeof args[0] === 'string' ? args[0] : (args[0].url || '');
    if (url.includes('draftkings.com')) {
      try {
        const clone = res.clone();
        clone.json().then(addNames).catch(() => {});
      } catch (_) {}
    }
    return res;
  };

  // ── Intercept XMLHttpRequest ─────────────────────────────────────────────────
  const _open = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (method, url, ...rest) {
    this._url = url;
    return _open.call(this, method, url, ...rest);
  };
  const _send = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.send = function (...args) {
    this.addEventListener('load', function () {
      if (this._url && this._url.includes('draftkings.com') &&
          this.responseType !== 'blob' && this.responseType !== 'arraybuffer') {
        try {
          const data = JSON.parse(this.responseText);
          addNames(data);
        } catch (_) {}
      }
    });
    return _send.apply(this, args);
  };

  // ── Toast notification ───────────────────────────────────────────────────────
  function showToast(msg) {
    const d = document.createElement('div');
    d.textContent = msg;
    Object.assign(d.style, {
      position: 'fixed', bottom: '24px', right: '24px', zIndex: 999999,
      background: '#1a1a2e', color: '#00d4aa', padding: '12px 20px',
      borderRadius: '8px', fontFamily: 'sans-serif', fontSize: '14px',
      boxShadow: '0 4px 16px rgba(0,0,0,.5)', transition: 'opacity .4s',
    });
    document.body.appendChild(d);
    setTimeout(() => { d.style.opacity = '0'; setTimeout(() => d.remove(), 500); }, 4000);
  }

  console.log('[Pick6 Harvester] Active — intercepting DK API responses for player names');
})();
