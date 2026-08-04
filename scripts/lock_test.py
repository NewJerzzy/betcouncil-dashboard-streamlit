import json
import os
import sys

sys.path.insert(0, "scripts")
from gist_lock import acquire_lock, release_lock

import requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"


def main():
    token = os.environ.get("GITHUB_TOKEN")
    results = {}

    # Test 1: acquire, verify held, release, verify released
    lock_token = acquire_lock(GIST_ID, token, "test_lock", holder="test_script_1", max_attempts=3, verify_delay_seconds=1.5)
    results["acquired"] = bool(lock_token)
    results["token_len"] = len(lock_token) if lock_token else 0

    release_lock(GIST_ID, token, "test_lock", lock_token)

    r = requests.get(f"https://api.github.com/gists/{GIST_ID}",
                      headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}, timeout=15)
    files = r.json().get("files", {})
    if "betcouncil_lock_test_lock.json" in files:
        raw = requests.get(files["betcouncil_lock_test_lock.json"]["raw_url"], timeout=15).json()
        results["after_release"] = raw
    else:
        results["after_release"] = "FILE_MISSING"

    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_bettingpros_debug.json": {"content": json.dumps({"note": "TEMP lock test", "results": results}, default=str)}}},
    )
    print("debug push:", resp.status_code)
    return 0


if __name__ == "__main__":
    sys.exit(main())
