---
name: theScore Bet GraphQL investigation
description: Real endpoint, current hash, full schema error list, sectionId source, and recommended fix approach for the Tampermonkey userscript
---

## Real Endpoint
`https://sportsbook.us-default.thescore.bet/graphql` — found in `env.js` (public)
NOT `sportsbook.thescore.bet/api/graphql` (405 Method Not Allowed)
WebSocket: `wss://sportsbook.us-default.thescore.bet/graphql/websocket`

**Why:** `env.js` is served publicly at `https://sportsbook.thescore.bet/env.js` and contains all Next.js public env vars including `NEXT_PUBLIC_SPORTSBOOK_API_URL`.

## Hash Confirmed Current
`4fcab2e9b286b7b14db66c66280a38bceab9effed830e3a805e833d7ce8cac0b` for `CompetitionPageSectionLinesTabNode` — confirmed in live JS bundle `index-ab5134e6e9bdcfaf.js` (1.26MB) in the hash manifest object. The hash is current; the problem is the schema.

## Schema Gap: 37 Errors, Not 1
The prior session's "35 fixed, 1 remaining" was measured against the wrong endpoint (got 405). Against the real endpoint with all feature flags properly false:

- `Team` type: lost `abbreviation`, `colour1`, `logos`
- `Player` type: lost `initials`, `jerseyImage`, `numberImage`, `headshots`, `country`, `teams`
- `Country` type: removed entirely
- `RecommendedProp*` types (3): removed
- `Interaction` and all subtypes (6): removed
- `BetSelector`, `AvatarView`, `MarketCardUI`: removed
- `BaseballLiveInfo`, `EventParticipant`, possession indicators (5): removed
- `GridMarketCard.ui` + `oddsFormat` arg: removed

Total schema errors: 37. `data` field is absent from all responses — full rejection, no partial data.

**Why:** Schema underwent major refactoring while the persisted query document stored server-side (by hash) references the old types. GraphQL validates the stored document on every execution.

## Correct Required Variables
```js
{
  sectionId: "<node-relay-id>",  // ID! — the ONLY required non-boolean variable; NOT competitionSlug
  includeRichEvent: false,       // Boolean! required
  oddsFormat: "AMERICAN",        // OddsFormat! required
  selectedFilterId: null,        // nullable in practice
  pageType: "PAGE",              // PageType enum — may have changed
}
```

## How to Get sectionId
Only available from `CompetitionPage(canonicalUrl: "/mlb")` → `page.pageChildren[].id` where `archetype === "CompetitionLines"`. That query returns 403 without auth. In the browser (Tampermonkey), auth is already present — hook fetch to capture the CompetitionPage response and extract `sectionId`.

## Recommended Fix: Fetch Interceptor
Don't replay the query from scratch. The schema is too far from the stored document. Instead, hook `window.fetch` in the Tampermonkey script to intercept the site's own `CompetitionPageSectionLinesTabNode` responses — the browser already has auth, correct `sectionId`, and the server may serve authenticated users differently.

## JS Bundle Structure
- 7 chunks total (small build)
- `index-ab5134e6e9bdcfaf.js` (1.26MB) contains all queries, hash manifest, and app logic
- Source map returns 404
- Hash manifest is a JSON-like object: `{"OperationName":"hash",...}` at one contiguous location in the bundle
