import json, os, sys, requests, traceback

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    token = os.environ.get("GITHUB_TOKEN")
    sys.path.insert(0, "scripts")
    import importlib.util
    spec = importlib.util.spec_from_file_location("wg", "scripts/wiseguyteam_refresh.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    results = {}
    for sport_slug in list(mod.SPORTS.keys())[:3]:
        try:
            raw = mod.fetch_sport(sport_slug)
            games_raw = raw.get("games", [])
            results[sport_slug] = {"raw_type": str(type(raw)), "games_type": str(type(games_raw)),
                                     "num_games": len(games_raw) if hasattr(games_raw, "__len__") else None}
            if games_raw:
                g0 = games_raw[0]
                results[sport_slug]["game0_type"] = str(type(g0))
                try:
                    normalized = mod.normalize_game(sport_slug, g0)
                    results[sport_slug]["normalize_ok"] = True
                except Exception as e:
                    results[sport_slug]["normalize_error"] = str(e)
                    results[sport_slug]["normalize_trace"] = traceback.format_exc()[:1000]
                    results[sport_slug]["game0_sample"] = json.dumps(g0, default=str)[:500]
        except Exception as e:
            results[sport_slug] = {"error": str(e), "trace": traceback.format_exc()[:1000]}

    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_bettingpros_debug.json": {"content": json.dumps({"note": "TEMP wiseguy diag", "results": results}, default=str)}}},
    )
    print("push:", resp.status_code)
    return 0

if __name__ == "__main__":
    sys.exit(main())
