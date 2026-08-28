---
name: BallparkPal source status
description: Publicly documented MLB projection API, coverage, and licensing limits
---

BallparkPal offers an authenticated API at `www.ballparkpal.com/api/v1` with game/team/player catalogs, modeled probabilities, simulated averages, game park factors, and hitter park factors. It does not provide sportsbook odds, weather forecasts, or historical projections. Access requires an active subscription, manual approval, and an API key; the documented 2026 beta limit is 15,000 requests per month. The stated license permits personal, non-commercial use only and disallows powering a public/shared app without separate permission.

**Why:** It can supply an independent MLB projection vote, but it overlaps with BetCouncil's existing MLB, park, and weather inputs and cannot by itself provide the historical ledger needed for pattern grading.

**How to apply:** If used, collect future snapshots in a private shadow test, compare against BetCouncil and closing lines, cap its ensemble weight until calibrated, and obtain commercial permission before exposing its data in a public BetCouncil product.