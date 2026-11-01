"""Narrow, read-only access to OddsAssist's public expert selections.

No odds-board import, credentials, background job, or scoring/staking changes.
The upstream route is internal Remix single-fetch data, not a versioned API.
"""

import json
import math
from datetime import datetime, timedelta, timezone

import requests


PICKS_URL = "https://pro.oddsassist.com/picks.data?_routes=routes%2F_main.picks"
SOURCE = "OddsAssist — Rob O'Connor"
MAX_RESPONSE_BYTES = 5_000_000


def decode_page_data(text):
    """Decode the reference table, without evaluating upstream JavaScript."""
    values = json.loads(text.splitlines()[0])
    if not isinstance(values, list) or not values:
        raise ValueError("OddsAssist returned an invalid reference table")
    memo = {}

    def resolve(index):
        if not isinstance(index, int) or isinstance(index, bool):
            raise ValueError("OddsAssist returned an invalid reference")
        # Turbo-stream uses negative references for null/undefined and other
        # special scalars. Required fields are validated separately.
        if index < 0:
            return None
        if index >= len(values):
            raise ValueError("OddsAssist returned an out-of-range reference")
        if index in memo:
            return memo[index]
        value = values[index]
        if not isinstance(value, (list, dict)):
            return value
        if isinstance(value, list) and value and value[0] == "D":
            return datetime.fromtimestamp(
                value[1] / 1000, tz=timezone.utc
            ).isoformat()
        if isinstance(value, list):
            result = []
            memo[index] = result
            result.extend(resolve(item) for item in value)
        else:
            result = {}
            memo[index] = result
            for key, ref in value.items():
                if not key.startswith("_") or not key[1:].isdigit():
                    raise ValueError("OddsAssist page-data encoding changed")
                field = resolve(int(key[1:]))
                if not isinstance(field, str):
                    raise ValueError("OddsAssist returned a non-string field")
                result[field] = resolve(ref)
        return result

    return resolve(0)


def _utc(value):
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("OddsAssist timestamp has no timezone")
    return parsed.astimezone(timezone.utc)


def _number(value):
    if isinstance(value, bool):
        raise ValueError("Invalid numeric field")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Non-finite numeric field")
    return result


def normalize_pending_picks(page_data):
    """Keep only this reviewed expert's pending full-game football picks."""
    route = page_data.get("routes/_main.picks", {}).get("data", {})
    picks = route.get("picks")
    if not isinstance(picks, list):
        raise ValueError("OddsAssist picks schema changed")
    output, seen = [], set()
    for pick in picks:
        if pick.get("result") not in (None, "PENDING"):
            continue
        if (pick.get("user") or {}).get("name") != "Rob O'Connor":
            continue  # Additional experts have not been reviewed.
        legs = pick.get("legs") or []
        if len(legs) != 1:
            continue
        leg = legs[0]
        event = leg.get("event") or {}
        sport = (
            event.get("competitionInstance", {}).get("competition", {}).get("shortName")
        )
        if sport not in ("NFL", "NCAAF") or event.get("type") == "COMPETITION":
            continue
        market = leg.get("marketType")
        if market not in ("POINT_SPREAD", "POINT_TOTAL", "MONEYLINE"):
            continue
        if leg.get("marketSegment") != "FULL_MATCH":
            continue
        try:
            start = _utc(event["startTime"])
            created = _utc(pick["createdAt"])
            payout = _number(leg["payout"])
            units = _number(pick["units"])
            participants = event["participants"]
            home_key = event["homeParticipantKey"]
            if len(participants) != 2 or not home_key:
                raise ValueError("Invalid event participants")
            home = next(p for p in participants if p["key"] == home_key)
            away = next(p for p in participants if p["key"] != home_key)
            if not home.get("name") or not away.get("name"):
                raise ValueError("Missing team name")
            selected = next(
                (p for p in participants if p["key"] == leg.get("participantKey")), None
            )
            line = _number(leg["modifier"]) if market != "MONEYLINE" else None
            if payout <= 1 or units <= 0 or created >= start:
                raise ValueError("Invalid published price, stake, or timestamp")
            if market == "POINT_TOTAL":
                if leg.get("type") not in ("OVER", "UNDER") or line <= 0:
                    raise ValueError("Invalid total")
                selection = f"{leg['type'].title()} {line:g}"
            else:
                if not selected or leg.get("type") != "WIN":
                    raise ValueError("Invalid selected team")
                selection = selected["name"]
                selection += f" {line:+g}" if market == "POINT_SPREAD" else " ML"
            identity = str(pick["id"])
            if not identity or identity in seen:
                continue
            seen.add(identity)
            output.append({
                "id": identity, "source": SOURCE, "sport": sport,
                "away": away["name"], "home": home["name"],
                "event_key": event["key"], "start_time": start.isoformat(),
                "published_at": created.isoformat(), "selection": selection,
                "market": market, "line": line, "decimal_odds": payout,
                "expert_units": units,
            })
        except (KeyError, TypeError, ValueError, StopIteration) as exc:
            # Do not quietly present a partially parsed source as complete.
            raise ValueError("OddsAssist has a malformed pending game pick") from exc
    return output


def fetch_public_picks():
    """Fetch once; the UI caches the small normalized snapshot for five minutes."""
    with requests.get(
        PICKS_URL, timeout=(5, 15), stream=True,
        headers={"Accept": "text/x-script", "User-Agent": "BetCouncil/1.0"},
    ) as response:
        response.raise_for_status()
        chunks, size = [], 0
        for chunk in response.iter_content(chunk_size=65536):
            size += len(chunk)
            if size > MAX_RESPONSE_BYTES:
                raise ValueError("OddsAssist response exceeded the size limit")
            chunks.append(chunk)
    page_data = decode_page_data(b"".join(chunks).decode("utf-8"))
    return {
        "picks": normalize_pending_picks(page_data),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def prediction_items(snapshot, now=None):
    """Filter at render time, so a cache hit cannot retain a kicked-off game."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Current time must have a timezone")
    fetched = _utc(snapshot["fetched_at"])
    if now - fetched > timedelta(minutes=10) or fetched > now + timedelta(minutes=1):
        raise ValueError("OddsAssist snapshot is stale or has a future timestamp")
    output = []
    for pick in snapshot["picks"]:
        if not (_utc(pick["published_at"]) <= now < _utc(pick["start_time"]) <= now + timedelta(days=7)):
            continue
        payout = pick["decimal_odds"]
        american = round((payout - 1) * 100 if payout >= 2 else -100 / (payout - 1))
        output.append({
            **pick,
            "text": (
                f"{pick['selection']} ({american:+d}, published price)"
                f" · {pick['expert_units']:g}u expert stake"
                f" · posted {_utc(pick['published_at']):%b %d %H:%M UTC}"
                f" · checked {fetched:%H:%M UTC}"
                " · not a current sportsbook quote"
            ),
        })
    return output
