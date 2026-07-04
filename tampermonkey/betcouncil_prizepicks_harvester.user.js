// ==UserScript==
// @name         BetCouncil PrizePicks Harvester
// @namespace    betcouncil
// @version      2.0
// @description  Intercepts PrizePicks API responses and pushes props to BetCouncil Gist while you browse.
// @match        https://app.prizepicks.com/*
// @grant        none
// @run-at       document-idle
// ==/UserScript==

(function () {
    'use strict';

    // ── BetCouncil Gist config ──
    const GITHUB_TOKEN = 'REPLACE_WITH_YOUR_GITHUB_PAT';  // github.com/settings/tokens — gist scope only
    const GIST_ID = '7e52e1c2c2054847c7c4663a157386c5';

    const LEAGUE_MAP = {
        4: 'NBA', 5: 'MLB', 3: 'NHL', 7: 'NFL', 8: 'WNBA',
        6: 'UFC', 11: 'GOLF', 14: 'PGA', 2: 'SOCCER', 18: 'NASCAR'
    };

    function pushToGist(filename, content) {
        fetch('https://api.github.com/gists/' + GIST_ID, {
            method: 'PATCH',
            headers: {
                'Authorization': 'token ' + GITHUB_TOKEN,
                'Content-Type': 'application/json',
                'Accept': 'application/vnd.github.v3+json'
            },
            body: JSON.stringify({
                files: { [filename]: { content: JSON.stringify(content, null, 2) } }
            })
        }).then(function (r) {
            if (r.ok) {
                console.log('[BetCouncil] Pushed: ' + filename);
            } else {
                console.log('[BetCouncil] Gist push failed for ' + filename + ':', r.status);
            }
        }).catch(function (e) {
            console.log('[BetCouncil] Gist push error for ' + filename + ':', e.message);
        });
    }

    function detectSport(url) {
        var m = url.match(/league_id=(\d+)/);
        if (m) return LEAGUE_MAP[parseInt(m[1])] || null;
        return null;
    }

    function handleResponse(sport, json) {
        var items = Array.isArray(json) ? json : (json.data || []);
        if (!items.length) return;

        var filename = 'betcouncil_prizepicks_' + sport + '.json';
        pushToGist(filename, {
            sport: sport,
            captured_at: new Date().toISOString(),
            data: json,
            source: 'tampermonkey_prizepicks_harvester'
        });
        console.log('[BetCouncil] PrizePicks ' + sport + ' captured: ' + items.length + ' props');
    }

    // ── Hook window.fetch ────────────────────────────────────────────────────
    var _origFetch = window.fetch;
    window.fetch = function () {
        var args = arguments;
        var url = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].url) || '';

        return _origFetch.apply(this, args).then(function (response) {
            if (url.indexOf('prizepicks.com/projections') !== -1 ||
                url.indexOf('api.prizepicks.com/projections') !== -1) {
                var sport = detectSport(url);
                if (sport) {
                    response.clone().json().then(function (json) {
                        handleResponse(sport, json);
                    }).catch(function () {});
                }
            }
            return response;
        });
    };

    // ── Hook XMLHttpRequest ──────────────────────────────────────────────────
    var _origOpen = XMLHttpRequest.prototype.open;
    var _origSend = XMLHttpRequest.prototype.send;

    XMLHttpRequest.prototype.open = function (method, url) {
        this._bc_url = url;
        return _origOpen.apply(this, arguments);
    };

    XMLHttpRequest.prototype.send = function () {
        var self = this;
        if (self._bc_url && self._bc_url.indexOf('prizepicks.com/projections') !== -1) {
            self.addEventListener('load', function () {
                var sport = detectSport(self._bc_url);
                if (!sport) return;
                try {
                    var json = JSON.parse(self.responseText);
                    handleResponse(sport, json);
                } catch (e) {}
            });
        }
        return _origSend.apply(this, arguments);
    };

    // ── Proactive fetch on load — pull active leagues ────────────────────────
    function proactiveFetch() {
        var leagues = [5, 4, 3, 8, 7]; // MLB, NBA, NHL, WNBA, NFL
        leagues.forEach(function (lid) {
            var sport = LEAGUE_MAP[lid];
            if (!sport) return;
            _origFetch('https://api.prizepicks.com/projections?league_id=' + lid + '&per_page=250&single_stat=true', {
                headers: {
                    'Accept': 'application/json',
                    'Referer': 'https://app.prizepicks.com/'
                }
            }).then(function (r) {
                return r.json();
            }).then(function (json) {
                var items = Array.isArray(json) ? json : (json.data || []);
                if (items.length) handleResponse(sport, json);
            }).catch(function () {});
        });
    }

    setTimeout(proactiveFetch, 2500);

    // Re-run proactive fetch every 30 minutes
    setInterval(proactiveFetch, 30 * 60 * 1000);

    console.log('[BetCouncil] PrizePicks harvester active - browse props to capture + auto-fetching on load');
})();
