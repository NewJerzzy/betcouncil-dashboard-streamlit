// ==UserScript==
// @name         BetCouncil BetMGM Harvester
// @namespace    betcouncil
// @version      1.0
// @description  Passively fetches BetMGM live-bettables odds from betmgm.com's own origin (avoids the CORS block that killed the old in-app cross-origin harvester) and pushes to the shared Gist for BetCouncil to read.
// @match        https://*.betmgm.com/*
// @grant        none
// @run-at       document-idle
// ==/UserScript==

(function () {
    'use strict';

    // ── Fill these in once, matching your existing Caesars/FanDuel scripts ──
    var GIST_ID  = '7e52e1c2c2054847c7c4663a157386c5';
    var GIST_TOK = 'PASTE_YOUR_GITHUB_TOKEN_HERE';

    // Same retry/queue pattern used by every other BetCouncil harvester —
    // serializes writes so concurrent PATCHes to the same Gist don't 409.
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
                    console.log('[BetCouncil-MGM] ✅ Pushed: ' + filename);
                    return;
                }
                if (r.status === 409) {
                    return new Promise(function (resolve) { setTimeout(resolve, 800); })
                        .then(function () { return __bcPushGistOnce(filename, content); })
                        .then(function (r2) {
                            console.log(r2.ok
                                ? '[BetCouncil-MGM] ✅ Pushed (after retry): ' + filename
                                : '[BetCouncil-MGM] ⚠️ Push failed after retry: ' + filename + ' status=' + r2.status);
                        });
                }
                console.log('[BetCouncil-MGM] ⚠️ Push failed: ' + filename + ' status=' + r.status);
            }).catch(function (e) {
                console.log('[BetCouncil-MGM] Push error:', filename, e.message);
            });
        });
        return __bcGistQueue;
    }

    function throttled(key, ms, fn) {
        var last = localStorage.getItem('bc_mgm_harvest_' + key);
        if (last && (Date.now() - parseInt(last)) < ms) return;
        localStorage.setItem('bc_mgm_harvest_' + key, Date.now().toString());
        fn();
    }

    // Same sport-slug mapping the (now-retired) in-app harvester used —
    // keeps the Gist filename/shape identical so fetch_betmgm_props_from_gist()
    // and _parse_betmgm_harvested() in fetchers.py need zero changes.
    var mgmSportMap = {
        'MLB': 'baseball', 'NBA': 'basketball',
        'NFL': 'american-football', 'NHL': 'ice-hockey', 'UFC': 'mma'
    };

    function harvestSport(sport, slug) {
        throttled('betmgm_' + sport, 1500000, function () { // every 25 min
            fetch('https://sports.az.betmgm.com/cds-web/api/v2/widgets/live-bettables?sport=' + slug + '&state=az&lang=en-us', {
                headers: {
                    'Accept': 'application/json',
                    'Origin': 'https://sports.az.betmgm.com',
                    'Referer': 'https://sports.az.betmgm.com/'
                }
            }).then(function (r) { return r.json(); })
              .then(function (data) {
                pushGist('betcouncil_mgm_props_' + sport + '.json', {
                    sport: sport,
                    captured_at: new Date().toISOString(),
                    data: data,
                    source: 'betcouncil_tampermonkey_harvest'
                });
              }).catch(function (e) {
                console.log('[BetCouncil-MGM] Harvest error (' + sport + '):', e.message);
              });
        });
    }

    // Harvest every mapped sport on every page load/idle, throttled to once
    // per 25 min per sport regardless of how many BetMGM tabs/pages you visit.
    Object.keys(mgmSportMap).forEach(function (sport) {
        harvestSport(sport, mgmSportMap[sport]);
    });

    console.log('[BetCouncil-MGM] Harvester active on ' + window.location.hostname);
})();
