---
name: PickFinder integration scope
description: Defines when PickFinder data is useful to BetCouncil without duplicating the existing prop pipeline.
---

PickFinder is an owner-authorized source, but do not ingest its complete live prop board into BetCouncil. Most visible fields and prices duplicate existing BetCouncil sources or calculations.

**Why:** Duplicate ingestion would increase fetch time, storage, matching work, and board noise without adding a new directional signal. The useful gaps are middle-detection inputs and, if consistently defined, L15 hit rate, streak context, and MLB pitcher innings context.

**How to apply:** Prefer a small owner-provided internal API over scraping. Request only typed missing fields keyed by sport, event, player, market, line, and timestamp. Keep source timestamps and metric definitions. Do not import duplicate EV, arb, discrepancies, implied probabilities, app prices, alt lines, L5/L10, H2H, defense, or season fields.