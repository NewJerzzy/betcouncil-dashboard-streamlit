---
name: DoinkSports source status
description: Public architecture clues, upstream providers, and access limits
---

DoinkSports is a Next.js research app whose public game pages are server-rendered. Its frontend calls a separate `stats.doinkapis.com` JSON service. Public, unauthenticated GETs were confirmed for the MLB slate, game metadata, game state, and weather forecast; the slate includes free-game IDs and game/provider mappings. Public page output also identifies upstream mappings for Odds API, OddsBlaze, Unabated, and Sportradar, plus a Supabase project used at least for public assets. The visible `/research/...` paths are human-facing pages, not the API contract.

The NFL service also exposes `/v1/leagues/nfl/games/{gameId}/box-score` for public historical game IDs. Its response includes game odds (spread, total, favorite), team settlement stats, quarter/half scoring, first touchdown, and detailed player outcomes such as rushing, receiving, targets, touchdowns, red-zone usage, shares, and quarter splits. Directly guessed `/odds`, `/player-props`, `/team-props`, `/touchdowns`, `/sides`, `/injuries`, and similar suffixes returned 404; current market lines and matchup factors remain unconfirmed as separate JSON.

As of August 27, 2026, ESPN listed NFL preseason games while Doink's `/v1/leagues/nfl/games/slate` returned HTTP 200 with an empty slate. Tested alternate identifiers such as `nfl_preseason` and `nfl-preseason` returned "League not found"; the supported league code is `nfl`, so the discrepancy is likely Doink's current feed coverage rather than a missing preseason slug.

Sportradar's official NFL API v7 documentation confirms full play-by-play coverage for preseason and documents schedules, box scores, statistics, play-by-play, rosters, and weekly injuries. The documented trial endpoints use `https://api.sportradar.com/nfl/official/trial/v7/en/...` with an `x-api-key`; unauthenticated schedule, current-season schedule, and injury requests returned HTTP 403. No Sportradar Replit connector or project credential is configured.

**Why:** The stats service is technically useful for understanding the data model and coverage, but DoinkSports' terms prohibit automated or non-human access. The useful discovery is the provider mix, API shape, and NFL product structure—not an automatically reusable DoinkSports feed.

**How to apply:** Use only permitted public access and obtain written permission before any scheduled connector. Source equivalent data directly from authorized providers—especially evaluate licensed Sportradar or OddsBlaze access—while continuing to use existing Odds API and Unabated integrations.