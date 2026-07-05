"""
ufc_scraper.py — UFC event/fight data from ufcstats.com.

Verified real structure (no stated anti-scraping ToS, unlike FanGraphs):
  tr.b-fight-details__table-row  — one row per fight
  td.b-fight-details__table-col  — 10 cells per row
  cell[6] = weight class, cell[7] = method, cell[8] = round

Public API
----------
fetch_event_results(event_url) -> list[dict]
compute_finish_rate_by_weightclass(events: list) -> dict
    {weight_class: {decision_pct, finish_pct, ko_pct, sub_pct, n_fights}}
"""
import time
import requests
from bs4 import BeautifulSoup

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
_REQUEST_DELAY_SECONDS = 1.5  # polite pacing, avoid hammering a small stats site


def _text(node):
    return node.get_text(strip=True) if node else None


def fetch_event_results(event_url: str) -> list:
    """
    Parse one completed event page into a list of fight-result dicts.
    Real column layout confirmed: cell[6]=weight class, cell[7]=method,
    cell[8]=round.
    """
    try:
        resp = requests.get(event_url, headers=_HEADERS, timeout=15)
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        rows = soup.select("tr.b-fight-details__table-row")
        fights = []
        for row in rows:
            cells = row.select("td.b-fight-details__table-col")
            if len(cells) < 10:
                continue
            fighter_names = [_text(p) for p in cells[1].select("p")]
            fights.append({
                "fighter_1": fighter_names[0] if fighter_names else None,
                "fighter_2": fighter_names[1] if len(fighter_names) > 1 else None,
                "weight_class": _text(cells[6]),
                "method": _text(cells[7]),
                "round": _text(cells[8]),
            })
        return fights
    except Exception as e:
        print(f"[WARN] fetch_event_results({event_url}): {e}")
        return []


def fetch_completed_events(limit: int = 10) -> list:
    """List recent completed event URLs from the events index page."""
    try:
        resp = requests.get(
            "http://www.ufcstats.com/statistics/events/completed?page=all",
            headers=_HEADERS, timeout=15,
        )
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        links = soup.select("a.b-link.b-link_style_black")
        urls = [a.get("href") for a in links if a.get("href")]
        return urls[:limit]
    except Exception as e:
        print(f"[WARN] fetch_completed_events: {e}")
        return []


def compute_finish_rate_by_weightclass(limit_events: int = 15) -> dict:
    """
    Computes REAL finish-rate stats per weight class from recent completed
    events (not DeepSeek's invented 35%/55% figures). Sequential requests
    with pacing delay, respecting this is a small/lightly-resourced site.
    """
    event_urls = fetch_completed_events(limit_events)
    tally = {}  # weight_class -> {"decision":0, "ko":0, "sub":0, "total":0}

    for url in event_urls:
        fights = fetch_event_results(url)
        for f in fights:
            wc = f.get("weight_class")
            method = (f.get("method") or "").upper()
            if not wc:
                continue
            tally.setdefault(wc, {"decision": 0, "ko": 0, "sub": 0, "total": 0})
            tally[wc]["total"] += 1
            if "DEC" in method:
                tally[wc]["decision"] += 1
            elif "KO" in method or "TKO" in method:
                tally[wc]["ko"] += 1
            elif "SUB" in method:
                tally[wc]["sub"] += 1
        time.sleep(_REQUEST_DELAY_SECONDS)  # polite pacing between event pages

    result = {}
    for wc, counts in tally.items():
        n = counts["total"]
        if n < 5:
            continue  # sample-size guard
        result[wc] = {
            "n_fights": n,
            "decision_pct": round(counts["decision"] / n * 100, 1),
            "ko_pct": round(counts["ko"] / n * 100, 1),
            "sub_pct": round(counts["sub"] / n * 100, 1),
            "finish_pct": round((counts["ko"] + counts["sub"]) / n * 100, 1),
        }
    return result
