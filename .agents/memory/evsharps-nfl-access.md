---
name: EVSharps NFL access
description: Access boundaries and payload roles for EVSharps NFL endpoints.
---

EVSharps has live NFL props and touchdown views, but their frontend sends a legitimate Supabase Bearer session to retrieve those boards. Without an authorized session, the live NFL and touchdown responses are empty; the same applies to the useful movement feed in practice.

The anonymous NFL Analysis/Results response contains historical prop rows with outcome/result fields, fair values, EV, odds, logs, and opponent context. It is suitable only for evaluating past records if use is authorized, not for generating current-game recommendations.

**Why:** NFL page availability does not mean there is an open, fresh NFL prediction feed. Mixing a completed-results table into the live board would create stale or look-ahead-biased signals.

**How to apply:** Keep using the existing public EVSharps feeds where they are already supported. Only add live NFL/TD data after EVSharps grants appropriate API/export access; do not reuse browser sessions or treat Results/Analysis data as live odds.