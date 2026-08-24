"""
Real, scheduled OddsWrap cache warmer.

Confirmed via a real, live diagnostic tonight: OddsWrap is genuinely
needed (feeds the Market Climate bar and the Cross-Book Discrepancies
section on every real board load), but its real, cold fetch takes up
to ~12-18s. The existing cache (local pkl, then Gist, both 1hr) is
genuinely sound architecture -- confirmed real via this same diagnostic
tool -- but the *first* real user after a cache expiry still eats the
full, slow cost.

This script closes that gap the same way every other scheduled refresh
in this repo does: call the real fetch function directly, on a real
schedule, before the cache expires, so no real user ever hits the cold
path. fetch_oddswrap_props() already writes its own result back to the
Gist as a real, natural side-effect on success -- no custom write logic
needed here, just calling it.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fetchers

SPORTS = ["MLB", "NBA", "NFL", "NHL"]


def main():
    for sport in SPORTS:
        t0 = time.time()
        try:
            props = fetchers.fetch_oddswrap_props(sport)
            elapsed = round(time.time() - t0, 2)
            print(f"[OK] {sport}: {len(props)} real props in {elapsed}s")
        except Exception as e:
            print(f"[WARN] {sport}: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
