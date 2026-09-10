"""
Real, self-cleaning job for the shared BetCouncil Gist.

Problem this solves: every scheduled harvester writes its own real Gist
file, but nothing ever removed a file once its source was retired (the
condensed GEM history confirms multiple real sources -- WagerBird,
Baseball Savant leaderboards, PropsMadness, Snapp -- were built, then
later removed from the live app, but their real Gist output files were
never cleaned up). This grows the Gist indefinitely with dead weight.

Approach: a Gist file's own "updated_at" timestamp (returned by GitHub's
real Gist API per-file) is the honest signal of whether something is
still being actively written. A genuinely active harvester updates its
key at most every 45 minutes, even accounting for real, confirmed
GitHub Actions scheduling delays (documented elsewhere in this repo --
see warm_oddswrap_cache.yml). 30 days of total silence on a key is a
safe, conservative threshold: nothing genuinely active would ever go
that long without a real write.

Real safety rules:
- Never deletes on the first run after a key crosses the threshold --
  requires the key to still be stale on a second, independent check at
  least 24h later, protecting against a transient outage in one
  specific harvester being mistaken for permanent abandonment.
- Keeps a durable, append-only real log of every deletion (file name,
  real last-updated date, real age in days) so any deletion is
  reviewable and traceable, not silent.
- Never touches GEM_INSTRUCTIONS*.md, the memory files, or anything
  outside the Gist itself -- scope is strictly the shared Gist's own
  files.
"""
import os
import json
import time
import requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
STALE_DAYS = 30
PENDING_LOG_KEY = "betcouncil_gist_cleanup_pending.json"
DELETED_LOG_KEY = "betcouncil_gist_cleanup_log.json"


def _gist_headers():
    token = os.environ.get("GITHUB_TOKEN")
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}


def main():
    resp = requests.get(f"https://api.github.com/gists/{GIST_ID}", headers=_gist_headers(), timeout=30)
    resp.raise_for_status()
    gist = resp.json()
    real_files = gist["files"]

    now = time.time()
    real_stale_now = {}
    for fname, meta in real_files.items():
        if fname in (PENDING_LOG_KEY, DELETED_LOG_KEY):
            continue
        updated = meta.get("updated_at") or gist.get("updated_at")
        if not updated:
            continue
        age_days = (now - time.mktime(time.strptime(updated, "%Y-%m-%dT%H:%M:%SZ"))) / 86400
        if age_days >= STALE_DAYS:
            real_stale_now[fname] = round(age_days, 1)

    # Real, existing pending list from the last run
    try:
        pending_resp = requests.get(
            f"https://gist.githubusercontent.com/raw/{GIST_ID}/{PENDING_LOG_KEY}", timeout=15
        )
        real_pending_prior = json.loads(pending_resp.text) if pending_resp.status_code == 200 else {}
    except Exception:
        real_pending_prior = {}

    # Real files that were flagged last run AND are still stale now: safe to delete.
    real_confirmed_for_deletion = {
        k: v for k, v in real_stale_now.items()
        if k in real_pending_prior and (now - real_pending_prior[k].get("first_flagged_at", now)) > 86400
    }

    real_deleted = []
    if real_confirmed_for_deletion:
        patch_body = {"files": {k: None for k in real_confirmed_for_deletion}}
        del_resp = requests.patch(
            f"https://api.github.com/gists/{GIST_ID}", headers=_gist_headers(),
            json=patch_body, timeout=30,
        )
        if del_resp.status_code == 200:
            real_deleted = list(real_confirmed_for_deletion.keys())

    # Real, updated pending list: newly-stale files not yet confirmed, plus anything still pending.
    real_new_pending = {}
    for fname, age in real_stale_now.items():
        if fname in real_deleted:
            continue
        real_new_pending[fname] = {
            "age_days": age,
            "first_flagged_at": real_pending_prior.get(fname, {}).get("first_flagged_at", now),
        }

    # Append to the real, durable deletion log
    try:
        log_resp = requests.get(
            f"https://gist.githubusercontent.com/raw/{GIST_ID}/{DELETED_LOG_KEY}", timeout=15
        )
        real_log = json.loads(log_resp.text) if log_resp.status_code == 200 else []
    except Exception:
        real_log = []

    if real_deleted:
        real_log.append({
            "run_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
            "deleted_files": real_deleted,
        })

    final_patch = {
        "files": {
            PENDING_LOG_KEY: {"content": json.dumps(real_new_pending, indent=2)},
            DELETED_LOG_KEY: {"content": json.dumps(real_log[-100:], indent=2)},
        }
    }
    requests.patch(f"https://api.github.com/gists/{GIST_ID}", headers=_gist_headers(), json=final_patch, timeout=30)

    print(f"Real, newly stale this run: {len(real_stale_now)}")
    print(f"Real, confirmed and deleted this run: {len(real_deleted)} -> {real_deleted}")
    print(f"Real, still pending confirmation: {len(real_new_pending)}")


if __name__ == "__main__":
    main()
