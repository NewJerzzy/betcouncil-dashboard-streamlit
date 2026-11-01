---
name: Betting Insider live scope
description: Authorized live website data, historical API boundaries, and expert-admission requirements.
---

The user describes this site as theirs and explicitly needs live data and expert picks to test and upgrade it, not just historical data. They only want additions that fill Lab gaps and picks with a proven track record.

**Why:** They do not want redundant odds boards, unverified expert votes, noise, or an observation-only trial they must manage.

**How to apply:** Retrieve current selections from the live website routes and independently check previous picks before admitting an expert. Keep original selections and prices separate from current market references. Do not treat source labels, social counts, promotional profit claims, or a positive win rate alone as verified evidence.

External API findings verified 2026-11-01:

- `/api/picks/list?mode=all` on the website returns pending selections, including futures; it is not the whole historical ledger.
- The `/picks` date selector uses `/api/picks/list?mode=today&date=YYYY-MM-DD`, which returned graded history even when `/api/picks/month-summary` returned empty calendar summaries. An empty calendar is not evidence of no historical picks.
- `/api/games/upcoming?sport=nfl` and `sport=ncaaf` return current website markets, betting splits, and signal records. Filter by actual kickoff and match event identity; returned lists can include stale fixtures.
- Upcoming-game spreads/totals may lack accompanying prices, and `sportsbook=Consensus` is not an executable bookmaker quote. Retrieval time is not a provider quote-update timestamp.
- The biggest-movers response can put totals into fields named `currentSpread` and `openingSpread`. Do not consume it as a spread-only feed without market-type validation.
- Some pick titles describe half-game bets even when `bet_type=total`; titles must also be checked. Team totals without an identified team are not independently gradable from the displayed selection.
- `https://api.thebettinginsider.com/v1/openapi.json` is a real public OpenAPI specification. The developer REST API and hosted MCP provide completed-game historical data only, require an API key, and do not include live picks/splits/props. Website membership and developer API access are separate.
- No matching standalone Postman/Apidog collection or public GitHub implementation was located. The actual OpenAPI specification is the more reliable reference.
