"""
Inspect RotoBot Supabase tables — dumps schemas and sample rows
to identify where picks/edges data lives.
"""
import requests, json, os, sys

key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
BASE = "https://ardonyjjtwljfzszhcko.supabase.co/rest/v1/"
H = {"apikey": key, "Authorization": "Bearer " + key, "Accept": "application/json"}

TABLES = ["notifications", "profiles", "feature_flags", "Rotobot AI Contact Form"]

for table in TABLES:
    resp = requests.get(BASE + table, headers=H, params={"limit": 3}, timeout=15)
    if resp.ok:
        rows = resp.json()
        print(f"\n=== {table} ({resp.headers.get('content-range','?')} rows total) ===")
        if rows:
            print("Keys:", list(rows[0].keys()))
            for r in rows[:2]:
                print(json.dumps(r, indent=2, default=str)[:600])
        else:
            print("  (empty)")
    else:
        print(f"\n=== {table} — {resp.status_code}: {resp.text[:100]} ===")

# Also check if there's an auth.users table accessible via Supabase admin API
print("\n\n=== auth.users (admin API) ===")
resp2 = requests.get(
    "https://ardonyjjtwljfzszhcko.supabase.co/auth/v1/admin/users",
    headers={"apikey": key, "Authorization": "Bearer " + key},
    params={"per_page": 3},
    timeout=15,
)
if resp2.ok:
    data = resp2.json()
    users = data.get("users", [])
    print(f"Total users: {data.get('total',0)}")
    for u in users[:2]:
        print(f"  email: {u.get('email','?')} | id: {u.get('id','?')[:8]}... | created: {u.get('created_at','?')[:10]}")
else:
    print(f"  {resp2.status_code}: {resp2.text[:100]}")
