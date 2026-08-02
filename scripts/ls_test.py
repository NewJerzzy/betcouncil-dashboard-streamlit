import json, os, sys, traceback, requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    token = os.environ.get("GITHUB_TOKEN")
    import importlib.util
    spec = importlib.util.spec_from_file_location("ls", "scripts/linestar_harvester.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    result = {}
    try:
        import datetime as dt
        captured_at = dt.datetime.now(dt.timezone.utc).isoformat()
        r = mod.run_sport("MLB", mod.SPORTS["MLB"], captured_at)
        result["run_sport_result_type"] = str(type(r))
        result["run_sport_result_keys"] = list(r.keys()) if isinstance(r, dict) else None
    except Exception as e:
        result["error"] = str(e)
        result["trace"] = traceback.format_exc()

    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_bettingpros_debug.json": {"content": json.dumps({"note": "TEMP linestar run_sport test", "result": result}, default=str)}}},
    )
    print("push:", resp.status_code)
    return 0

if __name__ == "__main__":
    sys.exit(main())
