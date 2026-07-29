---
name: Pick6 Props Pipeline
description: Architecture and known constraints for the DraftKings Pick6 props scraper/pipeline
---

## How it works (as of 2026-07-29)

**Scraper:** `scripts/pick6_refresh.py` — GitHub Actions cron (every 30 min, workflow ID 308390698)
- Fetches `https://pick6.draftkings.com/?sport={sport}` for 9 sports
- Extracts SSR stream via `streamController.enqueue("...")` regex
- Parses the flat array (3000–8000 elements) using `_resolve_refs` to build props
- Pushes to **`betcouncil_pick6_props.json`** in Gist 7e52e1c2c2054847c7c4663a157386c5

**Important filename fix:** The gist is at 300 files (GitHub's hard cap). `pick6_props_live.json` can't be created (no room). The scraper uses `betcouncil_pick6_props.json` (already exists). `fetchers.py` line 15970 and the HARVESTER_SOURCES registry at line 15777 both point to that same file.

**App side:** `_pf_dk_pick6()` in `app_core.py` calls `fetch_pick6_props_from_gist(sport)` which reads `betcouncil_pick6_props.json`. Result flows into `dk_pick6_props_raw` → `st.session_state["dk_pick6_props"]` → props fallback chain at line 15121.

## Known hard constraint: player names

**Confirmed 2026-07-29:** The Pick6 SSR stream has NO player display names. Player names are fetched client-side via XHR after React hydration. Tried:
- All dicts in the array (none have name + dkId together)
- DK DFS lobby + draftables API (all 404 from Actions runner — DraftGroupIds 146757, 151375–151410 are stale/invalid)
- `api.draftkings.com/players/v1/players` (404)
- `pick6.draftkings.com/api/pick6/v1/players` (404 — returns full HTML page)
- `api.draftkings.com/pick6/v1/entities` (404)

**Result:** Player field is `dkId_639885` style placeholder. Real names require either: (a) a browser session with valid DK auth to capture the XHR, or (b) discovering a working public DK API endpoint.

## Token constraint

The workflow uses `PICK6_GIST_TOKEN_2` which is a collaborator, not the gist owner. It can UPDATE existing files but NOT create new ones. Always push to pre-existing filenames.

## Stat names DO resolve from SSR

`pickSixMarketId` → `name` (stat label) works correctly via `_build_lookup_tables`. The market name (e.g., "Hits + Runs + RBIs") comes from the SSR stream.
