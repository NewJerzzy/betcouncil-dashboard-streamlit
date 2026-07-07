"""
pick6_ssr_scraper.py — Pick6 player props scraper (no login, no browser)
==========================================================================

Runs on GitHub Actions (see .github/workflows/pick6_refresh.yml), on a
schedule. Fetches pick6.draftkings.com directly — the player prop cards
(name, stat, line, multiplier) are rendered server-side into the page's
initial HTML, so a plain HTTP GET + text parse is enough. No login, no
Playwright, no WAF fight.

Pushes results to the same Gist BetCouncil already reads from
(pick6_props_live.json), matching the format fetch_pick6_props_from_gist()
in fetchers.py expects.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone

import requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
GIST_FILE = "pick6_props_live.json"

SPORTS = ["MLB", "NBA", "NFL", "NHL", "WNBA", "UFC", "SOCCER"]

NAME_RE = re.compile(r"^[A-Z]\.\s+[A-Za-z'\.\-]+$")
GLUED_NAME_RE = re.compile(r"\)([A-Z]\.\s+[A-Za-z'\.\-]+)$")
POS_RE = re.compile(r"^[A-Za-z/1-3]+\s*\([A-Z]\)$")
MATCHUP_RE = re.compile(r"^[A-Z]{2,4}\s*@\s*[A-Z]{2,4}$")


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def fetch_page_text(sport: str) -> str:
    """Fetch the Pick6 page and strip HTML tags down to line-based text,
    similar in structure to how a browser's readable-text view would
    render it. Player prop cards survive this as plain, parseable lines."""
    url = f"https://pick6.draftkings.com/?sport={sport}"
    headers = {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"),
        "Accept-Language": "en-US,en;q=0.9",
    }
    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()
    html = resp.text

    # Keep image src attributes (need player dkId from them), drop other tags.
    # Replace <img ...src="URL"...> with "![Player](URL)" style marker so the
    # dkId regex below still finds it, then strip all remaining tags.
    html = re.sub(
        r'<img[^>]*src="([^"]+)"[^>]*>',
        lambda m: f"![Player]({m.group(1)})",
        html,
    )
    text = re.sub(r"<[^>]+>", "\n", html)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&nbsp;", " ", text)
    return text


def parse_props(text: str, sport: str) -> list:
    lines = [l.strip() for l in text.splitlines()]
    lines = [l for l in lines if l]

    props = []
    seen = set()
    i = 0
    while i < len(lines):
        m = re.search(r"players/\d+/(?:d/)?(\d+)\.png", lines[i])
        if not m:
            i += 1
            continue

        dkid = m.group(1)
        j = i + 1
        name = None
        while j < len(lines) and j < i + 10:
            glued = GLUED_NAME_RE.search(lines[j])
            if glued:
                name = glued.group(1)
                j += 1
                break
            if NAME_RE.match(lines[j]):
                name = lines[j]
                j += 1
                break
            j += 1

        if not name:
            i += 1
            continue

        pos = lines[j] if j < len(lines) and POS_RE.match(lines[j]) else None
        if pos:
            j += 1
        matchup = lines[j] if j < len(lines) and MATCHUP_RE.match(lines[j]) else None
        if matchup:
            j += 1

        # Advance to the "---" card divider
        scan_limit = j + 15
        while j < len(lines) and lines[j] != "---" and j < scan_limit:
            j += 1
        if j >= len(lines) or lines[j] != "---":
            i += 1
            continue
        j += 1

        if j < len(lines) and "Minus Icon" in lines[j]:
            j += 1

        if j >= len(lines):
            i += 1
            continue
        raw_line = lines[j]
        half = len(raw_line) // 2
        if half > 0 and raw_line[:half] == raw_line[half:]:
            line_val = raw_line[:half]
        else:
            line_val = raw_line
        j += 1

        if j < len(lines) and "Plus Icon" in lines[j]:
            j += 1

        stat_type = lines[j] if j < len(lines) else None
        j += 1

        # Multiplier: look ahead a few lines for an "Nx" pattern
        multiplier = None
        for k in range(j, min(j + 6, len(lines))):
            mm = re.match(r"^(\d+(\.\d+)?x)\1$|^(\d+(\.\d+)?x)$", lines[k])
            if mm:
                multiplier = mm.group(1) or mm.group(3)
                break

        try:
            line_float = float(line_val)
        except (TypeError, ValueError):
            i = j
            continue

        key = (name, stat_type, line_float, multiplier)
        if key not in seen:
            seen.add(key)
            props.append({
                "player": name,
                "stat_name": stat_type or "Unknown",
                "line": line_float,
                "multiplier": multiplier,
                "dkId": dkid,
                "sport": sport,
                "captured_at": datetime.now(timezone.utc).isoformat(),
            })

        i = j

    return props


def push_to_gist(all_props: list) -> bool:
    github_token = os.environ["GITHUB_TOKEN"]
    content = json.dumps(
        {
            "props": all_props,
            "prop_count": len(all_props),
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "source": "pick6_ssr_scrape_github_actions",
        },
        indent=2,
    )
    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={
            "Authorization": f"Bearer {github_token}",
            "Accept": "application/vnd.github+json",
        },
        json={"files": {GIST_FILE: {"content": content}}},
        timeout=20,
    )
    return resp.status_code in (200, 201)


def main() -> int:
    if not os.environ.get("GITHUB_TOKEN"):
        log("FATAL: GITHUB_TOKEN not set")
        return 1

    all_props = []
    for sport in SPORTS:
        try:
            text = fetch_page_text(sport)
            props = parse_props(text, sport)
            log(f"{sport}: {len(props)} props")
            all_props.extend(props)
        except Exception as e:
            log(f"{sport}: error — {e}")

    if not all_props:
        log("FATAL: no props captured for any sport")
        return 1

    ok = push_to_gist(all_props)
    log(f"Gist push: {'SUCCESS' if ok else 'FAILED'} — {len(all_props)} total props")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
