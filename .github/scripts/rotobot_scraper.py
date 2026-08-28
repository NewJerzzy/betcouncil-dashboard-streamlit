import requests
import json
import os
import random
import time
import urllib.request
import urllib.error
from datetime import datetime

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
GIST_FILENAME = "rotobot_data.json"


def push_gist(content: str, gist_token: str) -> None:
    payload = json.dumps({"files": {GIST_FILENAME: {"content": content}}}).encode()
    for attempt in range(1, 5):
        req = urllib.request.Request(
            f"https://api.github.com/gists/{GIST_ID}",
            data=payload,
            method="PATCH",
            headers={
                "Authorization":        f"Bearer {gist_token}",
                "Accept":               "application/vnd.github+json",
                "Content-Type":         "application/json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                resp = json.loads(r.read())
            updated = list(resp.get("files", {}).keys())
            print(f"Gist updated: {updated}")
            return
        except urllib.error.HTTPError as exc:
            if exc.code in (409, 429) and attempt < 4:
                wait = (2 ** attempt) * 5 + random.uniform(0, 5)
                print(f"Gist push HTTP {exc.code} (attempt {attempt}/4) — retrying in {wait:.1f}s")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("push_gist: all 4 attempts exhausted")


supabase_url = "https://ardonyjjtwljfzszhcko.supabase.co/rest/v1/"
supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
gist_token   = os.getenv("PICK6_GIST_TOKEN")

supabase_headers = {"apikey": supabase_key, "Authorization": f"Bearer {supabase_key}"}

data = {"metadata": {"updated": datetime.utcnow().isoformat()}}

tables = ["props", "model_edges", "model_predictions"]
for t in tables:
    r = requests.get(supabase_url + t, headers=supabase_headers, params={"limit": 300})
    if r.ok:
        data[t] = r.json()
        print(f"Fetched {len(data[t])} rows from {t}")
    else:
        print(f"Warning: {t} returned HTTP {r.status_code}")

content = json.dumps(data, separators=(",", ":"))
push_gist(content, gist_token)
print("RotoBot refresh completed")
