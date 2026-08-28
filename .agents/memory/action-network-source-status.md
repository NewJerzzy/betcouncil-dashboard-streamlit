---
name: Action Network source status
description: Current distinction between usable Action Network game data and unavailable projection/public-split paths.
---

Action Network's public v1 scoreboard still returns scheduled games, and its sport-suffixed public-betting route returns live public-split payloads for active slates. The current response stores books and outcomes below `game.markets[bookId].event`, not the older `game.odds[bookId].event` shape expected by the project. Its player-projection route returns HTTP 200 with an empty `playerProps` array; Action Network's own NFL projection page states that projections versus market are for PRO subscribers.

**Why:** These are separate products/routes. Treating all Action Network data as down would discard working game metadata and publicly available ticket/money splits, while treating empty projections as an ordinary no-slate result hides a paid-data/access dependency.

**How to apply:** Do not use Action Network projections as a live model input without authorized PRO/export access. Keep its scoreboard as a distinct game-line source. Parse public splits from the current `markets` shape and preserve missing NFL preseason markets as missing—not zero—not-interest.