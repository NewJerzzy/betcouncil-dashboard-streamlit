"""
RotoBot scraper — fetches from Supabase and pushes to GitHub Gist.
Runs inside GitHub Actions via rotobot_refresh.yml.
"""
import requests, json, os, sys, urllib.request
from datetime import datetime, timezone

# ── Supabase fetch ────────────────────────────────────────────────────────
key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
if not key:
    print("ERROR: SUPABASE_SERVICE_ROLE_KEY not set", file=sys.stderr)
    sys.exit(1)

BASE_URL = "https://ardonyjjtwljfzszhcko.supabase.co/rest/v1/"
HEADERS  = {"apikey": key, "Authorization": "Bearer " + key}
TABLES   = ["props", "model_edges", "model_predictions"]

data = {}
for table in TABLES:
    resp = requests.get(BASE_URL + table, headers=HEADERS, params={"limit": 300}, timeout=30)
    if resp.ok:
        data[table] = resp.json()
        print(f"  {table}: {len(data[table])} rows")
    else:
        print(f"ERROR: {table} HTTP {resp.status_code}: {resp.text[:200]}", file=sys.stderr)
        sys.exit(1)

# ── Write local file (committed to repo by workflow) ──────────────────────
with open("rotobot_data.json", "w") as f:
    json.dump(data, f, indent=2)
print("rotobot_data.json written")

# ── Push to Gist (feeds BetCouncil model engine) ──────────────────────────
gist_token = os.getenv("GIST_TOKEN")
if not gist_token:
    print("WARNING: GIST_TOKEN not set — skipping Gist push", file=sys.stderr)
else:
    envelope = {
        "source": "rotobot",
        "captured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
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
