# BetCouncil Dashboard

Streamlit dashboard aggregating sports betting data from multiple open/unauthenticated sources.

## Project overview
- `app_core.py` — main Streamlit app
- `fetchers.py` — data fetchers for each source (HTTP, cached to pkl)
- `.agents/memory/` — persistent agent memory (topic files indexed by MEMORY.md)

## User preferences

**Site API investigation methodology:** When investigating any site for an API, backend, or data endpoints, ALWAYS run all four approaches in parallel:
1. **Framework & infrastructure recon** — page HTML, response headers, DNS sweep (including wildcard check), subdomain probe
2. **JS bundle analysis** — fetch every chunk, extract URLs, `/api/` paths, fetch/axios calls, env vars, auth provider patterns, WebSocket URLs, BaaS config (Supabase/Firebase/Clerk/etc.)
3. **Direct API probing** — robots.txt disallow list, well-known paths, NextAuth/tRPC/GraphQL routes, REST guesses from feature names, HTTP method variants, query param leak testing
4. **GitHub / apidog approach** — GitHub code search for the domain, API paths, build IDs, chunk hashes, Postman/OpenAPI/Swagger collections, client code using the API, Wayback Machine CDX for crawled API paths

The apidog approach (step 4) must always be included — not optional.
