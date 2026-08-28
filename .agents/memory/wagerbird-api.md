---
name: WagerBird paywalled picks API
description: app.wagerbird.com has an open /api/picks endpoint but all picks have unlocked:false — pick direction is the paid product
---

## Architecture
- Marketing: `wagerbird.com` (Next.js App Router)
- Terminal SPA: `app.wagerbird.com` (Vite + Laravel PHP backend)
- WebSocket: `ws.wagerbird.com` (Laravel Reverb, Pusher-compatible)

## Open endpoints
- `GET app.wagerbird.com/api/picks` — 200 JSON, 57 311 historical picks, all `"values":{"unlocked":false}`
- `GET app.wagerbird.com/api/picks?sport=mlb` — sport filter (lowercase only) works
- `GET app.wagerbird.com/api/games/{uuid}` — game details (teams, score, sport)
- `GET app.wagerbird.com/api/games/{uuid}/picks` — per-game picks, all locked
- `GET app.wagerbird.com/api/sports` — sport list with inSeason flags

## Auth-required (401 with Accept:application/json)
`/api/events`, `/api/schedule`, `/api/board`, `/api/terminal`, `/api/leagues`

## WebSocket
- Key: `f23xuooqfukpjfo7jbtq`, host: `ws.wagerbird.com:443`
- All public channels (`picks`, `board`, `board.mlb`, `games`, `results`, `public`) subscribe with 200
- No events broadcast between games — Reverb fires events only when picks are published/updated

## Why it's a dead end
The `values.unlocked` field contains the pick direction (which team/side/over-under). It's always false for unauthenticated users. No query param (date, sort, order, unlocked=true, free=1) changes this. WagerBird's product IS the pick direction — it's behind a $39-79+/mo paywall.

The free picks at `wagerbird.com/picks` are YouTube video breakdowns, not a JSON endpoint.

**Why:** Knowing a pick EXISTS on a market with +14% EV is not actionable without the direction.
