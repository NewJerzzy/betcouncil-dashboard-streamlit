import json
import os
import sys
import time
import uuid

sys.path.insert(0, "scripts")
from gist_lock import acquire_lock, release_lock

import requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"


def main():
    token = os.environ.get("GITHUB_TOKEN")
    my_id = str(uuid.uuid4())[:8]
    result = {"holder_id": my_id}

    t0 = time.time()
    lock_token = acquire_lock(GIST_ID, token, "test_lock", holder=f"runner_{my_id}", max_attempts=6, verify_delay_seconds=2.0)
    t1 = time.time()
    result["acquired"] = bool(lock_token)
    result["wait_seconds"] = round(t1 - t0, 1)
    result["acquired_at_unix"] = t1

    if lock_token:
        # simulate real work while holding the lock
        time.sleep(6)
        result["released_at_unix"] = time.time()
        release_lock(GIST_ID, token, "test_lock", lock_token)

    # push this runner's own result under a unique key so both parallel
    # runs can write without racing each other on the SAME debug file
    fname = f"betcouncil_locktest_{my_id}.json"
    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {fname: {"content": json.dumps(result, default=str)}}},
    )
    print("debug push:", resp.status_code, fname)
    return 0


if __name__ == "__main__":
    sys.exit(main())
