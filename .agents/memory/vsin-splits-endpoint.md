---
name: VSIN Splits endpoint
description: How data.vsin.com/betting-splits serves public betting splits (handle% / bets%)
---

## Finding
`data.vsin.com/betting-splits` is a genuine SSR page (older jQuery/Bootstrap/DataTables platform, separate subdomain from the Piano-paywalled editorial site `vsin.com/betting-splits/`). **No auth, no cookies, no Playwright.** Full splits table embedded directly in the HTML. Confirmed 2026-08-01.

**Why `splits_history.php` doesn't work:**
The `splits_history.php?gamecode=X&source=DK` endpoint returns the full WordPress homepage (335KB) — it's paywalled. The main splits table on the page itself is the free data.

## Parsing
```
GET https://data.vsin.com/betting-splits
```
- Find `<tr class="sp-row ...">` elements inside `<tbody>`
- Each game = 2 consecutive rows: road team + home team
- Road row: button has `class="sp-act-history"`, data-gamecode on the button
- Home row: button has `class="sp-act-count"`, data-gamecode on button, button text = VSiN pick count

## Cell layout (11 cells total per row)
| # | Content | Notes |
|---|---------|-------|
| 0 | action button | `data-gamecode="YYYYMMDD{SPORT}{ID}"` |
| 1 | team name | `a.sp-team-link` |
| 2 | spread line | `span.sp-badge-line` |
| 3 | spread handle% | `span.sp-badge` |
| 4 | spread bets% | `span.sp-badge` |
| 5 | total line | `span.sp-badge-line` |
| 6 | total handle% | `span.sp-badge` |
| 7 | total bets% | `span.sp-badge` |
| 8 | ML line | `span.sp-badge-line` |
| 9 | ML handle% | `span.sp-badge` |
| 10 | ML bets% | `span.sp-badge` |

## Gamecode format
`20260731MLB00019` → date=`20260731` (8 chars), sport=`MLB` (variable width), game_id=`00019` (5 chars)
Sport extraction: `gc[8:-5]` (everything between date and last 5 chars)

## Majority-handle indicator
`span.sp-badge-green` marks the side with >50% handle. Parser records raw % regardless.

## Output file
`betcouncil_vsin_splits.json` — produced by `scripts/vsin_splits_refresh.py`
Consumer: `fetch_vsin_splits_from_gist(sport)` in `fetchers.py` (added 2026-08-01)

## Distinct from existing vsin data
`betcouncil_vsin_{SPORT}.json` = **line data** (Vegas book lines from `data.vsin.com/vegas-odds-linetracker/`), harvested by `scripts/vsin_harvester.py`. The new splits file is entirely separate.
