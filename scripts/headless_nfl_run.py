"""One-off: runs the real NFL board pipeline headless (no Streamlit UI) and
writes ranked props + game lines to the Gist file
betcouncil_headless_nfl_run.json so results can be read without opening the app."""
import json, os, sys, traceback, time
from datetime import datetime, timezone
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
out = {"started": datetime.now(timezone.utc).isoformat(), "errors": []}

def done():
    out["finished"] = datetime.now(timezone.utc).isoformat()
    print(json.dumps(out, indent=1, default=str)[:6000])
    tok = os.environ.get("GITHUB_TOKEN", "")
    try:
        r = requests.patch(
            "https://api.github.com/gists/7e52e1c2c2054847c7c4663a157386c5",
            headers={"Authorization": f"Bearer {tok}"},
            json={"files": {"betcouncil_headless_nfl_run.json":
                  {"content": json.dumps(out, indent=1, default=str)}}}, timeout=30)
        print("gist write", r.status_code)
    except Exception as e:
        print("gist write failed", e)

try:
    import app_core as ac
    t0 = time.time()
    res = ac.load_sport_data("NFL")
    board, games, n_def, n_edge, home_teams, away_teams = res
    out["load_seconds"] = round(time.time() - t0, 1)
    out["n_board"], out["n_games"] = len(board or []), len(games or [])
    def slim(p):
        keys = ("player","prop","line","side","tier","edge","prob","Team","team","opponent","book","odds","avg","NFLInjuryImpactNote","Matchup","game")
        return {k: p.get(k) for k in keys if k in p}
    ranked = sorted(board or [], key=lambda p: abs(p.get("edge", 0) or 0), reverse=True)
    out["top_props"] = [{k: v for k, v in p.items() if isinstance(v, (str, int, float, bool, type(None)))} for p in ranked[:40]]
    try:
        ga = ac.analyze_all_games(games, "NFL", home_teams, away_teams)
        out["game_lines"] = ga if isinstance(ga, list) else str(type(ga))
        if isinstance(ga, list):
            out["game_lines"] = ga[:40]
    except Exception:
        out["errors"].append("analyze_all_games: " + traceback.format_exc()[-800:])
except Exception:
    out["errors"].append(traceback.format_exc()[-1500:])
done()
