"""
sharptrack_harvester.py — SharpTrack (Polymarket sharp-wallet tracker)
=======================================================================
Runs every 15 min via .github/workflows/sharptrack_refresh.yml.

Pipeline:
  1. Pull Polymarket's SPORTS + ESPORTS leaderboard (data-api.polymarket.com
     /v1/leaderboard) across WEEK / MONTH / ALL time periods, orderBy=PNL.
     Merge + rank-score every wallet seen -> "sharp wallet registry".
  2. Pull live/upcoming sports events from gamma-api.polymarket.com/events
     for a fixed set of sport tag slugs, take the highest-volume markets,
     collect their conditionIds.
  3. Pull recent trades for those markets in one batched call
     (data-api.polymarket.com/trades?market=id1,id2,...) and keep only
     trades whose proxyWallet is in the sharp registry and whose timestamp
     falls inside the lookback window.
  4. Cluster plays by (conditionId, outcomeIndex): 2+ distinct sharp
     wallets on the same side within the window = a flagged cluster.
  5. For the highest-scoring plays, pull the CLOB order book
     (clob.polymarket.com/book?token_id=...) to derive a simple
     bid/ask-imbalance "market maker sentiment" read.
  6. Score every wallet (1-100) and every play (1-100), push two files to
     the shared Gist:
       betcouncil_sharptrack_wallets.json  (registry snapshot)
       betcouncil_sharptrack_live.json     (plays + clusters snapshot)

No API key required — all endpoints used here are Polymarket's public,
unauthenticated read endpoints.
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone
from collections import defaultdict
import random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

DATA_API = "https://data-api.polymarket.com"
GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"

# BetCouncil sports -> best-effort Polymarket gamma tag slugs.
# Any slug that returns zero events is skipped silently (off-season, or
# Polymarket hasn't listed markets for it yet) rather than erroring.
SPORT_TAG_IDS = {
    # Verified against gamma-api.polymarket.com/sports (per-sport "tags" field)
    # and cross-checked against gamma-api.polymarket.com/tags.
    # NOTE: Polymarket's own docs warn that ?tag_slug=... on /events is
    # unreliable and silently falls back to unfiltered/default ordering —
    # confirmed empirically (tag_slug=nba returned unrelated politics/
    # election events, zero NBA content). Numeric tag_id is the only
    # reliable filter; do not revert to tag_slug.
    "NFL":    [450],
    "NBA":    [745],
    "WNBA":   [100254],
    "MLB":    [100381],
    "NHL":    [899],
    "TENNIS": [864],
    "SOCCER": [100350],
    "ESPORTS": [64],   # parent esports tag (covers CS2/Valorant/LoL/Dota2/etc.)
    # MMA/UFC has no dedicated numeric tag_id in Polymarket's sports metadata
    # (only generic "1"/"100639") as of this harvester's last check — omitted
    # rather than risk pulling the unfiltered/generic sports bucket again.
}

LOOKBACK_SECONDS = 2 * 60 * 60          # only trades from the last 2 hours
MAX_TRACKED_MARKETS = 60                # cap the batched /trades call
MAX_ORDER_BOOK_LOOKUPS = 20             # cap CLOB book calls per run
CLUSTER_MIN_WALLETS = 2
MIN_WALLET_SCORE_TO_TRACK = 35          # floor for "sharp" classification
LEADERBOARD_PERIOD_WEIGHTS = {"WEEK": 1.0, "MONTH": 0.6, "ALL": 0.4}


def log(msg):
    print(f"[sharptrack] {msg}", flush=True)


def _http_get_json(url, params=None, timeout=15, retries=2):
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    last_err = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "betcouncil-sharptrack/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            last_err = e
            time.sleep(0.6 * (attempt + 1))
    log(f"  GET failed ({url[:80]}...): {last_err}")
    return None


# ── Step 1: sharp wallet registry ──────────────────────────────────────
def fetch_leaderboards():
    """Merge SPORTS + ESPORTS leaderboards across WEEK/MONTH/ALL into a
    per-wallet weighted rank score. Returns dict[address] -> raw record."""
    wallets = {}
    for category in ("SPORTS", "ESPORTS"):
        for period, weight in LEADERBOARD_PERIOD_WEIGHTS.items():
            data = _http_get_json(f"{DATA_API}/v1/leaderboard", {
                "category": category,
                "timePeriod": period,
                "orderBy": "PNL",
                "limit": 50,
            })
            if not isinstance(data, list):
                continue
            for i, entry in enumerate(data):
                addr = (entry.get("proxyWallet") or "").lower()
                if not addr:
                    continue
                rank_points = (51 - (i + 1)) * weight  # rank 1 -> 50pts, decaying
                rec = wallets.setdefault(addr, {
                    "address": addr,
                    "userName": entry.get("userName", ""),
                    "profileImage": entry.get("profileImage", ""),
                    "verifiedBadge": False,
                    "rank_points": 0.0,
                    "best_pnl": 0.0,
                    "best_vol": 0.0,
                    "periods_seen": set(),
                })
                rec["rank_points"] += rank_points
                rec["verifiedBadge"] = rec["verifiedBadge"] or bool(entry.get("verifiedBadge"))
                rec["best_pnl"] = max(rec["best_pnl"], entry.get("pnl", 0) or 0)
                rec["best_vol"] = max(rec["best_vol"], entry.get("vol", 0) or 0)
                rec["periods_seen"].add(f"{category}:{period}")
            log(f"  leaderboard {category}/{period}: {len(data)} entries")
    return wallets


def score_wallets(wallets: dict) -> list:
    """Convert raw rank_points into a 1-100 wallet quality score via
    percentile scaling, plus small bonuses for verification and
    cross-period consistency (showing up in both WEEK and MONTH/ALL cuts
    is a stronger signal than one hot week)."""
    if not wallets:
        return []
    max_points = max(w["rank_points"] for w in wallets.values()) or 1.0
    scored = []
    for w in wallets.values():
        base = (w["rank_points"] / max_points) * 80.0          # 0-80
        consistency_bonus = min(len(w["periods_seen"]), 5) * 2.0  # 0-10
        verified_bonus = 5.0 if w["verifiedBadge"] else 0.0
        roi_bonus = 5.0 if (w["best_vol"] > 0 and w["best_pnl"] / w["best_vol"] > 0.15) else 0.0
        score = round(min(100.0, base + consistency_bonus + verified_bonus + roi_bonus), 1)
        scored.append({
            "address": w["address"],
            "userName": w["userName"],
            "profileImage": w["profileImage"],
            "verifiedBadge": w["verifiedBadge"],
            "best_pnl": w["best_pnl"],
            "best_vol": w["best_vol"],
            "periods_seen": sorted(w["periods_seen"]),
            "score": score,
        })
    scored.sort(key=lambda x: -x["score"])
    return scored


# ── Step 2: live sports markets ────────────────────────────────────────
def fetch_active_sports_markets():
    """Returns list of (conditionId, market_meta) for the highest-volume
    open markets across the configured sport tag IDs."""
    seen_ids = set()
    markets = []
    for sport, tag_ids in SPORT_TAG_IDS.items():
        for tag_id in tag_ids:
            if tag_id in seen_ids:
                continue
            seen_ids.add(tag_id)
            events = _http_get_json(f"{GAMMA_API}/events", {
                "tag_id": tag_id,
                "active": "true",
                "closed": "false",
                "order": "volume24hr",
                "ascending": "false",
                "limit": 15,
            })
            if not isinstance(events, list) or not events:
                continue
            for ev in events:
                for m in ev.get("markets", []) or []:
                    cid = m.get("conditionId")
                    if not cid:
                        continue
                    markets.append({
                        "sport": sport,
                        "conditionId": cid,
                        "question": m.get("question", ""),
                        "eventSlug": ev.get("slug", ""),
                        "volume24hr": m.get("volume24hr", 0) or 0,
                        "clobTokenIds": m.get("clobTokenIds", ""),
                        "outcomes": m.get("outcomes", ""),
                    })
            log(f"  events tag_id={tag_id} ({sport}): {len(events)} events")
    markets.sort(key=lambda x: -x["volume24hr"])
    # de-dupe by conditionId, keep highest volume first
    dedup, out = set(), []
    for m in markets:
        if m["conditionId"] in dedup:
            continue
        dedup.add(m["conditionId"])
        out.append(m)
        if len(out) >= MAX_TRACKED_MARKETS:
            break
    return out


# ── Step 3: trades on those markets, filtered to sharp wallets ─────────
def fetch_trades_for_markets(condition_ids: list):
    if not condition_ids:
        return []
    all_trades = []
    # data-api /trades accepts a comma-separated `market` list
    chunk_size = 20
    for i in range(0, len(condition_ids), chunk_size):
        chunk = condition_ids[i:i + chunk_size]
        data = _http_get_json(f"{DATA_API}/trades", {
            "market": ",".join(chunk),
            "limit": 500,
            "takerOnly": "true",
        })
        if isinstance(data, list):
            all_trades.extend(data)
    return all_trades


# ── Step 5: order book sentiment for top plays ─────────────────────────
def fetch_book_sentiment(token_id):
    book = _http_get_json(f"{CLOB_API}/book", {"token_id": token_id}, timeout=10, retries=1)
    if not book:
        return None
    try:
        bids = book.get("bids", []) or []
        asks = book.get("asks", []) or []
        bid_depth = sum(float(b["size"]) for b in bids[:5])
        ask_depth = sum(float(a["size"]) for a in asks[:5])
        total = bid_depth + ask_depth
        if total <= 0:
            return None
        imbalance = (bid_depth - ask_depth) / total  # -1 (all ask) .. +1 (all bid)
        if imbalance > 0.15:
            label = "bullish (bid-heavy)"
        elif imbalance < -0.15:
            label = "bearish (ask-heavy)"
        else:
            label = "balanced"
        return {
            "imbalance": round(imbalance, 3),
            "label": label,
            "best_bid": bids[0]["price"] if bids else None,
            "best_ask": asks[0]["price"] if asks else None,
            "spread": (round(float(asks[0]["price"]) - float(bids[0]["price"]), 4)
                       if bids and asks else None),
        }
    except (KeyError, ValueError, TypeError, IndexError):
        return None


# ── Scoring & clustering ────────────────────────────────────────────────
def build_plays(trades: list, wallet_score_map: dict, market_meta_by_id: dict):
    now_ts = int(time.time())
    cutoff = now_ts - LOOKBACK_SECONDS
    plays = []
    for t in trades:
        addr = (t.get("proxyWallet") or "").lower()
        wscore = wallet_score_map.get(addr)
        if wscore is None:
            continue
        ts = t.get("timestamp", 0) or 0
        if ts < cutoff:
            continue
        cid = t.get("conditionId", "")
        meta = market_meta_by_id.get(cid, {})
        usd_value = float(t.get("size", 0) or 0) * float(t.get("price", 0) or 0)
        plays.append({
            "wallet": addr,
            "userName": t.get("name") or t.get("pseudonym") or addr[:8],
            "wallet_score": wscore,
            "side": t.get("side", ""),
            "outcome": t.get("outcome", ""),
            "outcomeIndex": t.get("outcomeIndex"),
            "conditionId": cid,
            "asset": t.get("asset", ""),
            "sport": meta.get("sport", ""),
            "title": t.get("title") or meta.get("question", ""),
            "eventSlug": t.get("eventSlug") or meta.get("eventSlug", ""),
            "size": t.get("size", 0),
            "price": t.get("price", 0),
            "usd_value": round(usd_value, 2),
            "timestamp": ts,
            "transactionHash": t.get("transactionHash", ""),
        })

    # cluster by (conditionId, outcomeIndex): flag when >=2 distinct sharp
    # wallets took the same side within the lookback window
    groups = defaultdict(list)
    for p in plays:
        groups[(p["conditionId"], p["outcomeIndex"])].append(p)

    clusters = []
    for (cid, oidx), group in groups.items():
        distinct_wallets = {p["wallet"] for p in group}
        if len(distinct_wallets) >= CLUSTER_MIN_WALLETS:
            avg_score = sum(p["wallet_score"] for p in group) / len(group)
            total_usd = sum(p["usd_value"] for p in group)
            clusters.append({
                "conditionId": cid,
                "outcomeIndex": oidx,
                "title": group[0]["title"],
                "outcome": group[0]["outcome"],
                "sport": group[0]["sport"],
                "wallet_count": len(distinct_wallets),
                "wallets": sorted(distinct_wallets),
                "avg_wallet_score": round(avg_score, 1),
                "total_usd": round(total_usd, 2),
                "trade_count": len(group),
            })
            for p in group:
                p["cluster_wallet_count"] = len(distinct_wallets)

    # bet-size percentile within this run's play set, for scoring
    sizes = sorted(p["usd_value"] for p in plays) or [1]
    def size_pct(v):
        import bisect
        idx = bisect.bisect_left(sizes, v)
        return idx / max(1, len(sizes) - 1) if len(sizes) > 1 else 1.0

    for p in plays:
        cluster_bonus = min(p.get("cluster_wallet_count", 1) - 1, 3) * 5  # up to +15
        size_bonus = size_pct(p["usd_value"]) * 15                        # 0-15
        play_score = round(min(100, p["wallet_score"] * 0.7 + size_bonus + cluster_bonus), 1)
        p["play_score"] = play_score

    plays.sort(key=lambda x: -x["play_score"])
    clusters.sort(key=lambda x: (-x["wallet_count"], -x["avg_wallet_score"]))
    return plays, clusters


def attach_sentiment(plays: list):
    seen_assets = {}
    lookups = 0
    for p in plays:
        asset = p.get("asset")
        if not asset:
            continue
        if lookups >= MAX_ORDER_BOOK_LOOKUPS:
            break
        if asset not in seen_assets:
            seen_assets[asset] = fetch_book_sentiment(asset)
            lookups += 1
        p["market_sentiment"] = seen_assets[asset]


# ── Gist push ────────────────────────────────────────────────────────────
def push_to_gist(key: str, payload: dict) -> bool:
    if not GITHUB_TOKEN:
        log("ERROR: GITHUB_TOKEN not set")
        return False
    body = json.dumps({"files": {key: {"content": json.dumps(payload, indent=2, default=str)}}}).encode()
    for attempt in range(3):
        req = urllib.request.Request(
            f"https://api.github.com/gists/{GIST_ID}",
            data=body,
            method="PATCH",
            headers={
                "Authorization": f"token {GITHUB_TOKEN}",
                "Accept": "application/vnd.github.v3+json",
                "Content-Type": "application/json",
            }
        )
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                if r.status != 200:
                    return False
                resp_body = json.loads(r.read())
                if key in (resp_body.get("files") or {}):
                    return True
                log(f"  Push returned 200 but {key} missing from response -- retrying")
                if attempt < 2:
                    import time as _t
                    _t.sleep(5 * (attempt + 1))
                    continue
                return False
        except urllib.error.HTTPError as e:
            if e.code in (403, 429, 409) and attempt < 2:
                base_wait = 10 * (2 ** attempt)
                wait = base_wait + random.uniform(0, base_wait * 0.4)
                log(f"  Gist push got HTTP {e.code} -- retrying in {wait:.1f}s (attempt {attempt+1}/3)")
                time.sleep(wait)
                continue
            log(f"  Gist push failed: HTTP {e.code} {e.read()[:300]}")
            return False
    return False


def push_merged_to_gist(wallets_payload: dict, live_payload: dict) -> bool:
    """
    Real fix (2026-08-20): the real SharpTrack tab (sharptrack.py) reads
    two standalone files directly -- betcouncil_sharptrack_wallets.json
    and betcouncil_sharptrack_live.json -- never the merged
    betcouncil_sharp_feeds.json this function used to write to.
    Confirmed genuinely broken before this change (the tab's own read
    code never matched this function's write target). The "new-file-
    creation unreliable" issue (2026-08-07) that led to this merge
    workaround is confirmed no longer true -- proven by several new
    dedicated files created successfully on this same Gist earlier
    tonight. Writing directly to both standalone files now, and no lock
    needed -- each file is only ever written by this one script.
    """
    if not GITHUB_TOKEN:
        log("ERROR: GITHUB_TOKEN not set")
        return False

    files_payload = {
        "betcouncil_sharptrack_wallets.json": {"content": json.dumps(wallets_payload, default=str)},
        "betcouncil_sharptrack_live.json": {"content": json.dumps(live_payload, default=str)},
    }
    body = json.dumps({"files": files_payload}).encode()

    for attempt in range(4):
        req = urllib.request.Request(
            f"https://api.github.com/gists/{GIST_ID}", data=body, method="PATCH",
            headers={"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json",
                     "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                if r.status != 200:
                    return False
                resp_body = json.loads(r.read())
                resp_files = resp_body.get("files") or {}
                if all(f in resp_files for f in files_payload):
                    return True
                log("  Push returned 200 but expected files missing from response -- retrying")
        except urllib.error.HTTPError as e:
            if e.code in (403, 429, 409) and attempt < 3:
                wait = 8 * (attempt + 1)
                log(f"  Gist push got HTTP {e.code} -- retrying in {wait}s (attempt {attempt+1}/4)")
                time.sleep(wait)
                continue
            log(f"  Gist push failed: HTTP {e.code}")
            return False
        except Exception as e:
            log(f"  Gist push failed: {e}")
            return False
        if attempt < 3:
            time.sleep(5)
    return False


def run():
    log("Fetching Polymarket SPORTS/ESPORTS leaderboards...")
    raw_wallets = fetch_leaderboards()
    scored_wallets = score_wallets(raw_wallets)
    sharp_wallets = [w for w in scored_wallets if w["score"] >= MIN_WALLET_SCORE_TO_TRACK]
    log(f"  {len(scored_wallets)} unique wallets seen, {len(sharp_wallets)} classified sharp (score>={MIN_WALLET_SCORE_TO_TRACK})")

    if not sharp_wallets:
        log("No sharp wallets found this run — aborting without overwriting live data")
        sys.exit(0)

    wallet_score_map = {w["address"]: w["score"] for w in sharp_wallets}

    log("Fetching active sports markets...")
    markets = fetch_active_sports_markets()
    market_meta_by_id = {m["conditionId"]: m for m in markets}
    log(f"  tracking {len(markets)} markets across configured sports")

    log("Fetching trades for tracked markets...")
    trades = fetch_trades_for_markets([m["conditionId"] for m in markets])
    log(f"  {len(trades)} trades pulled")

    plays, clusters = build_plays(trades, wallet_score_map, market_meta_by_id)
    log(f"  {len(plays)} plays from sharp wallets in lookback window, {len(clusters)} clusters flagged")

    log("Fetching order-book sentiment for top plays...")
    attach_sentiment(plays[:MAX_ORDER_BOOK_LOOKUPS])

    now_iso = datetime.now(timezone.utc).isoformat()

    wallets_payload = {
        "captured_at": now_iso, "updated": now_iso,
        "min_score_threshold": MIN_WALLET_SCORE_TO_TRACK,
        "wallet_count": len(sharp_wallets),
        "wallets": sharp_wallets[:300],
    }
    live_payload = {
        "captured_at": now_iso, "updated": now_iso,
        "lookback_hours": LOOKBACK_SECONDS / 3600,
        "markets_tracked": len(markets),
        "plays": plays[:150],
        "clusters": clusters[:50],
    }

    ok = push_merged_to_gist(wallets_payload, live_payload)
    log(f"  merged push: {'ok' if ok else 'FAILED'}")

    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    run()
