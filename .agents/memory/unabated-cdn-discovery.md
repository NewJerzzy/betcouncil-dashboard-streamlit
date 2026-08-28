---
name: Unabated CDN — open endpoints, no auth
description: data.unabated.com went 401; the real open feed is content.unabated.com CDN; sharp anchors unblurred; NRFI lines confirmed live.
---

## The Dead Endpoint (old script pointed here — now 401)
- `data.unabated.com/bettype` → 401
- `data.unabated.com/market/{sport}/props/odds` → 401
- `data.unabated.com/market/{sport}/straight/odds` → 401

## The Live CDN (no auth, sharp anchors UNBLURRED even anonymously)
```
https://content.unabated.com/markets/v2/league/{league_id}/odds.json?v={ts_ms}
```
- Add `?v={epoch_ms}` cache-buster (same pattern callancapitolo17/NFLWork uses)
- Standard Referer + User-Agent headers only

## Legacy snapshot (also still open, 41MB)
```
https://content.unabated.com/markets/game-odds/b_gameodds.json
```
Has `propsPeopleEvents` key but MLB props section is empty in practice; use v2 per-league files instead.

## League IDs (confirmed 2026-08-13)
| ID | Sport | Notes |
|----|-------|-------|
| 1  | NFL   | 2,081 rows, preseason live |
| 2  | NCAAF | 688 rows |
| 3  | NBA   | 135 rows (offseason future lines) |
| 4  | CBB   | 94 rows |
| 5  | **MLB** | **5,822 rows — full daily slate** |
| 6  | NHL   | 282 rows |
| 7  | WNBA  | 373 rows |
| 9  | ATP Tennis | 1,213 rows + people map |
| 10 | WTA Tennis | 1,689 rows + people map |
| 12 | Intl Baseball | 79 rows |
| 21 | Soccer | 193 rows |
| 8, 13–20 | 404 |

## MLB Period Types (pt keys in `odds` dict)
| Key  | Period           |
|------|-----------------|
| pt1  | Full game (ML/Spread/Total) |
| **pt11** | **1st inning — NRFI/YRFI** |
| pt12–pt19 | Innings 2–9 |
| pt20 | First 5 (F5) |
| pt26 | First 3 innings |
| pt27 | First 7 innings |

## V2 Response Shape
```json
{
  "odds": {
    "lg5:pt1:pregame": [
      {
        "eventId": 108546,
        "eventStart": "2026-08-15T23:15:00",
        "eventName": "Royals Kansas City @ Angels Los Angeles",
        "betTypeId": 3,
        "sides": {
          "si0:tid{away_id}": { "ms7": {"americanPrice": -111, "points": 0.5, "isBlurred": false, "modifiedOn": "..."} },
          "si1:tid{home_id}": { "ms7": {"americanPrice": -107, "points": 0.5, "isBlurred": false} }
        }
      }
    ]
  },
  "people": {},
  "marketSources": [...],
  "teams": {}
}
```
- `si0` = away (YRFI/over), `si1` = home (NRFI/under) for 1st inning totals — confirmed 2026-08-13
- `isBlurred: false` on all sharp-book lines with no token

## Key Source IDs (confirmed from live data)
| ID | Book | Sharp? |
|----|------|--------|
| 7  | Sharp Book Price (true line) | ✅ |
| 6  | Circa | ✅ |
| 8  | Bookmaker | ✅ |
| 49 | Unabated | ✅ |
| 58 | Pinnacle - Delayed | ✅ |
| 68 | Circa Sports | ✅ |
| 1  | DraftKings | — |
| 2  | FanDuel | — |
| 4  | BetMGM | — |
| 20 | Caesars | — |
| 36 | TheScore US | — |
| 78 | Bet365 | — |
| 72 | PrizePicks | DFS |
| 73 | Underdog | DFS |
| 84 | DK Pick6 | DFS |

## What We Wired
- `scripts/unabated_refresh.py` — fully rewritten 2026-08-13 to use CDN
- Outputs: `betcouncil_unabated_straight_{SPORT}.json`, `betcouncil_unabated_nrfi_mlb.json`, `betcouncil_unabated_props_{SPORT}.json`
- Workflow: `.github/workflows/unabated_refresh.yml` — runs every 15 min, unchanged
- New fetchers: `fetch_unabated_nrfi()`, `get_nrfi_sharp_price()` in fetchers.py
- HARVESTER_REGISTRY entry: `"unabated_nrfi"` → `betcouncil_unabated_nrfi_mlb.json`

## Partner API (paid, ~$30/mo)
```
https://partner-api.unabated.com/v2/markets/gameOdds?x-api-key=KEY
https://partner-api.unabated.com/v2/markets/playerProps?x-api-key=KEY
https://partner-api.unabated.com/v2/markets/changes?x-api-key=KEY
```
Auth: `?x-api-key=YOUR_KEY` query param (NOT Authorization header).
Confirmed from vsintools/MLB-Odds UNABATED_API_README.md on GitHub.

**Why:** The CDN gives game lines + NRFI for free. The Partner API adds
player props (full, not just DFS) and the delta/changes feed. Subscribe
only if player prop volume or latency becomes a bottleneck.
