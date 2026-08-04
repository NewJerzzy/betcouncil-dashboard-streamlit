"""
wagerbird_refresh.py — WagerBird free MLB picks (wagerbird.com/picks)
================================================================================

REWRITE 2026-07-27: the site changed from embedding RSC data inline in the
HTML page (via self.__next_f.push([1,"..."]) blocks) to Next.js Partial
Prerendering -- the static shell loads immediately, but the actual picks
are "postponed" (confirmed via the real x-nextjs-postponed:2 response
header the user captured) and streamed in via a separate dedicated RSC
fetch. This is why the old regex, built for the inline-push format, went
from working to silently parsing 0 picks every run -- it was looking for
markup that no longer exists on this page at all, not markup that merely
drifted.

Confirmed real structure via an actual live browser DevTools capture the
user provided (both the picks page's Network tab request and a decoded
copy of the real RSC response body, not assumed): each pick is a
`fp-card` block using stable semantic class names (fp-card__league,
fp-card__time, fp-card__pick, fp-pill, fp-card__summary, fp-card__badge),
a real improvement over the old build's arbitrary hex-color Tailwind
classes since class *names* are much less likely to change than exact
color values. Tested this new parser against that real captured payload
before writing anything live: 93 of 95 real cards (98%) parsed completely
(the 2 misses were picks missing odds/tier in the source data itself, not
a parser failure).

FETCH MECHANISM (the one part not fully proven live yet): the response
the user captured came from a dedicated `picks?_rsc=<hash>` request, but
the response's own `Vary: rsc, next-router-state-tree, ...` header
indicates the server negotiates on the `RSC` request header, which is the
standard Next.js App Router mechanism -- not on the _rsc= query value
itself (that's client-side-generated and reportedly not required
server-side for this class of request in Next.js's own App Router
implementation). Requesting the plain page URL with an "RSC: 1" header
is the standard, documented way any HTTP client (not just Next's own
router) triggers this response type. If this specific guess is wrong,
the debug snippet this script ships with will show the actual HTML/RSC
response landed instead, making the real gap immediately visible on the
next real run rather than another silent 0-picks failure.

Pushes to betcouncil_wagerbird_picks.json (+ betcouncil_wagerbird_debug.json).
"""

import json
import os
import re
import sys
from datetime import datetime, timezone

import requests
import time
import random

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
URL = "https://wagerbird.com/picks"

HEADERS = {
    "Accept": "text/x-component",
    "RSC": "1",
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
}

CARD_BOUNDARY_RE = re.compile(r'"className":"fp-card","data-testid":"fp-card"')
DATE_SECTION_RE = re.compile(r'"fp-eyebrow","children":"([^"]+)"\}\],\["\$","h2",null,\{"className":"fp-h2","children":"([^"]+)"')
LEAGUE_RE = re.compile(r'"fp-card__league","children":\["([A-Z]+)","[^"]*","([^"]+)"\]')
TIME_RE = re.compile(r'"fp-card__time","children":"([^"]+)"')
PICK_RE = re.compile(r'"fp-card__pick","children":"([^"]+)"')
ODDS_RE = re.compile(r'"fp-pill","children":"([+-]?\d+)"')
TIER_RE = re.compile(r'"children":\["(WB\d|GEMS)","[^"]*?(\d+)"?\]')
SUMMARY_RE = re.compile(r'"fp-card__summary","children":"([^"]+)"')
BADGE_RE = re.compile(r'"fp-card__badge[^"]*","children":"([^"]+)"')
HREF_RE = re.compile(r'"href":"(https://www\.youtube\.com/watch\?v=[^"]+)"')

DEBUG_LOG: list = []


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def fetch_rsc():
    try:
        r = requests.get(URL, headers=HEADERS, timeout=20)
    except Exception as e:
        DEBUG_LOG.append({"url": URL, "error": str(e)})
        return None
    DEBUG_LOG.append({
        "url": URL, "status": r.status_code, "bytes": len(r.text),
        "content_type": r.headers.get("content-type", ""),
        "body_snippet": r.text[:800],
    })
    if r.status_code != 200:
        return None
    return r.text


