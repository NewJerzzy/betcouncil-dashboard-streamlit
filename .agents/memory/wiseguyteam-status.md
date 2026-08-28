---
name: WiseGuyTeam status
description: What's working, what's paywalled, and how the Gist issue was resolved
---

## What's fully working (as of 2026-08-03)
- Endpoint: `https://inngest-worker.memberservice.workers.dev/sharp-report?sport={sport}`
- No auth, no cookies, standard User-Agent only
- Returns: bet%, handle%, sharp_side, big_money_side per market (ML/spread/total)
- 10 sports covered: MLB, NFL, NBA, NHL, UFC, WNBA, SOCCER, CFB, CBB, TENNIS
- Confirmed live with real fresh data 2026-08-03 (7 sports active in-season)
- Free data is wired into Predictions tab and Verdict badge
- `wgt_play: true/false` flag surfaced in both Predictions tab and Verdict badge (confirmed)

## Gist issue — resolved
- Problem was the 300-file cap blocking new per-sport files
- Solution: merged all WiseGuyTeam sports into `betcouncil_evbets_combined.json` (already existed)
- Did NOT use the PATCH-rename trick — merging was simpler and cleaner
- Verified live 2026-08-03

## What's genuinely paywalled — cannot be scraped
- WiseGuyTeam's specific named play (their actual recommendation — which side to bet)
- The open API only ever returns aggregate sharp_side/big_money_side flags, never the named play
- Confirmed by endpoint inspection: no play direction field exists in the free response
- This requires a membership; no workaround exists

**Why this matters:** `wgt_play: true/false` (whether WGT has a play tonight) is public. The *direction* of that play is not. Do not conflate the two — the flag is already surfaced in the dashboard; the direction is a dead end without payment.
