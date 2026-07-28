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
            const waf  = (this._bc_headers && this._bc_headers['x-aws-waf-token']) || '';
            const hasBearer = auth && auth.startsWith('Bearer ') && auth.length > 60;
            // Confirmed via real live traffic 2026-07-28: many real Caesars
            // API calls carry a valid x-aws-waf-token with NO Authorization
            // header at all -- the old code required both, silently
            // discarding a perfectly good WAF token on every such request.
            // Push on EITHER being present, not requiring both.
            if (hasBearer || waf) {
                console.log(`[BetCouncil] Captured Caesars token(s) -- bearer=${hasBearer} waf=${!!waf}`);
                pushToGist(hasBearer ? auth.slice('Bearer '.length) : '', waf);
            }
        }
        return origSend.call(this, ...args);
    };

    // Also intercept fetch
    const origFetch = window.fetch;
    window.fetch = function(input, init, ...args) {
        // Confirmed via real live traffic 2026-07-28: Caesars' app builds
        // some fetch calls via `new Request(url, {headers})` instead of
        // passing headers as this function's own second argument -- the
        // old code only ever checked `init`, silently missing every
        // request built that way. Check both.
        const url = typeof input === 'string' ? input : (input && input.url) || '';
        let headersSource = (init && init.headers) || (input instanceof Request ? input.headers : null);
        if (url.includes('americanwagering.com') && headersSource) {
            let auth = '', waf = '';
            if (headersSource instanceof Headers) {
                auth = headersSource.get('authorization') || '';
                waf  = headersSource.get('x-aws-waf-token') || '';
            } else if (typeof headersSource === 'object') {
                const h = Object.fromEntries(Object.entries(headersSource).map(([k,v]) => [k.toLowerCase(), v]));
                auth = h['authorization'] || '';
                waf  = h['x-aws-waf-token'] || '';
            }
            const hasBearer = auth.startsWith('Bearer ') && auth.length > 60;
            if (hasBearer || waf) {
                console.log(`[BetCouncil] Captured Caesars token(s) (fetch) -- bearer=${hasBearer} waf=${!!waf}`);
                pushToGist(hasBearer ? auth.slice('Bearer '.length) : '', waf);
            }
        }
        return origFetch.call(this, input, init, ...args);
    };

    console.log('[BetCouncil] Caesars token harvester active');
})();