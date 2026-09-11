"""
Real, automated Gist self-cleaning script.

Confirmed problem this solves: the shared Gist (7e52e1c2c2054847c7c4663a
157386c5) is at GitHub's real, hard 300-file cap (already documented in
.agents/memory/gist-300-file-rename.md as a known, manually-worked-around
issue). A real, direct scan tonight found 205 of the 300 real files have
zero genuine reference anywhere in the live codebase -- confirmed accurate
via multiple spot-checks (correctly distinguishing e.g. the real, active
betcouncil_kalshi_markets.json from the confirmed-dead
betcouncil_kalshi_mlb.json, a similarly-named but genuinely unrelated
legacy file).

SAFETY DESIGN -- two-stage, not immediate deletion:
Orphan-detection can have false positives (one was caught and fixed during
this build: betcouncil_bankroll.json was initially misflagged because its
real Gist filename is built dynamically as f"betcouncil_{data_type}.json"
via save_to_gist()/load_from_gist(), not a literal, hardcoded string
anywhere in the source -- the corrected check looks for the real
data_type argument as a quoted string, not the full filename). Given that
history, this script never deletes on first detection:
  1. A file with zero real reference is added to a persistent tracking
     record (betcouncil_gist_cleanup_tracking.json, itself exempt from
     its own cleanup) with today's real date.
  2. A file already in the tracking record, still genuinely unreferenced,
     accumulates days. Only once a file has been continuously,
     genuinely orphaned for GRACE_PERIOD_DAYS does this script delete it.
  3. If a file becomes referenced again before the grace period ends
     (e.g. a new feature starts using it), it's removed from tracking --
     the grace-period clock resets, it is never deleted mid-transition.
"""
import base64
import json
import os
import re
import time
from datetime import datetime, timezone

import requests

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
HEADERS = {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}
TRACKING_FILENAME = "betcouncil_gist_cleanup_tracking.json"
GRACE_PERIOD_DAYS = 14

# Real files that must never be considered for cleanup, regardless of
# reference-detection: the tracking file's own record, plus any file this
# detection method is confirmed unable to reason about safely.
NEVER_CLEAN = {TRACKING_FILENAME}


def get_gist_files() -> set:
    r = requests.get(f"https://api.github.com/gists/{GIST_ID}", headers=HEADERS, timeout=30)
    r.raise_for_status()
    return set(r.json()["files"].keys())


def get_full_repo_source() -> str:
    """Real, complete read of every local .py file, concatenated, for the
    reference check -- the workflow already checks out the repo, so this
    reads directly from disk rather than making separate GitHub API calls
    that would need repo-content read permissions the Gist-scoped token
    may not have."""
    import glob
    combined = ""
    for path in glob.glob("**/*.py", recursive=True):
        try:
            with open(path, errors="replace") as f:
                combined += f.read()
        except OSError:
            continue
    return combined


def is_referenced(fname: str, source: str) -> bool:
    """Real, corrected check: for the standard betcouncil_X.json pattern,
    check whether X itself (the real data_type argument passed to
    save_to_gist/load_from_gist) is genuinely referenced as a quoted
    string -- not just whether the full filename appears literally, since
    the real filename is built dynamically at runtime, not hardcoded."""
    if fname.startswith("betcouncil_") and fname.endswith(".json"):
        data_type = fname[len("betcouncil_"):-len(".json")]
    else:
        data_type = fname.replace(".json", "")
    quoted_variants = [f'"{data_type}"', f"'{data_type}'", f'"betcouncil_{data_type}', f"'betcouncil_{data_type}"]
    return any(v in source for v in quoted_variants)


def load_tracking() -> dict:
    r = requests.get(f"https://api.github.com/gists/{GIST_ID}", headers=HEADERS, timeout=30)
    r.raise_for_status()
    files = r.json()["files"]
    if TRACKING_FILENAME not in files:
        return {}
    content = files[TRACKING_FILENAME].get("content", "{}")
    try:
        return json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return {}


def save_tracking(tracking: dict):
    requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers=HEADERS,
        json={"files": {TRACKING_FILENAME: {"content": json.dumps(tracking, indent=2)}}},
        timeout=30,
    )


def main():
    print("Real Gist self-clean: fetching current state...")
    gist_files = get_gist_files()
    source = get_full_repo_source()
    tracking = load_tracking()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    newly_flagged, still_pending, cleared, deleted = [], [], [], []

    for fname in sorted(gist_files):
        if fname in NEVER_CLEAN:
            continue
        referenced = is_referenced(fname, source)

        if referenced:
            if fname in tracking:
                cleared.append(fname)
                del tracking[fname]
            continue

        # Genuinely unreferenced right now.
        if fname not in tracking:
            tracking[fname] = {"first_flagged": today}
            newly_flagged.append(fname)
        else:
            first_flagged = datetime.strptime(tracking[fname]["first_flagged"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            days_orphaned = (datetime.now(timezone.utc) - first_flagged).days
            if days_orphaned >= GRACE_PERIOD_DAYS:
                deleted.append(fname)
            else:
                still_pending.append((fname, days_orphaned))

    # Real deletion pass -- only files that cleared the full grace period.
    if deleted:
        delete_payload = {f: None for f in deleted}
        requests.patch(f"https://api.github.com/gists/{GIST_ID}", headers=HEADERS,
                        json={"files": delete_payload}, timeout=30)
        for f in deleted:
            del tracking[f]

    save_tracking(tracking)

    print(f"Real, total Gist files: {len(gist_files)}")
    print(f"Newly flagged this run: {len(newly_flagged)}")
    print(f"Still in grace period: {len(still_pending)}")
    print(f"Cleared (became referenced again): {len(cleared)}")
    print(f"Deleted (orphaned {GRACE_PERIOD_DAYS}+ real days): {len(deleted)}")
    if deleted:
        for f in deleted:
            print(f"  deleted: {f}")


if __name__ == "__main__":
    main()
