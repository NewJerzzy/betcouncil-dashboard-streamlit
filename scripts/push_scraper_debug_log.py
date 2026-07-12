"""Pushes the last run's scraper output to the Gist for remote debugging.
Used by .github/workflows/auto_scraper_refresh.yml -- lets debugging happen
via the Gist API even when GitHub's own Actions log storage isn't reachable
from wherever the debugging is happening.
"""
import json
import os
import sys
import urllib.request

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"


def main():
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        print("No GITHUB_TOKEN set, skipping debug log push")
        return

    log_path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/scraper_output.log"
    if not os.path.exists(log_path):
        print(f"No log file at {log_path}, skipping")
        return

    with open(log_path, "r", errors="replace") as f:
        log = f.read()[-40000:]

    req = urllib.request.Request(
        f"https://api.github.com/gists/{GIST_ID}",
        method="PATCH",
        headers={
            "Authorization": f"token {token}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.github.v3+json",
        },
        data=json.dumps(
            {"files": {"betcouncil_scraper_debug_log.txt": {"content": log}}}
        ).encode(),
    )
    try:
        urllib.request.urlopen(req, timeout=15)
        print("Debug log pushed to Gist: betcouncil_scraper_debug_log.txt")
    except Exception as e:
        print(f"Failed to push debug log: {e}")


if __name__ == "__main__":
    main()
