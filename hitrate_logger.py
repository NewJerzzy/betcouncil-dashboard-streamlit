"""
hitrate_logger.py — Append-only prop hit-rate logging to Gist.

Logs every distinct prop seen (keyed by prop_key + date) to
betcouncil_prop_hitrate_log.json in the shared Gist.  Entries older than
PROP_HITRATE_RETENTION_DAYS are pruned on each write.

Public API
----------
log_props_to_hitrate(book_data, sport)     -> bool
load_hitrate_log()                         -> dict
compute_hit_rate(player, stat, line)       -> dict | None  (stub — needs resolved data)
"""
import json
import logging
import time
from datetime import date, datetime, timedelta
from typing import Optional

import requests

_logger = logging.getLogger("betcouncil.hitrate_logger")

try:
    from config import (
        GITHUB_TOKEN,
        GITHUB_GIST_ID,
        PROP_HITRATE_LOG_FILE,
        PROP_HITRATE_RETENTION_DAYS,
    )
except ImportError:
    GITHUB_TOKEN              = ""
    GITHUB_GIST_ID            = "7e52e1c2c2054847c7c4663a157386c5"
    PROP_HITRATE_LOG_FILE     = "betcouncil_prop_hitrate_log.json"
    PROP_HITRATE_RETENTION_DAYS = 60

from prop_normalizer import build_prop_key, normalize_player_name, normalize_stat_name

_GIST_API = "https://api.github.com/gists"
_HEADERS  = lambda: {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}

# Local in-memory cache: avoids re-fetching on every call within the same run
_cache: dict = {}
_cache_ts: float = 0.0
_CACHE_TTL_SEC: float = 300.0  # 5 minutes


# ── Gist I/O helpers ──────────────────────────────────────────────────────────

def _gist_read() -> dict:
    """Read betcouncil_prop_hitrate_log.json from Gist with in-memory TTL cache."""
    global _cache, _cache_ts
    if _cache and (time.time() - _cache_ts) < _CACHE_TTL_SEC:
        return _cache
    if not GITHUB_TOKEN or not GITHUB_GIST_ID:
        return {}
    try:
        r = requests.get(
            f"{_GIST_API}/{GITHUB_GIST_ID}",
            headers=_HEADERS(), timeout=10,
        )
        if r.status_code != 200:
            return _cache
        gist = r.json()
        f = gist.get("files", {}).get(PROP_HITRATE_LOG_FILE, {})
        content = f.get("content", "{}")
        data = json.loads(content) if content else {}
        _cache = data
        _cache_ts = time.time()
        return data
    except Exception as exc:
        _logger.warning("[hitrate_logger] _gist_read: %s", exc)
        return _cache


def _gist_write(data: dict) -> bool:
    """Write the full hitrate log dict back to the Gist (single PATCH)."""
    global _cache, _cache_ts
    if not GITHUB_TOKEN or not GITHUB_GIST_ID:
        return False
    try:
        payload = {
            "files": {
                PROP_HITRATE_LOG_FILE: {
                    "content": json.dumps(data, indent=2)
                }
            }
        }
        r = requests.patch(
            f"{_GIST_API}/{GITHUB_GIST_ID}",
            headers=_HEADERS(),
            json=payload,
            timeout=15,
        )
        if r.status_code == 200:
            _cache    = data
            _cache_ts = time.time()
            return True
        _logger.warning("[hitrate_logger] PATCH failed %s", r.status_code)
        return False
    except Exception as exc:
        _logger.warning("[hitrate_logger] _gist_write: %s", exc)
        return False


# ── Log structure ─────────────────────────────────────────────────────────────
#
# {
#   "entries": [
#     {
#       "prop_key":  "mlb:player_hits:juan soto:1.5:20260705",
#       "player":    "juan soto",
#       "stat":      "player_hits",
#       "line":      1.5,
#       "sport":     "MLB",
#       "date":      "2026-07-05",
#       "books":     ["prizepicks", "draftkings"],
#       "n_books":   2,
#       "logged_at": "2026-07-05T14:22:00Z"
#     },
#     ...
#   ]
# }


def _prune_old(entries: list, retention_days: int) -> list:
    cutoff = (date.today() - timedelta(days=retention_days)).isoformat()
    return [e for e in entries if e.get("date", "9999") >= cutoff]


# ── Public API ────────────────────────────────────────────────────────────────

def log_props_to_hitrate(
    book_data: dict[str, list[dict]],
    sport: str,
) -> bool:
    """
    Append any new props from book_data to the Gist-backed hit-rate log.

    Deduplication is by (prop_key + date) — re-runs within the same day
    are idempotent.  Prunes entries older than PROP_HITRATE_RETENTION_DAYS
    before writing.

    Parameters
    ----------
    book_data : {book_name: [prop_dicts]}
        Same format as match_props_across_books().
    sport : str

    Returns
    -------
    bool — True if write succeeded (or no new props to log), False on error.
    """
    if not GITHUB_TOKEN or not GITHUB_GIST_ID:
        return False

    today_str = date.today().isoformat()
    now_iso   = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    # Build set of new prop entries from book_data
    new_entries: dict[str, dict] = {}  # prop_key+date → entry
    for book, props in book_data.items():
        if not isinstance(props, list):
            continue
        for p in props:
            player_raw = str(p.get("Player") or p.get("player") or "")
            stat_raw   = str(p.get("Prop") or p.get("Stat") or p.get("stat") or "")
            line_raw   = p.get("Line") or p.get("line")
            if not player_raw or not stat_raw or line_raw is None:
                continue
            try:
                line_f = float(line_raw)
            except (TypeError, ValueError):
                continue
            player_norm = normalize_player_name(player_raw)
            stat_canon  = normalize_stat_name(stat_raw, sport)
            prop_key    = build_prop_key(player_norm, stat_canon, line_f, sport)
            dedup_key   = f"{prop_key}|{today_str}"
            if dedup_key not in new_entries:
                new_entries[dedup_key] = {
                    "prop_key":  prop_key,
                    "player":    player_norm,
                    "stat":      stat_canon,
                    "line":      line_f,
                    "sport":     sport.upper(),
                    "date":      today_str,
                    "books":     [],
                    "n_books":   0,
                    "logged_at": now_iso,
                }
            if book not in new_entries[dedup_key]["books"]:
                new_entries[dedup_key]["books"].append(book)
                new_entries[dedup_key]["n_books"] += 1

    if not new_entries:
        return True  # nothing to log

    # Load existing log
    existing = _gist_read()
    current_entries: list = existing.get("entries", [])

    # Deduplicate against what's already logged
    existing_keys = {
        f"{e.get('prop_key')}|{e.get('date')}"
        for e in current_entries
    }
    to_add = [v for k, v in new_entries.items() if k not in existing_keys]
    if not to_add:
        return True  # all already logged today

    merged = _prune_old(current_entries + to_add, PROP_HITRATE_RETENTION_DAYS)
    data = {"entries": merged, "last_updated": now_iso}
    ok = _gist_write(data)
    if ok:
        _logger.debug(
            "[hitrate_logger] %s: logged %d new props (total %d)",
            sport, len(to_add), len(merged),
        )
    return ok


def load_hitrate_log() -> dict:
    """Return the full Gist-backed hit-rate log (cached, 5-min TTL)."""
    return _gist_read()


def compute_hit_rate(
    player: str,
    stat: str,
    line: float,
    sport: str = "",
) -> Optional[dict]:
    """
    Stub — returns None until resolved-outcome data is wired in.

    Future: load betcouncil_prop_results.json from Gist and compute
    hit-rate by matching prop_key against logged entries.
    """
    return None
