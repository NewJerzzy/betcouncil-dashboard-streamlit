"""
board_snapshot_headless.py -- scheduled PROP board snapshots, no browser needed.

Props were only graded on days someone opened the app (12 snapshots total, nearly all MLB), so
NBA/NFL/NHL tier results were barely measured. This runs the real board pipeline headless for
every in-season sport and stores the snapshot (same store_board_snapshot the app uses) so the
daily grading job and the validation gate get a full, unbiased sample.
"""
import os, sys, time, traceback
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def in_season(sport, month):
    return {"NFL": month in (9, 10, 11, 12, 1, 2), "NBA": month in (10, 11, 12, 1, 2, 3, 4, 5, 6),
            "NHL": month in (10, 11, 12, 1, 2, 3, 4, 5, 6), "MLB": month in (3, 4, 5, 6, 7, 8, 9, 10),
            "WNBA": month in (5, 6, 7, 8, 9)}.get(sport, False)


def main():
    import app_core as ac
    month = datetime.now(timezone.utc).month
    sports = [s for s in ("NFL", "NBA", "NHL", "MLB", "WNBA") if in_season(s, month)]
    ok = 0
    for sport in sports:
        t0 = time.time()
        try:
            board = ac.load_sport_data(sport)[0]
            n = len(board or [])
            if n:
                ac.store_board_snapshot(board, sport)
                ok += 1
            print(f"[board_snapshot] {sport}: {n} props, stored={bool(n)} ({time.time()-t0:.0f}s)", flush=True)
        except Exception:
            print(f"[board_snapshot] {sport}: FAILED\n{traceback.format_exc()[-800:]}", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
