"""One-off: runs the NFL load headless, then finds every prop/line mentioning a
fixed list of players across ALL loaded sources. Writes betcouncil_headless_props_check.json."""
import json, os, sys, traceback
from datetime import datetime, timezone
import requests
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NAMES = ["walker", "seahawks", "giants", "chiefs", "dart", "kenneth"]
out = {"started": datetime.now(timezone.utc).isoformat(), "errors": [], "hits": {}, "board": []}
def finish():
    txt = json.dumps(out, indent=1, default=str)
    print(txt[:5000])
    try:
        r = requests.patch("https://api.github.com/gists/7e52e1c2c2054847c7c4663a157386c5",
            headers={"Authorization": "Bearer " + os.environ.get("GITHUB_TOKEN", "")},
            json={"files": {"betcouncil_headless_props_check.json": {"content": txt}}}, timeout=30)
        print("gist", r.status_code)
    except Exception as e:
        print("gist fail", e)
try:
    import streamlit as st
    import app_core as ac
    board = ac.load_sport_data("NFL")[0]
    out["board"] = [{k: v for k, v in p.items() if isinstance(v, (str, int, float, bool, type(None)))} for p in (board or [])]
    def scan(key, val):
        items = val if isinstance(val, list) else (list(val.values()) if isinstance(val, dict) else [])
        found = []
        for it in items:
            try:
                s = json.dumps(it, default=str).lower()
            except Exception:
                continue
            if any(n in s for n in NAMES) and any(t in s for t in ("pass", "rush", "rec", "yard", "catch", "point", "total", "team")):
                found.append(it if len(s) < 700 else s[:700])
        if found:
            out["hits"][key] = found[:25]
    for k in list(st.session_state.keys()):
        try:
            scan(k, st.session_state[k])
        except Exception:
            pass
except Exception:
    out["errors"].append(traceback.format_exc()[-1500:])
finish()
