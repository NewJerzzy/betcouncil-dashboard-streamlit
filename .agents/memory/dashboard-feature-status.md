---
name: Dashboard feature status
description: Confirmed-built features that stale code comments or TODOs may misrepresent as missing
---

## Problem pattern
Old TODO comments and inline notes describing pre-fix history remain in the code after fixes are applied. Reading these as current state produces false "gaps." Always verify against actual implementation, not comments.

## Confirmed built and wired (as of 2026-08-03)

| Feature | Location | Notes |
|---------|----------|-------|
| `build_game_line_consensus` | `bc_utils.py` | Real 18-book reputation-weighted consensus; fixed July 16 (twice). Old comment documents pre-fix history. |
| `fetch_nfl_defensive_ratings` | `fetchers.py` | Real implementation using `pts_against_pg` as defensive proxy |
| `fetch_atsstats_*_matchups` (×4) | `fetchers.py` | All four stubbed (return `{}`) — not undefined |
| `fetch_parlaysavant_props` | `fetchers.py` | Clean stub returning `{}`; dead-code block was PaddyPower code, not parlaysavant |
| BetQL player props | verified live | Real response data confirmed in prior session |
| DK Pick6 stat mapping | live | 48,602 props resolving real names via working endpoint |
| Bobby's Bets UI | `app_core.py` | Wired into Predictions, Summary, Game Lines, Line Shop |
| VSIN splits display | `app_core.py` | Dedicated display in Game Lines |
| LineStar | `app_core.py` | Wired into Player Lookup with salary/prop data |
| VegasInsider display | `app_core.py` | Live display widget in Game Lines |
| WiseGuyTeam `wgt_play` flag | `app_core.py` | Surfaced in Predictions tab and Verdict badge |

## Deliberately not built
- DailyFantasyFuel fetcher — redundant with existing sources, intentionally skipped
- RotoBot — auth-gated, intentionally disabled (explicit comment in workflow)

## Confirmed built 2026-08-03 (sidebar additions)
- Persistent sidebar with sport selector (sets `last_sport` default across all tabs)
- Steam moves indicator in sidebar (reads session_state; only populated after Full Board loads)
- Most Bet Tonight section using BetQL community data (independently callable)

## Confirmed built — corrected 2026-08-04 (previously flagged as gaps, all wrong)
- **EVSharps props** — all 11 EVSharps functions are wired; 16 harvester entries. The "props gap" was a naming artifact like "WiseBets" — the feature was never called that internally.
- **One-tap bet logging** — the "🔒 Lock" button already exists on Full Board cards (and 3+ other places); uses `active_unit()`, writes to Locks & Ledger, feeds into history/calibration/CLV pipeline. Nothing to build.
- **System tab** — accurately identified as visible to all users, but NOT safely fixable: `st.tabs()` shows every tab unconditionally; hiding one tab would require rebuilding the entire navigation paradigm. Same category as 14→7 consolidation — architecturally blocked, not worth forcing.

## Genuine open gaps
None confirmed as of 2026-08-04. All audited items either already exist or are architecturally blocked.

## Confirmed built — UI audit corrections 2026-08-04
- **Full Board sort** — already exists: Sort by BQ Score / Edge% / L5 Hit% / Line / Reliability; real `sort_map`, real caption confirmation
- **Tier filter** — in the primary filter bar above the board, NOT buried in sidebar
- **Charting library** — `st.line_chart` already in use; "no charting library at all" was false

## Fixed and pushed 2026-08-04 (UI improvements)
- Tier badges: 11px / 1px padding → 13px / 3px 9px padding
- Card hover state: extended to cover actual 10px/12px card radii (existing rule only matched unused 8px)

## Declined UI changes — real architectural reasons
- **Odds pill chips**: odds formatted inline across dozens of locations, no shared function; partial fix would create visual inconsistency worse than current uniform state
- **Sparklines / P&L charts**: require historical data storage infrastructure that doesn't exist
- **Push alerts**: Streamlit is pull-based; no true push path exists
- **Pick sharing, global search, SVG icons, sport-color palette, simplified mode**: all new infrastructure or design-direction calls, not scoped fixes

## Audit failure pattern — updated 2026-08-04
Four consecutive audit rounds produced false positives on the same codebase:
- Invented feature names not present in the code ("WiseBets", "EVSharps props gap")
- Declared features missing that already exist under different names ("Lock" button = one-tap logging; Full Board sort; tier filter in primary bar)
- Proposed fixes that are architecturally blocked (`st.tabs()` tab hiding, Streamlit push alerts)
- Flagged "no charting library" when `st.line_chart` was already in use
**Rule: grep for the actual implementation before declaring anything missing or broken. This codebase has a consistent pattern of more being built than surface reading suggests.**

## GameLinePicks.com API — confirmed 2026-08-04
- `/api/picks/today` — genuinely free, no auth, real +EV moneyline picks with reasoning strings
- `/api/arbitrage/today` — NOT free; response contains `"limited":true,"trialActive":true` — PRO feature at $9.99/mo, do not integrate
- Belongs in **Predictions tab** (same pattern as SignalOdds/BetQL/Pickswise), NOT Game Lines
- Per-pick track record (result, profitUnits, CLV) is available and worth surfacing

## Tab facts — do not guess
- Tab count is 15 (not 14)
- "New Bettor" was renamed to "Pick For You" — do not reference old name
- Tab 12 is SharpTrack, Tab 13 is Market Scanner
- Verdict sources are: WiseGuyTeam, SignalOdds, BetQL, Pickswise — "WiseBets" does not exist

**Why:** Do not trust TODO/stub comments as ground truth on whether something is built. Cross-reference against actual function implementations in `fetchers.py` and `bc_utils.py`.
