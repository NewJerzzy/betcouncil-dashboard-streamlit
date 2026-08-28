---
name: EVSharps + BookMaker.eu open endpoints
description: Confirmed open, no-auth API endpoints for EVSharps and BookMaker.eu scrapers — schema, book codes, URL patterns
---

## EVSharps (api-production-3a3b.up.railway.app)

**Base:** `https://api-production-3a3b.up.railway.app/api/{sport}`
**Auth:** None. Public Railway-hosted API.

### Endpoints
- `/api/mlb` — all MLB prop types (strikeouts, walks, etc.); response is `{updated, games, times, props, data[]}`
- `/api/nba` — NBA props (off-season returns `[]` directly, not `{data:[]}`)
- `/api/nfl` — NFL props (off-season returns `[]` directly, not a dict)
- `/api/ev` — HR dingers EV analysis (more books, fairVal, Kelly); already covered by `evsharps_dingers_harvester.py`

**Why:** `/api/{sport}` returns a list when off-season, a dict when in-season — handle both cases.

### data[] item shape
```
{dt, key, prop, game, player, pos, bookOdds, team, opp, oppRank, book, line, handicap,
 bats, under, hitRates{szn/lyr/L5/L10/L20}, ouIdx, logs, bpp, bppProj, bppDiff,
 playerFactor, roof, pitcherLR, pitcher, weather, batter_percs, percs, bvp, lastHR, ph,
 order, stadiumRank, stadiumRankLeft, stadiumRankRight, homerLogs, savant, pitcherData,
 links, liquidity, ev, fairVal, implied, kelly, ou}
```

### Book abbreviation codes (bookOdds keys)
`kal`=Kalshi `fd`=FanDuel `dk`=DraftKings `hr`=HardRock `hr_oh`=HardRock(OH)
`bv`=Bovada `br`=BetRivers `fn`=Fanatics `mgm`=BetMGM `cz`=Caesars
`fl`=Fliff `re`=BetRivers(alt) `bol`=BetOnline `nv`=Novig `circa`=Circa
`espn`=ESPN/theScore `pn`=Pinnacle `kambi`=Kambi `px`=ProphetX

### Gist files
- `betcouncil_evsharps_props_MLB.json` — all MLB props from `/api/mlb` (new)
- `betcouncil_evsharps_dingers_MLB.json` — HR props from `/api/ev` (existing)
- `betcouncil_evsharps_ev_MLB.json` — EV analysis from `/api/ev` (existing)

**Script:** `scripts/evsharps_refresh.py`

---

## BookMaker.eu (lines.bookmaker.eu)

**Base:** `https://lines.bookmaker.eu/en/sports/{sport}/`
**Auth:** None. Server-rendered HTML. gzip-encoded.

### URL paths
- `baseball` → MLB run lines, totals, ML
- `basketball` → NBA spread, total, ML
- `football` → NFL spread, total, ML
- `hockey` → NHL

### HTML structure
Single `<table class='oddsTable'>` per page. Two rows per game:
- Row 1 (5 cells): `[time, away_team, spread_away, total, ml_away]`
- Row 2 (4 cells): `[home_team, spread_home, total, ml_home]`
- Sub-header rows (1 cell): league name like `MLB` or `NFLMelbourne...`
- Time format: `8/011:10pmPT` (needs parsing: `M/DDH:MMam/pmTZ`)
- Fractions: `½` used in lines, replace with `.5`

**Why:** Sharp offshore book; widely used as a reference line alongside Pinnacle.

**Script:** `scripts/bookmaker_refresh.py`
**Gist file:** `betcouncil_bookmaker_game_lines.json`
**Dead file used for rename:** `betcouncil_bettingpros_snapshot_debug.json`
