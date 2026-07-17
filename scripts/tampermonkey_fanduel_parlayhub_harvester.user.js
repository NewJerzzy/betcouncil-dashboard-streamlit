// ==UserScript==
// @name         BetCouncil FanDuel Parlay Hub Harvester
// @namespace    betcouncil
// @version      2.1
// @description  Passively captures FanDuel's "Parlay Hub" (curated popular SGP/parlay picks — login-gated, no public API) from your own authenticated FanDuel tab, and pushes to the shared Gist so BetCouncil's New Bettor tab can show it next to BetCouncil's own picks. v2.0: intercepts FanDuel's own network calls instead of a hardcoded URL, so there's no session token to hand-refresh — install once and forget it. v2.1: adds XHR interception (not just fetch) and broad debug logging of any parlay/odds-related request, to diagnose exactly what FanDuel is calling.
// @match        https://*.fanduel.com/*
// @grant        none
// @run-at       document-start
// ==/UserScript==

(function () {
    'use strict';

    // ── Fill this in once, matching your existing BetMGM/Caesars scripts ──
    var GIST_ID  = '7e52e1c2c2054847c7c4663a157386c5';
    var GIST_TOK = 'PASTE_YOUR_GITHUB_TOKEN_HERE';

    // ── No hardcoded endpoint needed anymore ──────────────────────────────
    // v1 hardcoded the betting-opportunities/all URL including its `_ak`
    // session token, which expires and had to be re-copied from DevTools
    // by hand. v2 instead patches window.fetch (below) to watch every
    // request FanDuel's own app already makes and grabs the response the
    // moment FanDuel calls this endpoint itself — same data, zero manual
    // upkeep, and it keeps working even if FanDuel changes the `_ak` value
    // or query params.
    var PARLAY_HUB_URL_MATCH = 'betting-opportunities/all';

    var __bcGistQueue = Promise.resolve();

    function __bcPushGistOnce(filename, content) {
        return fetch('https://api.github.com/gists/' + GIST_ID, {
            method: 'PATCH',
            headers: {
                'Authorization': 'token ' + GIST_TOK,
                'Content-Type': 'application/json',
                'Accept': 'application/vnd.github.v3+json'
            },
            body: JSON.stringify({ files: { [filename]: { content: JSON.stringify(content, null, 2) } } })
        });
    }

    function pushGist(filename, content) {
        __bcGistQueue = __bcGistQueue.then(function () {
            return __bcPushGistOnce(filename, content).then(function (r) {
                if (r.ok) {
                    console.log('[BetCouncil-FDParlayHub] ✅ Pushed: ' + filename);
                    return;
                }
                if (r.status === 409) {
                    return new Promise(function (resolve) { setTimeout(resolve, 800); })
                        .then(function () { return __bcPushGistOnce(filename, content); })
                        .then(function (r2) {
                            console.log(r2.ok
                                ? '[BetCouncil-FDParlayHub] ✅ Pushed (after retry): ' + filename
                                : '[BetCouncil-FDParlayHub] ⚠️ Push failed after retry: ' + filename + ' status=' + r2.status);
                        });
                }
                console.log('[BetCouncil-FDParlayHub] ⚠️ Push failed: ' + filename + ' status=' + r.status);
            }).catch(function (e) {
                console.log('[BetCouncil-FDParlayHub] Push error:', filename, e.message);
            });
        });
        return __bcGistQueue;
    }

    function throttled(key, ms, fn) {
        var last = localStorage.getItem('bc_fdph_harvest_' + key);
        if (last && (Date.now() - parseInt(last)) < ms) return;
        localStorage.setItem('bc_fdph_harvest_' + key, Date.now().toString());
        fn();
    }

    // Sport is inferred from whichever league tab is active in Parlay Hub
    // rather than hard-mapped, since Parlay Hub mixes sports on one page.
    // Falls back to "ALL" if the page doesn't expose it — the Python side
    // (fetch_fanduel_parlayhub_from_gist) reads per-sport gist files, so
    // pushing under "ALL" still works, it just won't sport-filter.
    function detectActiveSport() {
        var active = document.querySelector('[aria-selected="true"], .selected, .active');
        var text = active ? active.textContent.trim().toUpperCase() : '';
        var known = ['NFL', 'NBA', 'MLB', 'NHL', 'WNBA', 'NCAAFB', 'NCAAMB', 'SOCCER', 'UFC'];
        for (var i = 0; i < known.length; i++) {
            if (text.indexOf(known[i]) !== -1) return known[i];
        }
        return 'ALL';
    }

    function pushParlayHubData(data) {
        throttled('parlayhub', 1500000, function () { // every 25 min, max
            var sport = detectActiveSport();
            pushGist('betcouncil_fd_parlayhub_' + sport + '.json', {
                sport: sport,
                captured_at: new Date().toISOString(),
                data: data,
                source: 'betcouncil_tampermonkey_harvest_v2'
            });
        });
    }

    // ── v2.1 diagnostics: log every fetch/XHR whose URL looks parlay/odds-
    // related, whether or not it matches PARLAY_HUB_URL_MATCH. If the exact
    // capture below isn't firing, these lines tell us what to match instead
    // — no DevTools Network tab needed, just paste the console output back.
    var DEBUG_KEYWORDS = ['parlay', 'betting-opp', 'popular', 'boapi'];
    function debugLog(kind, url) {
        var l = url.toLowerCase();
        for (var i = 0; i < DEBUG_KEYWORDS.length; i++) {
            if (l.indexOf(DEBUG_KEYWORDS[i]) !== -1) {
                console.log('[BetCouncil-FDParlayHub][debug] ' + kind + ' -> ' + url);
                return;
            }
        }
    }

    // ── Passive capture: patch window.fetch so we see the response the
    // moment FanDuel's own front-end calls betting-opportunities/all while
    // you're just browsing Parlay Hub normally. No separate request is
    // made, no CORS issue, and no session token ever needs updating —
    // whatever URL/params FanDuel is using right now is exactly what gets
    // captured. ──────────────────────────────────────────────────────────
    if (GIST_TOK.indexOf('PASTE_') !== 0) {
        var __bcOrigFetch = window.fetch;
        window.fetch = function (input, init) {
            var url = (typeof input === 'string') ? input : (input && input.url) || '';
            debugLog('fetch', url);
            var p = __bcOrigFetch.apply(this, arguments);
            if (url.indexOf(PARLAY_HUB_URL_MATCH) !== -1) {
                p.then(function (r) {
                    r.clone().json().then(function (data) {
                        console.log('[BetCouncil-FDParlayHub] Captured live betting-opportunities response (fetch)');
                        pushParlayHubData(data);
                    }).catch(function () {});
                }).catch(function () {});
            }
            return p;
        };

        // Same capture, but for XMLHttpRequest — some FanDuel modules use
        // XHR instead of fetch for this kind of call.
        var __bcOrigOpen = XMLHttpRequest.prototype.open;
        var __bcOrigSend = XMLHttpRequest.prototype.send;
        XMLHttpRequest.prototype.open = function (method, url) {
            this.__bcUrl = url;
            debugLog('xhr', url);
            return __bcOrigOpen.apply(this, arguments);
        };
        XMLHttpRequest.prototype.send = function () {
            var self = this;
            if (self.__bcUrl && self.__bcUrl.indexOf(PARLAY_HUB_URL_MATCH) !== -1) {
                self.addEventListener('load', function () {
                    try {
                        var data = JSON.parse(self.responseText);
                        console.log('[BetCouncil-FDParlayHub] Captured live betting-opportunities response (xhr)');
                        pushParlayHubData(data);
                    } catch (e) {}
                });
            }
            return __bcOrigSend.apply(this, arguments);
        };
    }

    console.log('[BetCouncil-FDParlayHub] Harvester active on ' + window.location.hostname
        + (GIST_TOK.indexOf('PASTE_') === 0 ? ' — waiting on GIST_TOK to be filled in' : ' — watching for Parlay Hub data (v2.1 debug mode: logging any parlay/odds-related request)'));
})();
