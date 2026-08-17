"""
espn_cron_runner.py — Replit-based cron for ESPN Opening Lines Capture
================================================================================

WHY THIS EXISTS (confirmed 2026-08-17):
  ESPN's scoreboard API (site.api.espn.com) blocks GitHub Actions' datacenter
  IP ranges with HTTP 403. ScrapeOps residential proxy also returns 403.
  Replit's IP is confirmed not blocked (HTTP 200, tested directly).
  This runner keeps espn_opening_lines_refresh.py executing from Replit's IP
  on the same schedule (10, 14, 18 UTC) the GH Actions workflow used.

SETUP:
  - Runs as a Replit workflow (console, background process)
  - Reads GITHUB_TOKEN env var; falls back to GITHUB_PERSONAL_ACCESS_TOKEN
    (the Replit secret already in this environment)
  - The GH Actions workflow still exists for manual dispatch but has no
    schedule — all scheduled runs come from here

OPERATION:
  - Polls every 30 seconds
  - Fires espn_opening_lines_refresh.py within the first 4 minutes of the
    scheduled hour (10, 14, 18 UTC)
  - Tracks last-fired hour so it doesn't double-fire during those 4 minutes
  - Logs all runs with UTC timestamps to stdout (visible in Replit console)
"""

import os
import subprocess
import sys
import time
from datetime import datetime, timezone

# UTC hours to fire the ESPN refresh (matches the original GH Actions schedule)
RUN_HOURS = {10, 14, 18}

# Fire within the first N minutes of the hour (prevents duplicate fires)
FIRE_WINDOW_MINUTES = 4

# How often to check the clock (seconds)
POLL_INTERVAL_SECONDS = 30

# Path to the ESPN script, relative to repo root
ESPN_SCRIPT = "scripts/espn_opening_lines_refresh.py"


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[espn-cron {ts}] {msg}", flush=True)


def build_env() -> dict:
    """Build subprocess env with GITHUB_TOKEN set.
    
    The ESPN script reads GITHUB_TOKEN. In Replit, the secret is
    GITHUB_PERSONAL_ACCESS_TOKEN. Map it over if GITHUB_TOKEN isn't
    separately set so the script works without any extra secret setup.
    """
    env = os.environ.copy()
    if not env.get("GITHUB_TOKEN") and env.get("GITHUB_PERSONAL_ACCESS_TOKEN"):
        env["GITHUB_TOKEN"] = env["GITHUB_PERSONAL_ACCESS_TOKEN"]
        log("GITHUB_TOKEN not set — using GITHUB_PERSONAL_ACCESS_TOKEN")
    if not env.get("GITHUB_TOKEN"):
        log("WARNING: neither GITHUB_TOKEN nor GITHUB_PERSONAL_ACCESS_TOKEN is set — ESPN refresh will fail")
    return env


def fire_refresh() -> int:
    """Run the ESPN script and return its exit code."""
    log(f"Firing {ESPN_SCRIPT} ...")
    env = build_env()
    result = subprocess.run(
        [sys.executable, ESPN_SCRIPT],
        env=env,
    )
    log(f"ESPN refresh exited with code {result.returncode}")
    return result.returncode


def main() -> None:
    log(f"ESPN cron runner started (fire hours UTC: {sorted(RUN_HOURS)}, "
        f"window: first {FIRE_WINDOW_MINUTES}min, poll: every {POLL_INTERVAL_SECONDS}s)")

    if not os.path.exists(ESPN_SCRIPT):
        log(f"ERROR: {ESPN_SCRIPT} not found — is the cwd the repo root?")
        sys.exit(1)

    last_fired_hour: int | None = None

    while True:
        now = datetime.now(timezone.utc)

        if now.hour in RUN_HOURS and now.minute < FIRE_WINDOW_MINUTES:
            if last_fired_hour != now.hour:
                last_fired_hour = now.hour
                fire_refresh()
        elif now.minute >= FIRE_WINDOW_MINUTES:
            # Reset once we're past the fire window so next scheduled hour works
            if last_fired_hour == now.hour:
                last_fired_hour = None

        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
