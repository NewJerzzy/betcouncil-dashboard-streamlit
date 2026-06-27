// ==UserScript==
// @name         BetCouncil — FanDuel Token Harvester
// @namespace    https://github.com/NewJerzzy/betcouncil-dashboard-streamlit
// @version      1.0
// @description  Intercepts FanDuel PerimeterX token and pushes to BetCouncil Gist
// @author       BetCouncil
// @match        https://sportsbook.fanduel.com/*
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

    function pushToGist(pxToken, authToken) {
        const now = Date.now();
        if (now - lastPush < 60000) return;
        lastPush = now;

        const payload = {
            files: {
                'betcouncil_fanduel_tokens.json': {
                    content: JSON.stringify({
                        px_token:    pxToken,
                        auth_token:  authToken || '',
                        captured_at: new Date().toISOString(),
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
            onload: (r) => console.log(`[BetCouncil] FanDuel token pushed HTTP ${r.status}`),
            onerror: (e) => console.error('[BetCouncil] Gist push failed:', e),
        });
    }

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
        if (this._bc_url && this._bc_url.includes('fanduel.com')) {
            const h = this._bc_headers || {};
            const px   = h['x-px-context'] || h['x-px-authorization'] || '';
            const auth = h['authorization'] || '';
            if (px) {
                console.log('[BetCouncil] Captured FanDuel PX token');
                pushToGist(px, auth);
            }
        }
        return origSend.call(this, ...args);
    };

    const origFetch = window.fetch;
    window.fetch = function(input, init, ...args) {
        const url = typeof input === 'string' ? input : (input && input.url) || '';
        if (url.includes('fanduel.com') && init && init.headers) {
            const headers = init.headers;
            let px = '', auth = '';
            if (headers instanceof Headers) {
                px   = headers.get('x-px-context') || headers.get('x-px-authorization') || '';
                auth = headers.get('authorization') || '';
            } else if (typeof headers === 'object') {
                const h = Object.fromEntries(Object.entries(headers).map(([k,v]) => [k.toLowerCase(), v]));
                px   = h['x-px-context'] || h['x-px-authorization'] || '';
                auth = h['authorization'] || '';
            }
            if (px) {
                console.log('[BetCouncil] Captured FanDuel PX token (fetch)');
                pushToGist(px, auth);
            }
        }
        return origFetch.call(this, input, init, ...args);
    };

    console.log('[BetCouncil] FanDuel token harvester active');
})();
