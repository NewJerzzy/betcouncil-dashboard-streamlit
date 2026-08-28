---
name: Outlier.bet access
description: Access boundary, documented methodology, and naming distinction for the Outlier.bet analytics product.
---

Outlier.bet is a paid sports-betting analytics app. Its public client bundle identifies `api.outlier.bet` and authenticated player-prop routes, but unauthenticated requests return authorization errors. No public developer API, export program, GitHub integration, or Outlier-specific APIDog project was found.

**Why:** The public bundle exposes the shape of a private client API, not permission to retrieve or reuse Outlier's proprietary odds, fair values, or recommendations.

**How to apply:** Do not add Outlier.bet as a production feed unless its owner provides written API/export access. Its documented ideas—multi-book devig, configurable sharp-book weighting, movement charts, and prop filters—can be treated as product-reference patterns. In this project, the existing EVSharps endpoint called `outliers` is unrelated to Outlier.bet and must not be labeled as an Outlier.bet integration.