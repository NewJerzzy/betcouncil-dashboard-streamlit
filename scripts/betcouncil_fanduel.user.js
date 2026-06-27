// ==UserScript==
// @name         BetCouncil — FanDuel Token Harvester
// @namespace    https://github.com/NewJerzzy/betcouncil-dashboard-streamlit
// @version      1.2
// @description  Intercepts FanDuel PerimeterX token and pushes to BetCouncil Gist
// @author       BetCouncil
// @match        https://sportsbook.fanduel.com/*
// @grant        GM_xmlhttpRequest
// @grant        unsafeWindow
// @connect      api.github.com
// @run-at       document-start
// ==/UserScript==

(function() {
    'use strict';

    // ── CONFIG ─────────────────────────────────────────────────────────────
    const GIST_TOKEN = 'YOUR_GIST_TOKEN_HERE';
    const GIST_ID    = '7e52e1c2c2054847c7c4663a157386c5';
    // ──────────────────────────────────────────────────────────────────────

    const _window = (typeof unsafeWindow !== 'undefined') ? unsafeWindow : window;

    let lastPush = 0;

    function pushToGist(pxToken, authToken) {
        const now = Date.now();
        if (now - lastPush < 60000) return;
        lastPush = now;
        GM_xmlhttpRequest({
            method: 'PATCH',
            url: 'https://api.github.com/gists/' + GIST_ID,
            headers: {
                'Authorization': 'token ' + GIST_TOKEN,
                'Content-Type':  'application/json',
                'Accept':        'application/vnd.github.v3+json',
            },
            data: JSON.stringify({
                files: {
                    'betcouncil_fanduel_tokens.json': {
                        content: JSON.stringify({
                            px_token:    pxToken,
                            auth_token:  authToken || '',
                            captured_at: new Date().toISOString(),
                        }, null, 2)
                    }
                }
            }),
            onload:  function(r) { console.log('[BetCouncil] FanDuel token pushed HTTP ' + r.status); },
            onerror: function(e) { console.error('[BetCouncil] Gist push failed', e); },
        });
    }

    const origOpen      = _window.XMLHttpRequest.prototype.open;
    const origSetHeader = _window.XMLHttpRequest.prototype.setRequestHeader;
    const origSend      = _window.XMLHttpRequest.prototype.send;

    _window.XMLHttpRequest.prototype.open = function(method, url) {
        this._bc_url     = url;
        this._bc_headers = {};
        return origOpen.apply(this, arguments);
    };

    _window.XMLHttpRequest.prototype.setRequestHeader = function(name, value) {
        if (this._bc_headers) this._bc_headers[name.toLowerCase()] = value;
        return origSetHeader.apply(this, arguments);
    };

    _window.XMLHttpRequest.prototype.send = function() {
        if (this._bc_url && this._bc_url.includes('fanduel.com')) {
            const h  = this._bc_headers || {};
            const px = h['x-px-context'] || h['x-px-authorization'] || '';
            const auth = h['authorization'] || '';
            if (px) {
                console.log('[BetCouncil] Captured FanDuel PX token');
                pushToGist(px, auth);
            }
        }
        return origSend.apply(this, arguments);
    };

    const origFetch = _window.fetch;
    _window.fetch = function(input, init) {
        const url = typeof input === 'string' ? input : (input && input.url) || '';
        if (url.includes('fanduel.com') && init && init.headers) {
            const h = init.headers;
            let px = '', auth = '';
            if (h && typeof h.get === 'function') {
                px   = h.get('x-px-context') || h.get('x-px-authorization') || '';
                auth = h.get('authorization') || '';
            } else if (h && typeof h === 'object') {
                const lh = {};
                Object.keys(h).forEach(function(k) { lh[k.toLowerCase()] = h[k]; });
                px   = lh['x-px-context'] || lh['x-px-authorization'] || '';
                auth = lh['authorization'] || '';
            }
            if (px) {
                console.log('[BetCouncil] Captured FanDuel PX token (fetch)');
                pushToGist(px, auth);
            }
        }
        return origFetch.apply(_window, arguments);
    };

    console.log('[BetCouncil] FanDuel token harvester v1.2 active');
})();