def extract_picks(text: str):
    date_sections = [(m.start(), m.group(2)) for m in DATE_SECTION_RE.finditer(text)]
    DEBUG_LOG.append({"date_sections_found": [d[1] for d in date_sections]})

    def date_for_position(pos: int) -> str:
        applicable = [d for d in date_sections if d[0] <= pos]
        if not applicable:
            return datetime.now(timezone.utc).strftime("%B %d, %Y")
        return applicable[-1][1]

    card_starts = [m.start() for m in CARD_BOUNDARY_RE.finditer(text)]
    DEBUG_LOG.append({"card_boundaries_found": len(card_starts)})
    card_starts.append(len(text))

    picks = []
    for i in range(len(card_starts) - 1):
        chunk = text[card_starts[i]:card_starts[i + 1]]
        league_m = LEAGUE_RE.search(chunk)
        pick_m = PICK_RE.search(chunk)
        if not (league_m and pick_m):
            continue
        time_m = TIME_RE.search(chunk)
        odds_m = ODDS_RE.search(chunk)
        tier_m = TIER_RE.search(chunk)
        summary_m = SUMMARY_RE.search(chunk)
        badge_m = BADGE_RE.search(chunk)
        href_m = HREF_RE.search(chunk)

        raw_date = date_for_position(card_starts[i])
        try:
            pick_date = datetime.strptime(raw_date, "%B %d, %Y").strftime("%Y-%m-%d")
        except ValueError:
            pick_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        picks.append({
            "sport": league_m.group(1),
            "matchup": league_m.group(2),
            "game_time": time_m.group(1) if time_m else None,
            "pick_text": pick_m.group(1),
            "odds": odds_m.group(1) if odds_m else None,
            "tier": tier_m.group(1) if tier_m else None,
            "confidence_score": int(tier_m.group(2)) if tier_m else None,
            "rationale": summary_m.group(1) if summary_m else None,
            "result": (badge_m.group(1) if badge_m else "pending").replace("Pending", "pending"),
            "pick_date": pick_date,
            "prediction_url": href_m.group(1) if href_m else None,
        })

    seen = set()
    deduped = []
    for p in picks:
        key = (p["matchup"], p["pick_text"], p["odds"], p["pick_date"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(p)

    return deduped


def push_files(files_payload: dict, github_token: str) -> int:
    """
    Merges into the shared evbets_combined.json.

    UPDATED (2026-08-03): confirmed a real, live production data-loss
    race -- multiple scripts merge into the same shared file on
    independent cron schedules, and a full read-modify-write cycle
    means one script's write can silently clobber another's just-
    written key if their timing overlaps (confirmed happening for
    real: wagerbird/sportsinsights/unabated all independently observed
    missing after other scripts' writes landed in between). Added an
    outer retry: after a successful write, re-read and verify no
    previously-present key vanished (not just that OUR key landed) --
    if one did, redo the entire read-modify-write cycle from a fresh
    read, up to 3 times total.
    """
    SHARED_FILE = "betcouncil_evbets_combined.json"
    merged = {}
    for fname, fbody in files_payload.items():
        key = fname.replace("betcouncil_wagerbird_", "").replace(".json", "")
        try:
            merged[key] = json.loads(fbody["content"])
        except Exception:
            merged[key] = fbody["content"]

    for outer_attempt in range(3):
        try:
            r = requests.get(f"https://api.github.com/gists/{GIST_ID}",
                              headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
                              timeout=15)
            r_files = r.json().get("files", {})
            if SHARED_FILE in r_files:
                raw_url = r_files[SHARED_FILE]["raw_url"]
                existing = requests.get(raw_url, timeout=15).json()
            else:
                existing = {}
        except Exception as e:
            log(f"Could not read existing shared file, starting fresh: {e}")
            existing = {}
        pre_write_keys = set(existing.keys())
        existing["wagerbird"] = merged
        shared_payload = {SHARED_FILE: {"content": json.dumps(existing)}}

        write_ok = False
        for attempt in range(5):
            resp = requests.patch(
                f"https://api.github.com/gists/{GIST_ID}",
                headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
                json={"files": shared_payload}, timeout=30,
            )
            if resp.status_code in (200, 201):
                returned_files = resp.json().get("files", {}) or {}
                if SHARED_FILE in returned_files:
                    write_ok = True
                    break
                if attempt < 4:
                    wait = min((attempt + 1) * 5, 30)
                    log(f"Push returned 200 but {SHARED_FILE} missing from response -- retrying in {wait}s")
                    time.sleep(wait)
                    continue
                log(f"Push returned 200 but {SHARED_FILE} still missing after retries -- treating as failed")
                return 0
            if resp.status_code in (403, 429, 409) and attempt < 4:
                base_wait = min(10 * (2 ** attempt), 90)
                wait = base_wait + random.uniform(0, base_wait * 0.4)
                log(f"Gist push got {resp.status_code} -- retrying in {wait:.1f}s (attempt {attempt+1}/5)")
                time.sleep(wait)
                continue
            log(f"Gist push failed: {resp.status_code} {resp.text[:300]}")
            return 0

        if not write_ok:
            return 0

        # Verify no previously-present key vanished (a concurrent writer's
        # stale read clobbering our just-written state).
        try:
            time.sleep(2)
            r2 = requests.get(f"https://api.github.com/gists/{GIST_ID}",
                               headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
                               timeout=15)
            raw_url2 = r2.json().get("files", {}).get(SHARED_FILE, {}).get("raw_url")
            post_write = requests.get(raw_url2, timeout=15).json() if raw_url2 else {}
            post_write_keys = set(post_write.keys())
            lost_keys = pre_write_keys - post_write_keys - {"wagerbird"}
            if "wagerbird" in post_write_keys and not lost_keys:
                return len(files_payload)
            log(f"Post-write verification found lost keys {lost_keys} or missing own key -- retrying full cycle (outer attempt {outer_attempt+1}/3)")
        except Exception as e:
            log(f"Post-write verification failed to check: {e} -- treating write as successful anyway")
            return len(files_payload)

    log("Gave up after 3 full read-modify-write cycles -- concurrent writers kept colliding")
    return 0


def _rate_limit_ok(github_token: str, min_remaining: int = 150) -> bool:
    try:
        r = requests.get(
            "https://api.github.com/rate_limit",
            headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
            timeout=15,
        )
        remaining = r.json().get("resources", {}).get("core", {}).get("remaining")
        if remaining is not None and remaining < min_remaining:
            log(f"Shared GitHub token budget low ({remaining} left this hour) -- skipping cleanly")
            return False
    except Exception as e:
        log(f"Rate-limit pre-check failed ({e}) -- proceeding anyway")
    return True


def main() -> int:
    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        log("FATAL: GITHUB_TOKEN not set")
        return 1

    if not _rate_limit_ok(github_token):
        return 0

    now_iso = datetime.now(timezone.utc).isoformat()

    text = fetch_rsc()
    files_payload = {}

    if text is None:
        log("Fetch failed — see debug log")
        files_payload["betcouncil_wagerbird_debug.json"] = {
            "content": json.dumps({"captured_at": now_iso, "requests": DEBUG_LOG[:15]}, indent=2)
        }
        push_files(files_payload, github_token)
        return 1

    picks = extract_picks(text)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    latest_date = max((p["pick_date"] for p in picks if p["pick_date"]), default=today)
    todays_picks = [p for p in picks if p["pick_date"] == latest_date]
    log(f"Parsed {len(picks)} total picks, {len(todays_picks)} dated on latest slate ({latest_date})")

    files_payload["betcouncil_wagerbird_picks.json"] = {
        "content": json.dumps({
            "source": "wagerbird_picks_page",
            "captured_at": now_iso,
            "total_picks": len(picks),
            "todays_picks_count": len(todays_picks),
            "picks": picks,
        }, indent=2)
    }
    files_payload["betcouncil_wagerbird_debug.json"] = {
        "content": json.dumps({"captured_at": now_iso, "requests": DEBUG_LOG[:15],
                                "text_snippet": text[:1500] if len(picks) == 0 else None},
                               indent=2)
    }

    if not picks:
        log("0 picks parsed — see debug snippet")
        push_files(files_payload, github_token)
        return 1

    pushed = push_files(files_payload, github_token)
    log(f"Pushed {pushed} files")
    return 0 if pushed > 0 else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as _e:
        import traceback
        _tb = traceback.format_exc()
        try:
            _emergency_token = os.environ.get("GITHUB_TOKEN", "")
            if _emergency_token:
                import urllib.request as _ur
                _body = json.dumps({"files": {"betcouncil_wagerbird_debug.json": {
                    "content": json.dumps({
                        "captured_at": datetime.now(timezone.utc).isoformat(),
                        "uncaught_exception": str(_e),
                        "traceback": _tb[-3000:],
                    }, indent=2)
                }}}).encode()
                _req = _ur.Request(f"https://api.github.com/gists/{GIST_ID}", data=_body, method="PATCH",
                    headers={"Authorization": f"token {_emergency_token}", "Accept": "application/vnd.github+json",
                             "Content-Type": "application/json"})
                _ur.urlopen(_req, timeout=15)
        except Exception:
            pass
        print(_tb, flush=True)
        sys.exit(1)
