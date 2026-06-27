// ==UserScript==
// @name         BetCouncil — Caesars Token Harvester
// @namespace    https://github.com/NewJerzzy/betcouncil-dashboard-streamlit
// @version      1.2
// @description  Intercepts Caesars sportsbook auth tokens and pushes them to BetCouncil Gist
// @author       BetCouncil
// @match        https://sportsbook.caesars.com/*
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

    // Use unsafeWindow to access the real page context in Edge/Chrome
    const _window = (typeof unsafeWindow !== 'undefined') ? unsafeWindow : window;

    let lastPush = 0;

    function pushToGist(bearer, wafToken) {
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
                    'betcouncil_caesars_tokens.json': {
                        content: JSON.stringify({
                            bearer_jwt:  bearer,
                            waf_token:   wafToken || '',
                            captured_at: new Date().toISOString(),
                        }, null, 2)
                    }
                }
            }),
            onload:  function(r) { console.log('[BetCouncil] Caesars token pushed HTTP ' + r.status); },
            onerror: function(e) { console.error('[BetCouncil] Gist push failed', e); },
        });
    }

    // Intercept XHR on the real page window
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
        if (this._bc_url && this._bc_url.includes('americanwagering.com')) {
            const auth = this._bc_headers && this._bc_headers['authorization'];
            if (auth && auth.startsWith('Bearer ') && auth.length > 60) {
                const bearer = auth.slice(7);
                const waf    = (this._bc_headers['x-aws-waf-token'] || '');
                console.log('[BetCouncil] Captured Caesars Bearer token');
                pushToGist(bearer, waf);
            }
        }
        return origSend.apply(this, arguments);
    };

    // Intercept fetch
    const origFetch = _window.fetch;
    _window.fetch = function(input, init) {
        const url = typeof input === 'string' ? input : (input && input.url) || '';
        if (url.includes('americanwagering.com') && init && init.headers) {
            const h = init.headers;
            let auth = '', waf = '';
            if (h && typeof h.get === 'function') {
                auth = h.get('authorization') || '';
                waf  = h.get('x-aws-waf-token') || '';
            } else if (h && typeof h === 'object') {
                const lh = {};
                Object.keys(h).forEach(function(k) { lh[k.toLowerCase()] = h[k]; });
                auth = lh['authorization'] || '';
                waf  = lh['x-aws-waf-token'] || '';
            }
            if (auth.startsWith('Bearer ') && auth.length > 60) {
                console.log('[BetCouncil] Captured Caesars Bearer (fetch)');
                pushToGist(auth.slice(7), waf);
            }
        }
        return origFetch.apply(_window, arguments);
    };

    console.log('[BetCouncil] Caesars token harvester v1.2 active');
})();
