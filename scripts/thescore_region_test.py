"""
thescore_region_test.py — test theScore's Lines query across candidate
regional GraphQL hosts to find one whose schema actually matches.
================================================================================

Both prior investigation threads (mine and a parallel Replit session)
converged on the same theory: theScore's GraphQL endpoint is geo-routed per
state (sportsbook.us-<state>.thescore.bet), the client determines this at
runtime (not hardcoded in the bundle -- confirmed, the _app chunk is ~964
bytes and "us-default" doesn't appear in any loaded chunk), and "us-default"
is likely a stale/fallback schema that doesn't match the current query --
while real per-state hosts may have the fully-deployed, matching schema.

My own discovery run's real (non-target) traffic hit sportsbook.us-az.
thescore.bet for Startup/SportsMenu/etc from this exact GitHub Actions
runner's IP -- so us-az is a real, live-routed host for whatever region
these runners geolocate to, not a guess.

This script tests the Lines query directly against a spread of candidate
state hosts (no browser needed -- just swapping the host on the same
persisted-query GET) and reports, per host: HTTP status, whether the
response has GraphQL errors, and the first error message if so. A host
that returns clean data is the fix; a host that 403s tells us it's not
valid without a session in that region; a host with the same 36 errors
confirms the schema problem is universal, not regional.
"""

import json
import os
import sys
from datetime import datetime, timezone

import requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
GIST_FILE = "betcouncil_thescore_region_test.json"

# Confirmed current hash for CompetitionPageSectionLinesTabNode (bundle-scrape
# self-heal already confirmed this is what the live frontend maps to).
LINES_HASH = "4fcab2e9b286b7b14db66c66280a38bceab9effed830e3a805e833d7ce8cac0b"
STARTUP_HASH = "72b1ffd2b081b918369a7e942093ec666b55c2f3768608a7ec76150db5ebcf62"

# Candidate regional hosts: us-az and us-default are confirmed-real from
# actual traffic; the rest are the most populous/likely legal-sports-betting
# states, worth a cheap try each since we have no way to know which one(s)
# have the current schema without testing.
CANDIDATE_HOSTS = [
    "sportsbook.us-az.thescore.bet",
    "sportsbook.us-default.thescore.bet",
    "sportsbook.us-ia.thescore.bet",
    "sportsbook.us-nj.thescore.bet",
    "sportsbook.us-va.thescore.bet",
    "sportsbook.us-co.thescore.bet",
    "sportsbook.us-in.thescore.bet",
    "sportsbook.us-oh.thescore.bet",
    "sportsbook.us-mi.thescore.bet",
    "sportsbook.us-pa.thescore.bet",
    "sportsbook.us-il.thescore.bet",
    "sportsbook.us-tn.thescore.bet",
]

# Confirmed sectionId for MLB (2026-07-12 capture) -- known possibly stale,
# but held constant across hosts so any difference in results is attributable
# to the host/schema, not this variable.
MLB_SECTION_ID = "Section:d9513891-c315-4c16-8554-09d52d3ce9b2"


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def push_to_gist(payload: dict, github_token: str) -> bool:
    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"},
        json={"files": {GIST_FILE: {"content": json.dumps(payload, indent=2, default=str)}}},
        timeout=30,
    )
    if resp.status_code in (200, 201):
        return True
    log(f"Gist push failed: {resp.status_code} {resp.text[:300]}")
    return False


