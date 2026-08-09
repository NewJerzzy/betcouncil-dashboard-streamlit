"""
Distributed lock for coordinating writes to a shared Gist file across
independent GitHub Actions scripts.

Root problem this solves: every script sharing a merged Gist file does
a full read-modify-write cycle. GitHub's Gist PATCH has no conditional/
ETag-based write support, so two scripts running close together can
both read the file, both modify their own key, and whichever writes
LAST silently overwrites the other's just-written key -- confirmed
happening for real in production multiple times this session, even
after splitting into smaller per-cadence files and adding post-write
verification-and-retry. That earlier fix reduced collision frequency
and blast radius; it did not eliminate the possibility, because two
scripts can still both pass their own verification if their write-then-
verify cycles interleave just right.

This module adds a real lock: a small dedicated Gist file per lock
name (e.g. "betcouncil_lock_sharp_feeds.json") that scripts must
acquire before doing their read-modify-write, and release after.
Because acquiring the lock is ITSELF a write to a shared file (same
underlying problem, one level up), acquisition uses a claim-then-
verify pattern: write a claim with a random token, wait briefly, then
re-read to confirm the token that landed is really ours. If not, we
lost the race -- back off and retry. This is standard optimistic-
locking practice for a backing store with no native compare-and-swap,
and is far stronger than "just retry the write" since it serializes
the ENTIRE read-modify-write cycle across scripts, not just the final
write step.

A stale-lock timeout (default 5 minutes) prevents a crashed or timed-
out holder from deadlocking everyone else forever.

Usage (see scripts/unabated_refresh.py etc for real integration):

    from gist_lock import acquire_lock, release_lock

    token = acquire_lock(GIST_ID, github_token, "sharp_feeds", holder="unabated")
    if not token:
        log("Could not acquire lock after retries -- skipping this run")
        return 1
    try:
        # ... real read-modify-write-verify cycle here ...
    finally:
        release_lock(GIST_ID, github_token, "sharp_feeds", token)
"""
import json
import random
import time
import uuid

import requests

LOCK_STALE_MINUTES = 5


def _lock_filename(lock_name: str) -> str:
    return f"betcouncil_lock_{lock_name}.json"


def _read_lock(gist_id: str, github_token: str, lock_name: str) -> dict:
    fname = _lock_filename(lock_name)
    try:
        r = requests.get(
            f"https://api.github.com/gists/{gist_id}",
            headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
            timeout=15,
        )
        files = r.json().get("files", {})
        if fname not in files:
            return {}
        raw_url = files[fname]["raw_url"]
        content = requests.get(raw_url, timeout=15).text.strip()
        if not content:
            return {}
        return json.loads(content)
    except Exception:
        return {}


def _write_lock(gist_id: str, github_token: str, lock_name: str, payload: dict) -> bool:
    """
    Confirmed real bug (2026-08-09): this only checked the HTTP status
    code, not whether the file actually appeared in the response --
    matching the "200 but silently missing" pattern confirmed elsewhere
    this session. For a brand-new lock name (first-ever acquisition
    attempt, no pre-existing lock file), this let a genuinely-failed
    write masquerade as success, which then made the verify-read
    correctly find nothing and misread it as "someone else raced us"
    rather than "my own write vanished" -- causing acquire_lock to
    fail every attempt with no way to recover. Now verifies presence.
    """
    fname = _lock_filename(lock_name)
    try:
        resp = requests.patch(
            f"https://api.github.com/gists/{gist_id}",
            headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
            json={"files": {fname: {"content": json.dumps(payload)}}},
            timeout=20,
        )
        if resp.status_code not in (200, 201):
            return False
        returned_files = resp.json().get("files", {}) or {}
        return fname in returned_files
    except Exception:
        return False


def _is_stale(lock: dict) -> bool:
    ts = lock.get("acquired_at", "")
    if not ts:
        return True
    try:
        from datetime import datetime, timezone
        acquired = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        age_min = (datetime.now(timezone.utc) - acquired).total_seconds() / 60
        return age_min > LOCK_STALE_MINUTES
    except Exception:
        return True


def acquire_lock(gist_id: str, github_token: str, lock_name: str, holder: str,
                  max_attempts: int = 6, verify_delay_seconds: float = 2.5) -> str:
    """
    Attempts to acquire the named lock. Returns a unique token string on
    success (pass this to release_lock), or "" if the lock could not be
    acquired after max_attempts.
    """
    from datetime import datetime, timezone

    for attempt in range(max_attempts):
        current = _read_lock(gist_id, github_token, lock_name)
        if current and not _is_stale(current):
            wait = min(5 * (attempt + 1), 30) + random.uniform(0, 3)
            print(f"[gist_lock] {lock_name} held by {current.get('holder','?')}, waiting {wait:.1f}s (attempt {attempt+1}/{max_attempts})", flush=True)
            time.sleep(wait)
            continue

        my_token = str(uuid.uuid4())
        claim = {
            "holder": holder,
            "token": my_token,
            "acquired_at": datetime.now(timezone.utc).isoformat(),
        }
        if not _write_lock(gist_id, github_token, lock_name, claim):
            time.sleep(2 + random.uniform(0, 2))
            continue

        # Claim-then-verify: another script may have raced us and written
        # its own claim in between our read and our write. Wait briefly
        # for that write to land, then check whose token survived.
        time.sleep(verify_delay_seconds)
        verify = _read_lock(gist_id, github_token, lock_name)
        if verify.get("token") == my_token:
            print(f"[gist_lock] {lock_name} acquired by {holder}", flush=True)
            return my_token

        wait = 3 + random.uniform(0, 4)
        print(f"[gist_lock] Lost the race for {lock_name} to {verify.get('holder','?')} -- retrying in {wait:.1f}s", flush=True)
        time.sleep(wait)

    print(f"[gist_lock] FAILED to acquire {lock_name} after {max_attempts} attempts", flush=True)
    return ""


def release_lock(gist_id: str, github_token: str, lock_name: str, token: str) -> None:
    """
    Releases the named lock, but only if we still hold it (token
    matches) -- avoids accidentally releasing a lock some other script
    has since legitimately acquired (e.g. after our own lock went
    stale and someone else took over).
    """
    if not token:
        return
    current = _read_lock(gist_id, github_token, lock_name)
    if current.get("token") != token:
        print(f"[gist_lock] {lock_name} no longer held by us (token mismatch) -- not releasing", flush=True)
        return
    _write_lock(gist_id, github_token, lock_name, {})
    print(f"[gist_lock] {lock_name} released", flush=True)
