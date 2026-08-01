// ==UserScript==
// @name         BetCouncil TheScore Bet Harvester
// @namespace    betcouncil
// @version      4.0
// @description  Captures theScore Bet game lines (moneyline/spread/total) via a hand-built full GraphQL query (not persisted-query hash), pushes to shared Gist
// @match        https://sportsbook.thescore.bet/*
// @grant        none
// ==/UserScript==

(function () {
    'use strict';
    const GRAPHQL_ENDPOINT = "https://sportsbook.us-default.thescore.bet/graphql";
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

    // Hand-built, non-persisted GraphQL query -- the original persisted
    // query hash bakes in a stale ParticipantTeam fragment (abbreviation,
    // colour1, logos) that no longer exists on the current Team type,
    // which is a schema VALIDATION error (no partial data possible, ever,
    // regardless of variables). This full query document has that broken
    // fragment (and several other now-broken optional pieces: richEvent,
    // recommendedProps, statistics) removed entirely. Confirmed via a real
    // test call that this document parses and passes schema validation
    // cleanly (a real `data` key came back, just null due to an auth
    // check on the resolver -- a completely different, expected kind of
    // block that a real logged-in browser session resolves).
    const QUERY_DOCUMENT = `query GetCompetitionLines($sectionId: ID!, $oddsFormat: OddsFormat!, $isSubscription: Boolean = false, $pageType: PageType = PAGE, $selectedFilterId: ID) {
  competitionSection(id: $sectionId) {
    id
    slug
    sectionChildren {
      ... on MarketplaceShelf {
        id
        icon(imageSize: { resizeFormat: AUTO, maxWidth: 48, maxHeight: 48 }) {
          customSize: customSizeThemable
          customHeight
          customWidth
        }
        marketplaceShelfChildren(selectedFilterId: $selectedFilterId) {
          ... on GridMarketCard {
            id
            rawId
            attributes
            marketTags
            deepLink(pageType: $pageType) { webUrl }
            markets(pageType: $pageType) {
              id
              name @skip(if: $isSubscription)
              status
              type @skip(if: $isSubscription)
              extraInformation
              startTime
              updatedAtTime
              selections {
                id
                rawId
                status
                probabilityEncrypted
                name @skip(if: $isSubscription) {
                  cleanName
                  defaultName
                  fullName
                  minimalName
                }
                odds {
                  denominatorLong
                  numeratorLong
                  formattedOdds(oddsFormat: $oddsFormat)
                }
                points @skip(if: $isSubscription) {
                  decimalPoints
                  formattedPoints
                }
                participant @skip(if: $isSubscription) {
                  id
                  abbreviation
                  mediumName
                  fullName
                  resourceUri
                }
              }
            }
            fallbackEvent @skip(if: $isSubscription) {
              id
              name
              startTime
              status
              slug
              resourceUri
              competition { id name slug resourceUri }
              sport { id name slug resourceUri }
              organization { id slug }
              ... on StandardEvent {
                homeParticipant { id abbreviation mediumName fullName resourceUri }
                awayParticipant { id abbreviation mediumName fullName resourceUri }
              }
            }
          }
          ... on ThreeWayMoneylineMarketCard { id rawId }
          ... on CompactMultipleMarketCard { id rawId }
          ... on ListMarketCard { id rawId }
          ... on SoccerGridMarketCard { id rawId }
          ... on TennisGridMarketCard { id rawId }
          ... on SimpleGridMarketCard { id rawId }
          ... on CricketGridMarketCard { id rawId }
          ... on CombatGridMarketCard { id rawId }
        }
      }
      ... on FeaturedMarketsCarousel { id label }
    }
  }
}
`;

    // Confirmed via real, empirical testing: credentials:"include" only
    // forwards cookies, but theScore's auth token is a JWT stored in
    // localStorage (Zustand persist format), never a cookie -- that's
    // the actual missing piece the whole time. Verified by observing a
    // real 403 -> 401 status/message flip the moment ANY Authorization
    // header is present, confirming the resolver requires a real bearer
    // token specifically, not just a valid session.
    function getAuthHeaders() {
        let bearerToken = null;
        try {
            const raw = localStorage.getItem("__SBWEB____AUTH_TOKENS__");
            if (raw) bearerToken = JSON.parse(raw)?.state?.bearerToken ?? null;
        } catch (_) {}
        let dmaCode = "", device = "DESKTOP";
        try {
            const raw = sessionStorage.getItem("__SBWEB____VIEWER_DATA__");
            if (raw) {
                const vd = JSON.parse(raw)?.state?.viewerData;
                dmaCode = vd?.dmaCode ?? "";
                device = vd?.device ?? "DESKTOP";
            }
        } catch (_) {}
        const headers = { "Content-Type": "application/json", "Accept": "application/json" };
        if (bearerToken) headers["authorization"] = `Bearer ${bearerToken}`;
        headers["x-dma"] = dmaCode;
        headers["x-device"] = device;
        return headers;
    }

    function buildRequestBody(sectionId) {
        const variables = {
            sectionId: sectionId,
            oddsFormat: "AMERICAN",
            isSubscription: false,
            pageType: "PAGE",
            selectedFilterId: null,
        };
        return JSON.stringify({
            operationName: "GetCompetitionLines",
            variables: variables,
            query: QUERY_DOCUMENT,
        });
    }

    async function harvestGameLines() {
        const allData = {};
        for (const [sport, sectionId] of Object.entries(SPORTS_SECTIONS)) {
            try {
                const res = await fetch(GRAPHQL_ENDPOINT, { method: "POST", credentials: "include", headers: getAuthHeaders(), body: buildRequestBody(sectionId) });
                const json = await res.json().catch(() => null);
                if (!json) {
                    console.warn(`[BetCouncil TheScore Harvester] ${sport} unparseable body, status:`, res.status);
                    continue;
                }
                if (json.errors) {
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

    harvestGameLines();
    setInterval(harvestGameLines, POLL_INTERVAL_MS);
})();
