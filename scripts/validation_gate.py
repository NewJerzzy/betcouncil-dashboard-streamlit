"""
validation_gate.py -- nothing changes a pick's tier or weight until it passes this.

Reads (Gist):  betcouncil_third_party_calibration.json (expert/comparison sources, aligned pairs),
               betcouncil_board_grading_history.json + betcouncil_game_board_grading_history.json
               (BetCouncil's own tiers, incl. CLV).
Writes (Gist): betcouncil_validation_gate.json  {name: {status, n, ...}}

Rules (same spirit as the Replit Research Lab gate):
  * under MIN_N graded decisions            -> INSUFFICIENT (never promoted)
  * chronological split: first 70% train, last 30% fixed holdout
  * PASS only if on the holdout ALL hold:
      Brier(claimed prob) < Brier(train base rate)      (adds information)
      |mean claimed prob - hit rate| <= CAL_TOL          (calibrated)
  * otherwise FAIL. Status is advisory data; code that wants to use a source/signal
    calls bc_utils.signal_gate_allows(name).
"""
import json, os, sys
from datetime import datetime, timezone
import requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
MIN_N = 100
CAL_TOL = 0.05


def log(m): print(f"[validation_gate] {m}", flush=True)


def gist_read(token, fn):
    r = requests.get(f"https://api.github.com/gists/{GIST_ID}",
                     headers={"Authorization": f"Bearer {token}"}, timeout=30)
    f = r.json().get("files", {}).get(fn)
    if not f:
        return None
    if f.get("truncated"):
        return requests.get(f["raw_url"], timeout=60).json()
    return json.loads(f["content"])


def brier(pairs):
    return sum((p - h) ** 2 for p, h, *_ in pairs) / len(pairs)


def evaluate(pairs):
    pairs = [x for x in pairs if isinstance(x[0], (int, float)) and 0 < x[0] < 1]
    n = len(pairs)
    if n < MIN_N:
        return {"status": "INSUFFICIENT", "n": n, "need": MIN_N}
    pairs.sort(key=lambda x: str(x[2] or ""))
    cut = int(n * 0.7)
    train, hold = pairs[:cut], pairs[cut:]
    base = sum(h for _, h, *_ in train) / len(train)
    b_src = brier(hold)
    b_base = sum((base - h) ** 2 for _, h, *_ in hold) / len(hold)
    mp = sum(p for p, *_ in hold) / len(hold)
    hr = sum(h for _, h, *_ in hold) / len(hold)
    ok = b_src < b_base and abs(mp - hr) <= CAL_TOL
    return {"status": "PASS" if ok else "FAIL", "n": n, "holdout_n": len(hold),
            "brier_source": round(b_src, 4), "brier_baseline": round(b_base, 4),
            "mean_prob": round(mp, 4), "hit_rate": round(hr, 4)}


def evaluate_flat(flags):
    """Sources with no probability claim (named-expert ATS/total/prop picks priced ~-110):
    PASS only if the 95% Wilson lower bound on hit rate beats the 52.38% breakeven."""
    n = len(flags)
    if n < MIN_N:
        return {"status": "INSUFFICIENT", "n": n, "need": MIN_N}
    w = sum(flags); p = w / n; z = 1.96
    lo = (p + z*z/(2*n) - z*((p*(1-p)/n + z*z/(4*n*n)) ** 0.5)) / (1 + z*z/n)
    return {"status": "PASS" if lo > 0.5238 else "FAIL", "n": n, "hit_rate": round(p, 4),
            "wilson_lower_95": round(lo, 4), "breakeven": 0.5238}


def main():
    token = os.environ["GITHUB_TOKEN"]
    out = {}
    cal = gist_read(token, "betcouncil_third_party_calibration.json") or {}
    for src, st in cal.items():
        pairs = st.get("pairs") or []
        flags = st.get("actual_hit_flags") or []
        if not pairs and flags and src in ("sportsline", "fantasylabs", "bettinginsider"):
            out[f"source:{src}"] = evaluate_flat(flags)
            continue
        res = evaluate(pairs) if pairs else {"status": "INSUFFICIENT", "n": 0, "need": MIN_N,
                                             "note": "pairs start accumulating from the first grading run after this update"}
        out[f"source:{src}"] = res
    # BetCouncil's own props tiers: claimed prob vs outcome
    hist = gist_read(token, "betcouncil_board_grading_history.json") or {}
    by_tier = {}
    for day, rows in hist.items():
        for r in rows:
            if r.get("outcome") in ("WIN", "LOSS") and isinstance(r.get("prob"), (int, float)):
                by_tier.setdefault(r.get("tier") or "?", []).append([r["prob"], 1 if r["outcome"] == "WIN" else 0, day])
    for t, pairs in by_tier.items():
        out[f"own_props_tier:{t}"] = evaluate(pairs)
    # BetCouncil game lines: hit rate + CLV
    g = gist_read(token, "betcouncil_game_board_grading_history.json") or {}
    rows = [r for d in g.values() for r in d]
    clv = [r["clv_ev"] for r in rows if isinstance(r.get("clv_ev"), (int, float))]
    pts = [r["clv_pts"] for r in rows if isinstance(r.get("clv_pts"), (int, float))]
    wl = [r for r in rows if r.get("outcome") in ("WIN", "LOSS")]
    out["own_game_lines"] = {
        "n_graded": len(wl), "wins": sum(1 for r in wl if r["outcome"] == "WIN"),
        "clv_n": len(clv) + len(pts),
        "avg_clv_ev": round(sum(clv) / len(clv), 4) if clv else None,
        "pct_beat_close": round(100 * (sum(1 for x in clv if x > 0) + sum(1 for x in pts if x > 0)) / (len(clv) + len(pts)), 1) if (clv or pts) else None,
        "status": "INSUFFICIENT" if len(clv) + len(pts) < 30 else ("PASS" if (sum(1 for x in clv if x > 0) + sum(1 for x in pts if x > 0)) / (len(clv) + len(pts)) > 0.5 else "FAIL"),
    }
    out["_meta"] = {"generated": datetime.now(timezone.utc).isoformat(), "min_n": MIN_N, "cal_tol": CAL_TOL}
    r = requests.patch(f"https://api.github.com/gists/{GIST_ID}",
                       headers={"Authorization": f"Bearer {token}"},
                       json={"files": {"betcouncil_validation_gate.json": {"content": json.dumps(out, indent=1)}}}, timeout=60)
    log(f"gist write {r.status_code}")
    for k, v in out.items():
        if k != "_meta":
            log(f"{k}: {v.get('status')} n={v.get('n', v.get('n_graded'))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
