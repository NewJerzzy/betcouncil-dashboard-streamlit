---
name: EVBets endpoint
description: How evbets.app serves its value-bet data and how to parse it
---

## Finding
`evbets.app` is an Astro SSR app hosted on Cloudflare Pages. All bet data is **server-rendered directly into the HTML response** — no browser / Playwright / JavaScript execution needed. Confirmed 2026-08-01 via live AFL signal.

**Why it looks like a SPA:**
- The bundle `/_assets/page.BuNOqHnL.js` (389 chars) is just a Sentry debug-ID stub, not the app bundle
- No `<astro-island>` components, no XHR endpoints from the HTML
- Cloudflare headers confirm fresh origin computation per request: `cfOrigin;dur=594`, `cf-cache-status: EXPIRED`

## Discovery flow
1. `GET https://evbets.app/value-bets` — the hub page lists all sports with active bets in `vbh-sport-card` elements with `vbh-sport-count` (e.g. "1 signal"). Sports with zero bets are absent entirely.
2. For each active sport: `GET https://evbets.app/value-bets/{sport-slug}`
3. Parse `<table class="vb-table" id="vb-main-table">` tbody rows

## Bet row structure (confirmed live AFL 2026-08-01)
```html
<tr data-ev="0.524" data-bm="betfair" data-market="h2h" data-odds="1.210" data-hours="0.6">
  <td>1</td>
  <td><a href="...">Event Name</a></td>
  <td>Outcome/Team</td>
  <td><span class="market-tag">h2h</span></td>
  <td>1.21</td>        <!-- decimal odds -->
  <td><a href="...">Betfair ↗</a></td>
  <td><span class="ev-chip ev-chip--low">+0.52%</span></td>
  <td>$6</td>          <!-- Kelly $1k -->
  <td class="countdown-cell" data-commence="2026-08-01T03:35:16+00:00"></td>
</tr>
```

Key: `data-commence` is on the `<td>` tag itself, NOT inner HTML — search `row_html` directly.

## Encoding gotcha
`requests` defaults to latin-1 for HTML responses without explicit charset, producing mojibake on non-ASCII glyphs (↗ becomes â†—). **Always decode explicitly:**
```python
text = resp.content.decode("utf-8", errors="replace")
```

## "No bets" state
When no bets for a sport, the page embeds: `"No X value bets right now · check back soon"` — parser returns empty list, NOT an error.

## Sport slugs (71 total in sitemap)
Key ones: `baseball-mlb`, `basketball-nba`, `american-football-nfl`, `hockey-nhl`, `mma-mixed-martial-arts`, `basketball-wnba`, `soccer-epl`, `aussierules-afl`

## Output file
`betcouncil_evbets_combined.json` — produced by `scripts/evbets_refresh.py`
Consumer in `app_core.py`: reads `st.session_state["evbets_ev_picks"]` (set in the post-parallel-batch block around line 13845, same pattern as Unabated props).
