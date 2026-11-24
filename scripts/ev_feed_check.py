"""One-off: hits the EV API feed directly and reports status + props by sport."""
import json, os, sys, collections
import requests
from datetime import datetime, timezone
out = {"started": datetime.now(timezone.utc).isoformat()}
try:
    r = requests.get("https://api-production-3a3b.up.railway.app/api/ev", timeout=30)
    out["status"] = r.status_code
    out["bytes"] = len(r.content)
    d = r.json() if r.status_code == 200 else {}
    items = d.get("data") or []
    out["n_items"] = len(items)
    out["updated"] = d.get("updated")
    out["by_prop"] = collections.Counter(i.get("prop") for i in items).most_common(40)
    out["by_src_sport"] = collections.Counter(i.get("_source_sport") for i in items).most_common()
    out["top_keys"] = list(d.keys())[:15]
    out["sample"] = items[:2]
    out["body_head"] = r.text[:300] if r.status_code != 200 else ""
except Exception as e:
    out["error"] = str(e)[:300]
txt = json.dumps(out, indent=1, default=str)
print(txt[:3000])
r = requests.patch("https://api.github.com/gists/7e52e1c2c2054847c7c4663a157386c5",
    headers={"Authorization": "Bearer " + os.environ.get("GITHUB_TOKEN", "")},
    json={"files": {"betcouncil_ev_feed_check.json": {"content": txt}}}, timeout=30)
print("gist", r.status_code)
