---
name: Edge Sniper app access
description: What the public Edge Sniper share link exposes and the boundary for data-access work.
---

The public Edge Sniper share link opens an email/Google access gate on a Glide application. Its unauthenticated HTML and app manifest expose only generic Glide/Firebase client infrastructure and PWA assets, not prediction, odds, or props data. An authenticated browser capture showed Glide `channel` requests carrying session-specific `gsessionid` query values, but no app-specific REST endpoint or response payload was included. No official public API documentation or APIDog project was found.

**Why:** A browser-visible Glide runtime is not a usable data API. Session-bearing channel URLs are sensitive and ephemeral; replaying or sharing them is unsafe and would not establish a lawful, durable data source.

**How to apply:** Treat Edge Sniper as a product reference unless the owner provides an authorized account and a documented export/API permission. Do not bypass the access gate, replay session URLs, or ingest the app's proprietary predictions into BetCouncil's model. If a future network capture is shared, redact cookies, `gsessionid`, authorization headers, and tokens first.