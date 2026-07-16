// ==UserScript==
// @name         BetCouncil FanDuel Parlay Hub Harvester
// @namespace    betcouncil
// @version      1.0
// @description  Passively captures FanDuel's "Parlay Hub" (curated popular SGP/parlay picks — login-gated, no public API) from your own authenticated FanDuel tab, and pushes to the shared Gist so BetCouncil's New Bettor tab can show it next to BetCouncil's own picks.
// @match        https://*.fanduel.com/*
// @grant        none
// @run-at       document-idle
// ==/UserScript==

(function () {
    'use strict';

    // ── Fill these in once, matching your existing BetMGM/Caesars scripts ──
    var GIST_ID  = '7e52e1c2c2054847c7c4663a157386c5';
    var GIST_TOK = 'PASTE_YOUR_GITHUB_TOKEN_HERE';

    // ── ENDPOINT — confirmed live 2026-07-16 via DevTools capture ────────
    // Real request: GET boapi.sportsbook.fanduel.com/betting-opportunities/all
    // Response confirmed to contain popularBettingOpportunities (PARLAY/SGP
    // entries with narrative, americanOdds, totalBets, selections) plus an
    // "attachments" block with full market/runner/team data to resolve
    // those selections into readable picks. No extra auth header needed —
    // credentials:'include' (session cookies) was sufficient.
    //
    // The `_ak` query param looks account/session-scoped and may need
    // refreshing if this stops returning data — same DevTools steps as
    // before: open Parlay Hub, Network tab, find the fresh
    // betting-opportunities/all request, copy its Request URL here.
    var PARLAY_HUB_ENDPOINT = 'https://boapi.sportsbook.fanduel.com/betting-opportunities/all?cardVersion=v1&_ak=FhMFpcPWXMeyZxOx&source=ORGANIC,MANUAL';

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

    function harvestParlayHub() {
        if (PARLAY_HUB_ENDPOINT.indexOf('PASTE_') === 0) {
            console.log('[BetCouncil-FDParlayHub] Endpoint not configured yet — see setup comment at top of this script. Not pushing anything.');
            return;
        }
        throttled('parlayhub', 1500000, function () { // every 25 min
            fetch(PARLAY_HUB_ENDPOINT, {
                headers: {
                    'Accept': 'application/json',
                    'Referer': window.location.href
                },
                credentials: 'include'  // send your logged-in session cookies
            }).then(function (r) { return r.json(); })
              .then(function (data) {
                var sport = detectActiveSport();
                pushGist('betcouncil_fd_parlayhub_' + sport + '.json', {
                    sport: sport,
                    captured_at: new Date().toISOString(),
                    data: data,
                    source: 'betcouncil_tampermonkey_harvest'
                });
              }).catch(function (e) {
                console.log('[BetCouncil-FDParlayHub] Harvest error:', e.message);
              });
        });
    }

    // Only harvest while actually on a Parlay Hub page/tab, not every
    // FanDuel page — avoids wasted requests and matches the "browse
    // Parlay Hub in an authenticated tab" protocol used elsewhere.
    if (window.location.href.toLowerCase().indexOf('parlay') !== -1) {
        harvestParlayHub();
    }

    console.log('[BetCouncil-FDParlayHub] Harvester active on ' + window.location.hostname);
})();
