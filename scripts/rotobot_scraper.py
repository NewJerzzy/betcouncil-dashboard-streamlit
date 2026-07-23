"""
RotoBot scraper — auto-discovers tables from Supabase schema,
fetches all of them, writes to repo + pushes to GitHub Gist.
"""
import requests, json, os, sys, urllib.request
from datetime import datetime, timezone

key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
if not key:
    print("ERROR: SUPABASE_SERVICE_ROLE_KEY not set", file=sys.stderr)
    sys.exit(1)

BASE_URL = "https://ardonyjjtwljfzszhcko.supabase.co/rest/v1/"
HEADERS  = {
    "apikey": key,
    "Authorization": "Bearer " + key,
    "Accept": "application/json",
}

# ── Step 1: discover available tables from the OpenAPI spec ───────────────
print("Discovering tables from Supabase schema...")
try:
    resp = requests.get(BASE_URL, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    spec = resp.json()
    paths = spec.get("paths", {})
    # paths look like {"/table_name": {...}, "/rpc/fn_name": {...}}
    tables = sorted([p.strip("/") for p in paths if not p.startswith("/rpc")])
    print(f"  Found tables: {tables}")
except Exception as e:
    print(f"ERROR: could not fetch schema: {e}", file=sys.stderr)
    sys.exit(1)

if not tables:
    print("ERROR: no tables found in schema", file=sys.stderr)
    sys.exit(1)

# ── Step 2: fetch each table (up to 300 rows each) ───────────────────────
data = {}
for table in tables:
    resp = requests.get(
        BASE_URL + table,
        headers=HEADERS,
        params={"limit": 300},
        timeout=30,
    )
    if resp.ok:
        rows = resp.json()
        data[table] = rows
        print(f"  {table}: {len(rows)} rows")
    else:
        print(f"  WARNING: {table} HTTP {resp.status_code} — skipping", file=sys.stderr)

if not data:
    print("ERROR: fetched zero tables successfully", file=sys.stderr)
    sys.exit(1)

# ── Step 3: write local file (committed to repo by workflow) ──────────────
with open("rotobot_data.json", "w") as f:
    json.dump(data, f, indent=2)
print("rotobot_data.json written")

# ── Step 4: push to Gist (feeds BetCouncil model engine) ─────────────────
gist_token = os.getenv("GIST_TOKEN")
if not gist_token:
    print("WARNING: GIST_TOKEN not set — skipping Gist push", file=sys.stderr)
else:
    envelope = {
        "source": "rotobot",
        "captured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tables_fetched": tables,
        **data,
    }
    payload = json.dumps({
        "files": {
            "betcouncil_rotobot_data.json": {"content": json.dumps(envelope, indent=2)}
        }
    }).encode()
    req = urllib.request.Request(
        "https://api.github.com/gists/7e52e1c2c2054847c7c4663a157386c5",
        data=payload,
        method="PATCH",
        headers={
            "Authorization": f"Bearer {gist_token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        print(f"Gist updated: HTTP {r.status}")
