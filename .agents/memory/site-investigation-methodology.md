---
name: Site investigation methodology
description: Required steps for investigating any site for API endpoints or data access — four parallel approaches, apidog always included
---

When investigating any site for an API, backend, or data endpoints, run all four approaches — in parallel where possible.

## The four approaches (all required)

### 1. Framework & infrastructure recon
- Fetch main page HTML: response headers (Server, X-Powered-By, CF-Ray, X-Vercel-Id), title, meta, framework detection
- DNS sweep: main domain + common subdomains (api, app, backend, data, auth, cdn, ws, realtime, status, docs, staging); always probe a nonsense subdomain to detect wildcard DNS
- Subdomain HTTP probe: GET / with Accept: application/json on every resolved subdomain

### 2. JS bundle analysis
- Fetch every chunk referenced in the HTML (Vite `/assets/*.js`, Next.js `/_next/static/chunks/*.js`)
- Extract: all non-noise URLs, `/api/` paths, `fetch()`/`axios()` calls, `baseUrl`/`apiUrl`/`endpoint` configs, NEXT_PUBLIC_ / process.env refs, WebSocket (`wss://`) URLs, BaaS config (Supabase `createClient`, Firebase `initializeApp`, Clerk `publishableKey`, etc.)
- For Next.js App Router: also fetch the webpack runtime to extract chunk IDs; try RSC payloads via `Accept: text/x-component` + `RSC: 1` headers

### 3. Direct API probing
- robots.txt disallow list (reveals real route prefixes)
- sitemap.xml (all public routes)
- Well-known: `/openapi.json`, `/swagger`, `/graphql`, `/api/health`, `/api/status`
- Auth provider routes: `/api/auth/session`, `/api/auth/providers` (NextAuth), `/.well-known/openid-configuration`
- tRPC: `/api/trpc`
- REST guesses derived from feature copy, pricing page, help articles
- For every 401: try different HTTP methods (GET/POST/OPTIONS) and query params — error messages may leak schema info
- `/books/*.png` or similar static asset paths often enumerate supported entities

### 4. GitHub / apidog approach (ALWAYS required)
Search GitHub code for:
- `"<domain>/api"` — direct API URL references
- `"<domain>" fetch OR axios` — client code calling the API
- `"<domain>" openapi OR swagger OR postman` — documentation collections
- Confirmed endpoint names: `"api/sharp" <sitename>`, etc.
- Build IDs / chunk hashes from the bundles (someone may have cached/decompiled)
- `"<domain>" scrape OR reverse` — existing reverse-engineering work
- Search GitHub repositories for the site/company name
- Wayback Machine CDX: `http://web.archive.org/cdx/search/cdx?url=<domain>/api/*&output=json&limit=50&fl=original,statuscode&collapse=urlkey`

**Why:** Even when the site itself yields nothing, GitHub often contains Postman collections, client libraries, scrapers, or disclosed API docs that short-circuit the investigation entirely.

## Dead-end signals
- Wildcard DNS + no subdomain responds → fake infrastructure
- All JS bundles are pure framework/vendor code with no app strings → RSC/SSR, app code never reaches browser
- robots.txt has no `/api/` disallow → no REST API
- GitHub: zero results across all query variants → no community tooling, newly launched or obscure product
- Wayback: no `/api/*` crawls → API has never been publicly indexed
