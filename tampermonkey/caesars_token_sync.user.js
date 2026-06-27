// ==UserScript==
// @name         Caesars Token Sync → Gist
// @namespace    betcouncil
// @version      1.1
// @description  Intercepts americanwagering.com XHRs while you browse Caesars and pushes the Bearer JWT + WAF token to the betcouncil Gist automatically.
// @author       betcouncil
// @match        https://sportsbook.caesars.com/*
// @grant        GM_xmlhttpRequest
// @grant        GM_setValue
// @grant        GM_getValue
// @connect      api.github.com
// @run-at       document-start
// ==/UserScript==

(function () {
    'use strict';

    // ── Config — fill these in after installing ───────────────────────────────
    // GIST_TOKEN: create a GitHub PAT at github.com/settings/tokens with "gist" scope
    const GIST_TOKEN = 'PASTE_YOUR_GIST_PAT_HERE';
    const GIST_ID    = '7e52e1c2c2054847c7c4663a157386c5';
    const MIN_PUSH_INTERVAL_MS = 20 * 60 * 1000; // push at most once per 20 min

    if (GIST_TOKEN === 'PASTE_YOUR_GIST_PAT_HERE') {
        console.warn('[betcouncil] Caesars Token Sync: set GIST_TOKEN in the script before use.');
        return;
    }

    let lastPushAt = GM_getValue('caesars_last_push', 0);
    let badge;

    function showBadge(msg, color) {
        if (!badge) {
            badge = document.createElement('div');
            Object.assign(badge.style, {
                position: 'fixed', bottom: '12px', right: '12px',
                background: color, color: '#fff', padding: '6px 12px',
                borderRadius: '6px', fontSize: '12px', fontWeight: 'bold',
                zIndex: '999999', fontFamily: 'monospace',
                boxShadow: '0 2px 8px rgba(0,0,0,.4)',
            });
            document.body.appendChild(badge);
        }
        badge.style.background = color;
        badge.textContent = msg;
        badge.style.display = 'block';
        setTimeout(() => { if (badge) badge.style.display = 'none'; }, 4000);
    }

    function pushToGist(bearer, waf) {
        const now = Date.now();
        if (now - lastPushAt < MIN_PUSH_INTERVAL_MS) return; // debounce
        lastPushAt = now;
        GM_setValue('caesars_last_push', now);

        const payload = {
            files: {
                'caesars_tokens.json': {
                    content: JSON.stringify({
                        bearer_jwt:  bearer,
                        waf_token:   waf || '',
                        captured_at: new Date().toISOString(),
                    }, null, 2)
                }
            }
        };

        GM_xmlhttpRequest({
            method: 'PATCH',
            url:    `https://api.github.com/gists/${GIST_ID}`,
            headers: {
                'Authorization': `token ${GIST_TOKEN}`,
                'Accept':        'application/vnd.github.v3+json',
                'Content-Type':  'application/json',
            },
            data: JSON.stringify(payload),
            onload: (r) => {
                if (r.status === 200 || r.status === 201) {
                    showBadge('🟢 Caesars token synced', '#1a7f37');
                    console.log('[betcouncil] Caesars Bearer pushed to Gist', new Date().toLocaleTimeString());
                } else {
                    showBadge('\u26a0 Gist push failed ' + r.status, '#b94a48');
                    console.warn('[betcouncil] Gist push failed', r.status, r.responseText.slice(0, 200));
                }
            },
            onerror: () => showBadge('\u26a0 Gist push error', '#b94a48'),
        });
    }

    // ── XHR intercept ────────────────────────────────────────────────────────
    const _open = XMLHttpRequest.prototype.open;
    const _setHdr = XMLHttpRequest.prototype.setRequestHeader;

    XMLHttpRequest.prototype.open = function (m, url) {
        this._bc_url = url; this._bc_h = {};
        return _open.apply(this, arguments);
    };
    XMLHttpRequest.prototype.setRequestHeader = function (k, v) {
        if (this._bc_url && this._bc_url.includes('americanwagering.com'))
            this._bc_h[k.toLowerCase()] = v;
        return _setHdr.apply(this, arguments);
    };
    XMLHttpRequest.prototype.send = function () {
        if (this._bc_url && this._bc_url.includes('americanwagering.com')) {
            const auth = this._bc_h['authorization'] || '';
            if (auth.startsWith('Bearer ') && auth.length > 60)
                pushToGist(auth.slice(7), this._bc_h['x-aws-waf-token'] || '');
        }
        return XMLHttpRequest.prototype.send.apply(this, arguments);
    };

    // ── fetch intercept ───────────────────────────────────────────────────────
    const _fetch = window.fetch;
    window.fetch = function (input, init) {
        const url = typeof input === 'string' ? input : (input.url || '');
        if (url.includes('americanwagering.com') && init && init.headers) {
            const h = init.headers instanceof Headers
                ? Object.fromEntries(init.headers.entries()) : init.headers;
            const auth = h['authorization'] || h['Authorization'] || '';
            if (auth.startsWith('Bearer ') && auth.length > 60)
                pushToGist(auth.slice(7), h['x-aws-waf-token'] || '');
        }
        return _fetch.apply(this, arguments);
    };

    console.log('[betcouncil] Caesars Token Sync v1.1 active');
})();
