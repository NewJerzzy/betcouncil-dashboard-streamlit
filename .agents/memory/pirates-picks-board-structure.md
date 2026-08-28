---
name: Pirates Picks board structure
description: What an authorized Pirates Picks board capture reveals about its visible product and model outputs.
---

The board endpoint returns a JSON object whose main `cards` value is server-rendered HTML. The visible product organizes picks into convergence/trust plays and a ranked master list, with market categories, confidence tiers, historical rolling windows, sample sizes, unit results, confidence-interval floors, contextual reads, and multi-book price/deep-link cards. Network transfer sizes around 33 KB can expand to roughly 613 KB of decompressed JSON because the response is compressed. Repeated captures were the same full board snapshot except for capture time and an incrementing odds-age counter, not delta updates. The briefing text explicitly defines TRUST as an odds-aware ROI 95% CI lower bound above zero, WATCH as a positive lean whose CI straddles zero, NEGATIVE as non-positive mean, and NOISE as fewer than 10 decisions; SOLID is an in-sample peak/regression warning rather than a stronger tier. Convergence uses distinct backers and separates source-count cohorts. The capture exposes finished outputs and decision rules, not upstream providers or exact scoring formulas.

**Why:** The product can be used as a feature reference for an independent BetCouncil presentation and scoring layer, but the HTML is not evidence that its private model or provider contracts are reproducible.

**How to apply:** Analyze only authorized, sanitized captures. Recreate general concepts with BetCouncil’s own public/licensed data and formulas; do not replay sessions, bulk-scrape the subscription service, or copy proprietary model logic.