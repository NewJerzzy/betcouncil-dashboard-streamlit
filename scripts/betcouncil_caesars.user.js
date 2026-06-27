// ==UserScript==
// @name         BetCouncil — Caesars Token Harvester
// @namespace    https://github.com/NewJerzzy/betcouncil-dashboard-streamlit
// @version      1.0
// @description  Intercepts Caesars sportsbook auth tokens and pushes them to BetCouncil Gist
// @author       BetCouncil
// @match        https://sportsbook.caesars.com/*
// @grant        GM_xmlhttpRequest
// @connect      api.github.com
// @run-at       document-start
// ==/UserScript==

(function() {
    'use strict';

    // ── CONFIG — fill in your GitHub PAT with gist scope ──────────────────
    const GIST_TOKEN = 'YOUR_GIST_TOKEN_HERE';
    const GIST_ID    = '7e52e1c2c2054847c7c4663a157386c5';
    // ──────────────────────────────────────────────────────────────────────

    let lastPush = 0;

    function pushToGist(bearer, wafToken) {
        const now = Date.now();
        if (now - lastPush < 60000) return; // throttle: max once per minute
        lastPush = now;

        const payload = {
            files: {
                'betcouncil_caesars_tokens.json': {
                    content: JSON.stringify({
                        bearer_jwt:   bearer,
                        waf_token:    wafToken || '',
                        captured_at:  new Date().toISOString(),
                    }, null, 2)
                }
            }
        };

        GM_xmlhttpRequest({
            method: 'PATCH',
            url: `https://api.github.com/gists/${GIST_ID}`,
            headers: {
                'Authorization': `token ${GIST_TOKEN}`,
                'Content-Type':  'application/json',
                'Accept':        'application/vnd.github.v3+json',
            },
            data: JSON.stringify(payload),
            onload: (r) => console.log(`[BetCouncil] Caesars token pushed HTTP ${r.status}`),
            onerror: (e) => console.error('[BetCouncil] Gist push failed:', e),
        });
    }

    // Intercept XHR
    const origOpen = XMLHttpRequest.prototype.open;
    const origSetHeader = XMLHttpRequest.prototype.setRequestHeader;

    XMLHttpRequest.prototype.open = function(method, url, ...args) {
        this._bc_url = url;
        this._bc_headers = {};
        return origOpen.call(this, method, url, ...args);
    };

    XMLHttpRequest.prototype.setRequestHeader = function(name, value) {
        if (this._bc_headers) this._bc_headers[name.toLowerCase()] = value;
        return origSetHeader.call(this, name, value);
    };

    const origSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.send = function(...args) {
        if (this._bc_url && this._bc_url.includes('americanwagering.com')) {
            const auth = this._bc_headers && this._bc_headers['authorization'];
            if (auth && auth.startsWith('Bearer ') && auth.length > 60) {
                const bearer = auth.slice('Bearer '.length);
                const waf    = this._bc_headers['x-aws-waf-token'] || '';
                console.log('[BetCouncil] Captured Caesars Bearer token');
                pushToGist(bearer, waf);
            }
        }
        return origSend.call(this, ...args);
    };

    // Also intercept fetch
    const origFetch = window.fetch;
    window.fetch = function(input, init, ...args) {
        const url = typeof input === 'string' ? input : (input && input.url) || '';
        if (url.includes('americanwagering.com') && init && init.headers) {
            const headers = init.headers;
            let auth = '', waf = '';
            if (headers instanceof Headers) {
                auth = headers.get('authorization') || '';
                waf  = headers.get('x-aws-waf-token') || '';
            } else if (typeof headers === 'object') {
                const h = Object.fromEntries(Object.entries(headers).map(([k,v]) => [k.toLowerCase(), v]));
                auth = h['authorization'] || '';
                waf  = h['x-aws-waf-token'] || '';
            }
            if (auth.startsWith('Bearer ') && auth.length > 60) {
                console.log('[BetCouncil] Captured Caesars Bearer (fetch)');
                pushToGist(auth.slice('Bearer '.length), waf);
            }
        }
        return origFetch.call(this, input, init, ...args);
    };

    console.log('[BetCouncil] Caesars token harvester active');
})();