def mint_token(host: str, cf, session=None):
    import random, string
    connect_token = "".join(random.choices(string.ascii_lowercase + string.digits, k=32))
    variables = {
        "connectToken": connect_token,
        "latLongParams": {"accuracy": 20, "latitude": 41.977786, "longitude": -91.6624807},
    }
    extensions = {"persistedQuery": {"version": 1, "sha256Hash": STARTUP_HASH}}
    headers = {
        "x-client": "espnbet", "x-app": "espnbet", "x-platform": "web",
        "apollographql-client-name": "espnbet-espnbet-web",
        "apollographql-client-version": "26.13.2", "x-app-version": "26.13.2",
        "accept": "application/json", "content-type": "application/json",
        "x-install-id": "".join(random.choices(string.ascii_lowercase + string.digits, k=32)),
    }
    requester = session if session is not None else cf
    try:
        r = requester.get(
            f"https://{host}/graphql/persisted_queries/{STARTUP_HASH}",
            params={"operationName": "Startup", "variables": json.dumps(variables),
                    "extensions": json.dumps(extensions)},
            headers=headers, impersonate="chrome124", timeout=15)
        if r.status_code != 200:
            return None, r.status_code
        token = ((r.json().get("data") or {}).get("startup") or {}).get("anonymousToken")
        return token, r.status_code
    except Exception as e:
        return None, f"error: {e}"


def test_host(host: str) -> dict:
    from curl_cffi import requests as cf

    result = {"host": host}

    # Establish session cookies via the homepage first -- a bare, stateless
    # request to every regional host except us-ia returned a 302, which is
    # consistent with real browsers needing geo/session cookies set on first
    # load before the regional host will respond directly.
    session = cf.Session()
    try:
        home = session.get("https://sportsbook.thescore.bet/", impersonate="chrome124", timeout=15)
        result["homepage_status"] = home.status_code
        result["cookies_set"] = list(session.cookies.keys()) if hasattr(session, "cookies") else []
    except Exception as e:
        result["homepage_status"] = f"error: {e}"

    token, mint_status = mint_token(host, cf, session=session)
    result["mint_status"] = mint_status
    if not token:
        result["verdict"] = "no_token"
        return result

    variables = {
        "isSubscription": False, "pageType": "PAGE",
        "includeRecommendedProps": True, "isBrandingImageEnabled": True,
        "isNewFeaturedBetParticipantLogoEnabled": True,
        "isFeaturedBetCarouselHeaderRedesignEnabled": True,
        "includeStandardizedBoxscore": True, "isCfpRankingEnabled": True,
        "isCombatSportsRedesignEnabled": True,
        "isFeaturedMarketCardRedesignEnabled": True,
        "isDsModelRecommendedPropsEnabled": False, "includeRichEvent": True,
        "oddsFormat": "AMERICAN", "sectionId": MLB_SECTION_ID, "selectedFilterId": "",
    }
    extensions = {"persistedQuery": {"version": 1, "sha256Hash": LINES_HASH}}
    headers = {"x-anonymous-authorization": f"Bearer {token}", "accept": "application/json"}
    try:
        r = session.get(
            f"https://{host}/graphql/persisted_queries/{LINES_HASH}",
            params={"operationName": "CompetitionPageSectionLinesTabNode",
                    "variables": json.dumps(variables), "extensions": json.dumps(extensions)},
            headers=headers, impersonate="chrome124", timeout=15)
        result["lines_status"] = r.status_code
        if r.status_code != 200:
            result["verdict"] = "non_200"
            return result
        body = r.json()
        errors = body.get("errors")
        if errors:
            result["verdict"] = "schema_errors"
            result["error_count"] = len(errors)
            result["first_error"] = errors[0].get("message")
        else:
            result["verdict"] = "CLEAN"
            result["has_data"] = bool(body.get("data"))
        return result
    except Exception as e:
        result["verdict"] = f"exception: {e}"
        return result


def main() -> int:
    github_token = os.environ.get("GITHUB_TOKEN", "")
    if not github_token:
        log("FATAL: GITHUB_TOKEN not set")
        return 1

    results = []
    for host in CANDIDATE_HOSTS:
        log(f"Testing {host}...")
        r = test_host(host)
        log(f"  -> {r}")
        results.append(r)

    payload = {
        "captured_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "results": results,
    }
    push_to_gist(payload, github_token)

    clean = [r for r in results if r.get("verdict") == "CLEAN"]
    if clean:
        log(f"CLEAN host(s) found: {[r['host'] for r in clean]}")
        return 0
    log("No clean host found among candidates")
    return 1


if __name__ == "__main__":
    sys.exit(main())
