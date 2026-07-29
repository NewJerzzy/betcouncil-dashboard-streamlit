// ==UserScript==
// @name         BetCouncil TheScore Bet Harvester
// @namespace    betcouncil
// @version      3.1
// @description  Captures theScore Bet game lines (moneyline/spread/total) with self-healing persisted query hash, pushes to shared Gist
// @match        https://sportsbook.thescore.bet/*
// @grant        none
// ==/UserScript==

(function () {
    'use strict';
    const GRAPHQL_ENDPOINT = "https://sportsbook.us-default.thescore.bet/graphql";
    const OPERATION_NAME = "CompetitionPageSectionLinesTabNode";
    let QUERY_HASH = localStorage.getItem("bc_thescore_hash") ||
        "4fcab2e9b286b7b14db66c66280a38bceab9effed830e3a805e833d7ce8cac0b";
    const SPORTS_SECTIONS = {
        MLB: "Section:d9513891-c315-4c16-8554-09d52d3ce9b2",
        NFL: "Section:647c3091-b79f-47bc-a96c-b053cc3a4a6a",
        WNBA: "Section:7ffc9b6f-598e-4080-88eb-0e04ce2cf28e",
        UFC: "Section:2f68eb65-3813-4f28-9dca-979db608e050",
        TENNIS: "Section:e049b112-bdb3-4ccd-ac12-df9cd5849369",
    };
    const GIST_ID = "7e52e1c2c2054847c7c4663a157386c5";
    const GITHUB_TOKEN = "PASTE_YOUR_GITHUB_TOKEN_HERE";
    const GIST_FILENAME = "betcouncil_thescore_games.json";
    const POLL_INTERVAL_MS = 45000;
    const HASH_CHECK_INTERVAL_MS = 6 * 60 * 60 * 1000;

    function buildRequestUrl(sectionId) {
        // Optional/cosmetic flags all set false -- confirmed via real error
        // messages ('Cannot query field jerseyImage/headshots/logos/colour1
        // on Team/Player', 'Unknown type RecommendedPropSelection/Country')
        // that these conditionally-included fields no longer exist on the
        // current schema, even though this persisted query hash still
        // references them when these flags are true. We only need core
        // odds data, not player headshots/branding/recommended-props UI.
        const variables = {
            isSubscription: false,
            includeStandardizedBoxscore: false,
            pageType: "PAGE",
            includeRecommendedProps: false,
            isBrandingImageEnabled: false,
            isNewFeaturedBetParticipantLogoEnabled: false,
            isFeaturedBetCarouselHeaderRedesignEnabled: false,
            isCfpRankingEnabled: false,
            isCombatSportsRedesignEnabled: false,
            isFeaturedMarketCardRedesignEnabled: false,
            isDsModelRecommendedPropsEnabled: false,
            includeRichEvent: false,
            oddsFormat: "AMERICAN",
            sectionId: sectionId,
            selectedFilterId: "",
        };
        const extensions = { persistedQuery: { version: 1, sha256Hash: QUERY_HASH } };
        const params = new URLSearchParams({
            operationName: OPERATION_NAME,
            variables: JSON.stringify(variables),
            extensions: JSON.stringify(extensions),
        });
        return `${GRAPHQL_ENDPOINT}/persisted_queries/${QUERY_HASH}?${params.toString()}`;
    }

    async function checkForHashUpdate() {
        try {
            const homeRes = await fetch("https://sportsbook.thescore.bet/", { credentials: "omit" });
            const homeHtml = await homeRes.text();
            const scriptSrcs = Array.from(homeHtml.matchAll(/src="(\/_next\/static\/chunks\/pages\/index-[^"]+\.js)"/g)).map(m => m[1]);
            if (scriptSrcs.length === 0) {
                console.warn("[BetCouncil TheScore Harvester] hash self-heal: could not find index bundle");
                return;
            }
            for (const src of scriptSrcs) {
                const jsRes = await fetch(`https://sportsbook.thescore.bet${src}`, { credentials: "omit" });
                const jsText = await jsRes.text();
                const linesMatch = jsText.match(new RegExp(`"${OPERATION_NAME}":"([a-f0-9]{64})"`));
                if (linesMatch && linesMatch[1] !== QUERY_HASH) {
                    console.warn(`[BetCouncil TheScore Harvester] hash changed: ${QUERY_HASH} -> ${linesMatch[1]}`);
                    QUERY_HASH = linesMatch[1];
                    localStorage.setItem("bc_thescore_hash", QUERY_HASH);
                }
                if (linesMatch) break;
            }
        } catch (e) {
            console.warn("[BetCouncil TheScore Harvester] hash self-heal check failed:", e);
        }
    }

    async function harvestGameLines() {
        const allData = {};
        for (const [sport, sectionId] of Object.entries(SPORTS_SECTIONS)) {
            try {
                const res = await fetch(buildRequestUrl(sectionId), { method: "GET", credentials: "include", headers: { "Accept": "application/json" } });
                const json = await res.json().catch(() => null);
                if (!json) {
                    console.warn(`[BetCouncil TheScore Harvester] ${sport} unparseable body, status:`, res.status);
                    continue;
                }
                if (json.errors) {
                    const notFound = json.errors.some(e => e?.message === "PersistedQueryNotFound" || e?.extensions?.code === "PERSISTED_QUERY_NOT_FOUND");
                    if (notFound) {
                        console.warn("[BetCouncil TheScore Harvester] PersistedQueryNotFound — forcing hash refresh");
                        await checkForHashUpdate();
                        continue;
                    }
                    // GraphQL supports partial success: data + errors can both be
                    // present in the same response. Confirmed via real capture
                    // that this specific field error (Team.abbreviation, not
                    // gated by any of our disabled flags) still comes back
                    // alongside real usable data -- only bail out if data is
                    // genuinely empty, not just because *an* error exists.
                    console.warn(`[BetCouncil TheScore Harvester] ${sport} graphql error (using partial data anyway): ${JSON.stringify(json.errors[0])}`);
                    if (!json.data) { continue; }
                }
                allData[sport] = json;
            } catch (e) {
                console.error(`[BetCouncil TheScore Harvester] ${sport} error:`, e);
            }
        }
        if (Object.keys(allData).length === 0) return;
        const payload = { captured_at: new Date().toISOString(), data: allData };
        await pushToGist(payload);
    }

    async function pushToGist(payload) {
        const res = await fetch(`https://api.github.com/gists/${GIST_ID}`, {
            method: "PATCH",
            headers: { "Authorization": `token ${GITHUB_TOKEN}`, "Content-Type": "application/json", "Accept": "application/vnd.github.v3+json" },
            body: JSON.stringify({ files: { [GIST_FILENAME]: { content: JSON.stringify(payload) } } }),
        });
        if (!res.ok) { console.warn("[BetCouncil TheScore Harvester] Gist push failed:", res.status); }
        else { console.log("[BetCouncil TheScore Harvester] pushed", GIST_FILENAME, "at", payload.captured_at); }
    }

    checkForHashUpdate();
    setInterval(checkForHashUpdate, HASH_CHECK_INTERVAL_MS);
    harvestGameLines();
    setInterval(harvestGameLines, POLL_INTERVAL_MS);
})();
