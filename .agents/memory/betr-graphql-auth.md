---
name: Betr GraphQL auth
description: Betr picks.betr.app GraphQL endpoint — open for introspection but player prop projections require bearer token
---

## Endpoint
`https://api.fantasy.betr.app/graphql`

## Required headers (all requests, even unauthenticated)
```
channel: MOBILE_WEB
fantasy-api-version: 15.0
fantasy-application-version: 3.38.6
jurisdiction: CA
```

## What works without auth
- Full schema introspection (`__schema`, `__type`)
- `getLeagueConfigs` — returns enabled leagues (MLB, NBA, NFL, NHL, UFC, PGA, etc.)
- `getUpcomingEventsV2(league: League!)` — returns event IDs, dates, statuses (no projections)
- `getUpcomingLobbyEventsV2(league: League!)` — same shape

## Schema key facts
- `League` enum values: NBA, NFL, NHL, MLB, PGA, UFC, CFB, CBB, WNBA, MLS, EPL, UCL, WCC, LLG, L1F, FWC, SEA, CSGO, LOL, DOTA, WCBB, WTA, ATP, VALORANT, COD, BUN
- `EventV2` is an **INTERFACE**; concrete types: `TeamVersusEvent`, `TeamTournamentEvent`, `IndividualVersusEvent`, `IndividualTournamentEvent`
- `TeamVersusEvent` has `teams` but NO `players` field
- Player projections live on `Player.projections: [Projection]` but only accessible when authenticated
- `getEventsWithFilteredPlayers` requires both `eventIds` AND `playerIds` — no way to get playerIds without auth
- `Projection` type has `type: ProjectionType`, `playerRecentStats: PlayerRecentStats`, `nonRegularPercentage`, `nonRegularValue`
- `ProjectionType` enum: BOOSTED, REGULAR, SPECIAL, SUPER_BOOSTED, MINI_BOOSTED, FREE_PICK, EDGE_1..4, ANCHOR, NUKE, BOOSTED_4

## Auth path
Bearer token required. No anonymous token mint found (the `Startup` operation mentioned in scrapers doesn't exist in this schema version). Need a real Betr account + login flow.

**Why:** Betr is a DFS pickem platform; prop lines are the product, so they're gated behind auth to prevent mass scraping without an account.
