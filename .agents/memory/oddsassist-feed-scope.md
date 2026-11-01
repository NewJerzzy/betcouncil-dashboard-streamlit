---
name: OddsAssist feed scope
description: Public feed observations and constraints for evaluating OddsAssist in the Lab.
---

Use OddsAssist only where it supplies missing information; avoid importing another complete odds, EV, or arbitrage board.

**Why:** The user requested live-data testing but explicitly does not want redundancy or bloat. Public expert picks provide original directional recommendations rather than another calculation of existing sportsbook prices. Distinct branding alone does not establish statistical independence.

**How to apply:** Evaluate expert picks separately before adding scoring weight. Preserve the originally published line, decimal price, units, creation time, event time, result, and source pick ID; never replace the original selection with a different current best line. Provider units are not Lab stake recommendations.

Public observations verified on 2026-11-01:

- The public `/picks` page supplies expert selections and graded history without login. Its Remix loader route `/picks.data?_routes=routes%2F_main.picks` returned HTTP 200 and serialized records under `routes/_main.picks.data.picks`.
- This is internal Remix single-fetch/turbo-stream serialization, not ordinary JSON objects or a documented/versioned developer API. Array references and tagged Dates need proper decoding. Prefer an owner-maintained JSON contract for durable integration.
- Public frontend modules reference `/api/competitions/{competition}/events` with `from`/`to`, `/api/markets?marketKey=...`, and `/api/advantages/{type}`. Finding a route does not verify valid parameters, entitlement, completeness, or freshness.
- Anonymous advantage probes returned HTTP 200 with empty arrays even while the public middles page displayed preview rows. Do not interpret those responses as proof that no opportunities exist or attempt to circumvent account gating.
- Site terms require permission for automation. The user describes the site as theirs; use their authorized API/export path for continued integration rather than bypassing account controls.
- Current public documentation describes sports tools as free, with a free account unlocking fuller access; paid Prediction Markets Pro is a separate product. Do not equate the word Pro with paid sports-pick access.
