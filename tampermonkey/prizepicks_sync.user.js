// ==UserScript==
// @name         BetCouncil — PrizePicks Props Sync
// @namespace    https://betcouncil.streamlit.app
// @version      1.0
// @description  Intercepts PrizePicks API responses and pushes props to GitHub Gist for BetCouncil dashboard
// @author       BetCouncil
// @match        https://app.prizepicks.com/*
// @match        https://*.prizepicks.com/*
// @grant        GM_xmlhttpRequest
// @connect      api.github.com
// @connect      raw.githubusercontent.com
// @run-at       document-start
// ==/UserScript==

(function () {
  'use strict';

  // ── CONFIG — fill in your token ───────────────────────────────────────────
  const GIST_TOKEN = 'REPLACE_WITH_YOUR_GIST_PAT';  // github.com/settings/tokens (gist scope)
  const GIST_ID    = '7e52e1c2c2054847c7c4663a157386c5';
  const PUSH_INTERVAL_MS = 15 * 60 * 1000;  // push at most every 15 min per sport
  // ─────────────────────────────────────────────────────────────────────────

  const LEAGUE_MAP = {4:'NBA',5:'MLB',3:'NHL',7:'NFL',8:'WNBA',6:'UFC',11:'Golf',12:'Tennis',2:'Soccer'};
  const _lastPush = {};

  function detectSport(url) {
    const m = url.match(/league_id=(\d+)/);
    return m ? (LEAGUE_MAP[parseInt(m[1])] || 'UNKNOWN') : 'UNKNOWN';
  }

  function pushToGist(sport, data) {
    if (!GIST_TOKEN || GIST_TOKEN === 'REPLACE_WITH_YOUR_GIST_PAT') return;
    const now = Date.now();
    if (_lastPush[sport] && now - _lastPush[sport] < PUSH_INTERVAL_MS) return;
    _lastPush[sport] = now;

    const filename = `betcouncil_prizepicks_${sport}.json`;
    const payload = JSON.stringify({
      data: data,
      sport: sport,
      timestamp: new Date().toISOString(),
      source: 'prizepicks_tampermonkey'
    });

    GM_xmlhttpRequest({
      method: 'PATCH',
      url: `https://api.github.com/gists/${GIST_ID}`,
      headers: {
        'Authorization': `token ${GIST_TOKEN}`,
        'Content-Type':  'application/json',
        'Accept':        'application/vnd.github.v3+json'
      },
      data: JSON.stringify({ files: { [filename]: { content: payload } } }),
      onload: r => console.log(`[BetCouncil PP] ${sport} pushed (${r.status}) — ${(data.data||data).length||'?'} props`),
      onerror: e => console.warn('[BetCouncil PP] Gist push failed', e)
    });
  }

  // ── Intercept XMLHttpRequest ──────────────────────────────────────────────
  const _XHRopen = XMLHttpRequest.prototype.open;
  const _XHRsend = XMLHttpRequest.prototype.send;

  XMLHttpRequest.prototype.open = function (method, url, ...args) {
    this._bc_url = url;
    return _XHRopen.apply(this, [method, url, ...args]);
  };

  XMLHttpRequest.prototype.send = function (...args) {
    if (this._bc_url && this._bc_url.includes('prizepicks.com/projections')) {
      const url   = this._bc_url;
      const sport = detectSport(url);
      this.addEventListener('load', function () {
        try {
          const json = JSON.parse(this.responseText);
          if (json && (json.data || json.included)) {
            console.log(`[BetCouncil PP] XHR captured ${sport} projections`);
            pushToGist(sport, json);
          }
        } catch (e) {}
      });
    }
    return _XHRsend.apply(this, args);
  };

  // ── Intercept fetch() ─────────────────────────────────────────────────────
  const _origFetch = window.fetch;
  window.fetch = function (input, init) {
    const url = (typeof input === 'string') ? input : (input.url || '');
    return _origFetch.apply(this, [input, init]).then(resp => {
      if (url.includes('prizepicks.com/projections')) {
        const sport = detectSport(url);
        resp.clone().json().then(json => {
          if (json && (json.data || json.included)) {
            console.log(`[BetCouncil PP] fetch captured ${sport} projections`);
            pushToGist(sport, json);
          }
        }).catch(() => {});
      }
      return resp;
    });
  };

  // ── Proactive fetch on load — pull all active sports ─────────────────────
  function fetchAllSports() {
    const leagues = [4, 5, 3, 8];  // NBA, MLB, NHL, WNBA — add more as needed
    leagues.forEach(lid => {
      const sport = LEAGUE_MAP[lid] || 'UNK';
      fetch(`https://api.prizepicks.com/projections?league_id=${lid}&per_page=250&single_stat=true`)
        .then(r => r.json())
        .then(json => {
          if (json && json.data && json.data.length > 0) {
            console.log(`[BetCouncil PP] proactive fetch ${sport}: ${json.data.length} props`);
            pushToGist(sport, json);
          }
        })
        .catch(() => {});
    });
  }

  // Fetch on page load and then every 30 minutes
  window.addEventListener('load', () => { setTimeout(fetchAllSports, 3000); });
  setInterval(fetchAllSports, 30 * 60 * 1000);

  console.log('[BetCouncil] PrizePicks sync script loaded ✅');
})();
