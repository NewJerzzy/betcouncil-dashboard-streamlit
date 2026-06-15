"""BetCouncil Scrapers — direct API fetchers for sportsbooks."""
import re
import datetime
from datetime import date, timedelta
import os
import json
import time
import pickle
import os

CACHE_DIR = os.path.join(os.path.dirname(__file__), ".cache")
os.makedirs(CACHE_DIR, exist_ok=True)
import requests
from functools import lru_cache
try:
    from bc_utils import normalize_name, safe_float
except ImportError:
    def normalize_name(n): return n.strip().lower()
    def safe_float(v, d=0.0):
        try: return float(v)
        except: return d


def fetch_auto_scraped_props(sport="NBA"):
    """Fetch props from GitHub Gist. Fallback when PrizePicks direct fails."""
    try:
        if not GITHUB_TOKEN or not GITHUB_GIST_ID:
            log_error_to_session("fetch_auto_scraped_props", "GitHub credentials not configured", "warning")
            return []

        r = requests.get(
            f"https://api.github.com/gists/{GITHUB_GIST_ID}",
            headers={"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"},
            timeout=10
        )

        if r.status_code != 200:
            log_error_to_session("fetch_auto_scraped_props", f"Gist API returned {r.status_code}", "warning")
            return []

        files = r.json().get("files", {})
        if "auto_scraped_props.json" not in files:
            log_error_to_session("fetch_auto_scraped_props", "auto_scraped_props.json not found in Gist", "warning")
            return []

        file_obj = files["auto_scraped_props.json"]
        file_size = file_obj.get("size", 0)

        # Large files may be truncated — use raw_url
        if file_size > 900000:
            raw_url = file_obj.get("raw_url", "")
            if raw_url:
                r_raw = requests.get(raw_url, headers={"Authorization": f"token {GITHUB_TOKEN}"}, timeout=15)
                if r_raw.status_code == 200:
                    gist_content = r_raw.json()
                else:
                    log_error_to_session("fetch_auto_scraped_props", f"Raw URL returned {r_raw.status_code}", "error")
                    return []
            else:
                log_error_to_session("fetch_auto_scraped_props", "raw_url not available", "error")
                return []
        else:
            content = file_obj.get("content", "")
            if not content:
                log_error_to_session("fetch_auto_scraped_props", "Gist content is empty", "warning")
                return []
            try:
                gist_content = json.loads(content)
            except json.JSONDecodeError as e:
                log_error_to_session("fetch_auto_scraped_props", f"JSON parse error: {str(e)[:100]}", "error")
                return []

        # Verify date
        gist_date = gist_content.get("date", "")
        if not is_date_valid_for_today(gist_date):
            log_error_to_session("fetch_auto_scraped_props", f"Gist stale (date: {gist_date}, today: {date.today().isoformat()})", "warning")
            return []

        # Filter by sport
        all_props = gist_content.get("props", [])
        props = [p for p in all_props if p.get("Sport") == sport]

        if props:
            log_error_to_session("fetch_auto_scraped_props", f"Loaded {len(props)} {sport} props from Gist", "info")
        else:
            log_error_to_session("fetch_auto_scraped_props", f"No {sport} props in Gist", "warning")

        return props

    except requests.Timeout:
        log_error_to_session("fetch_auto_scraped_props", "Gist API timed out (10s)", "error")
        return []
    except Exception as e:
        log_error_to_session("fetch_auto_scraped_props", f"Unexpected: {str(e)[:100]}", "error")
        return []



def fetch_fanduel_direct(sport):
    """Fetch FanDuel props directly using curl_cffi. Fallback when OddsPAPI is down."""
    try:
        from curl_cffi import requests as cf
        session = cf.Session(impersonate="chrome124")
    except ImportError:
        return []

    FD_KEY = "FhMFpcPWXMeyZxOx"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Origin": "https://az.sportsbook.fanduel.com",
        "Referer": "https://az.sportsbook.fanduel.com/",
        "x-application": FD_KEY,
    }

    event_type_map = {"NBA": 7522, "MLB": 6, "NHL": 7524, "WNBA": 614, "NFL": 63747}
    etid = event_type_map.get(sport, 7522)
    props = []

    cache_path = os.path.join(CACHE_DIR, f"fanduel_direct_{sport}.pkl")
    if os.path.exists(cache_path):
        age_mins = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_mins < 90:
            with open(cache_path, "rb") as f:
                cached = pickle.load(f)
            if cached:
                return cached

    try:
        r = session.get(
            f"https://api.sportsbook.fanduel.com/sbapi/content-managed-page",
            params={"page": "SPORT", "eventTypeId": etid, "_ak": FD_KEY, "timezone": "America/Phoenix"},
            headers=headers, timeout=15
        )
        if r.status_code != 200:
            return []

        data = r.json()
        attachments = data.get("attachments", {})
        events = attachments.get("events", {})
        markets = attachments.get("markets", {})
        selections = attachments.get("selections", {})

        for mkt_id, mkt in markets.items():
            mkt_name = mkt.get("marketName", "")
            if not any(kw in mkt_name.lower() for kw in
                       ["point", "rebound", "assist", "steal", "block", "three",
                        "strikeout", "hit", "home run", "rbi", "bases",
                        "goal", "shot", "save", "yard", "reception",
                        "touchdown", "pass", "rush", "pra", "fantasy"]):
                continue

            for runner in mkt.get("runners", []):
                rn_name = runner.get("runnerName", "")
                handicap = runner.get("handicap")
                sel_id = str(runner.get("selectionId", ""))

                if " Over " in rn_name:
                    player = rn_name.split(" Over ")[0].strip()
                    side = "OVER"
                elif " Under " in rn_name:
                    player = rn_name.split(" Under ")[0].strip()
                    side = "UNDER"
                else:
                    player = rn_name
                    side = "OVER"

                odds = "—"
                sel_det = selections.get(sel_id, {})
                if sel_det:
                    am = sel_det.get("winRunnerOdds", {}).get("americanDisplayOdds", {}).get("americanOdds")
                    if am is not None:
                        odds = f"{'+' if am > 0 else ''}{int(am)}"

                if player and handicap is not None:
                    props.append({
                        "Player": player, "Prop": mkt_name,
                        "Line": float(handicap), "Side": side,
                        "OverOdds": odds if side == "OVER" else "—",
                        "UnderOdds": odds if side == "UNDER" else "—",
                        "Book": "FanDuel", "Sport": sport,
                        "source": "fanduel_direct",
                    })

        # Per-event fallback if content-managed-page didn't have props
        if not props:
            for eid in list(events.keys())[:5]:
                r2 = session.get(
                    f"https://api.sportsbook.fanduel.com/sbapi/event-page",
                    params={"_ak": FD_KEY, "eventId": eid, "tab": "player-props"},
                    headers=headers, timeout=10
                )
                if r2.status_code == 200:
                    ev = r2.json().get("attachments", {})
                    for mid, m in ev.get("markets", {}).items():
                        mn = m.get("marketName", "")
                        if not any(kw in mn.lower() for kw in ["point","rebound","assist","strikeout","hit","home run","goal","shot","yard","touchdown"]):
                            continue
                        for rn in m.get("runners", []):
                            nm = rn.get("runnerName", "")
                            hc = rn.get("handicap")
                            if " Over " in nm:
                                pn, sd = nm.split(" Over ")[0].strip(), "OVER"
                            elif " Under " in nm:
                                pn, sd = nm.split(" Under ")[0].strip(), "UNDER"
                            else:
                                pn, sd = nm, "OVER"
                            od = "—"
                            sd2 = ev.get("selections", {}).get(str(rn.get("selectionId", "")), {})
                            if sd2:
                                am2 = sd2.get("winRunnerOdds", {}).get("americanDisplayOdds", {}).get("americanOdds")
                                if am2 is not None:
                                    od = f"{'+' if am2 > 0 else ''}{int(am2)}"
                            if pn and hc is not None:
                                props.append({"Player": pn, "Prop": mn, "Line": float(hc), "Side": sd,
                                    "OverOdds": od if sd == "OVER" else "—",
                                    "UnderOdds": od if sd == "UNDER" else "—",
                                    "Book": "FanDuel", "Sport": sport, "source": "fanduel_direct"})
                time.sleep(0.3)

        # Cache results
        if props:
            with open(cache_path, "wb") as f:
                pickle.dump(props, f)

    except Exception as _e:
            print(f"[WARN] {_e}")

    return props


def fetch_weather_for_game(city, is_outdoor=True):
    if not is_outdoor:
        return None
    cache_key = hashlib.md5(f"weather_{city}_{date.today()}".encode()).hexdigest()
    cache_path = os.path.join(CACHE_DIR, f"{cache_key}_weather.pkl")
    if os.path.exists(cache_path):
        age_hours = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_hours < 3:
            with open(cache_path, "rb") as f:
                return pickle.load(f)
    weather = None
    # Tier 1: wttr.in
    try:
        url = f"https://wttr.in/{city.replace(' ', '+')}?format=j1"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            current = data.get("current_condition", [{}])[0]
            weather = {"city": city, "wind_speed_mph": int(current.get("windspeedMiles", 0)),
                       "wind_dir": current.get("winddir16Point", "N"), "temp_f": int(current.get("temp_F", 70)),
                       "humidity": int(current.get("humidity", 50)), "fetched_at": datetime.now().strftime("%H:%M"),
                       "source": "wttr.in"}
    except (ValueError, KeyError, TypeError, AttributeError):
        pass
    # Tier 2: NWS fallback
    if weather is None:
        weather = _fetch_nws_weather(city)
    if weather:
        try:
            with open(cache_path, "wb") as f:
                pickle.dump(weather, f)
        except (ValueError, KeyError, TypeError, AttributeError):
            pass
    return weather


def fetch_todays_referees(sport):
    cache_path = os.path.join(CACHE_DIR, f"officials_{sport}_{date.today()}.pkl")
    if os.path.exists(cache_path):
        age = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age < 6:
            with open(cache_path, "rb") as f:
                return pickle.load(f)
    slug_map = {"NBA": "basketball/nba", "MLB": "baseball/mlb"}
    path = slug_map.get(sport)
    if not path:
        return {}
    officials = {}
    try:
        today_str = date.today().strftime("%Y%m%d")
        url = f"https://site.web.api.espn.com/apis/site/v2/sports/{path}/scoreboard?dates={today_str}"
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            return {}
        for event in resp.json().get("events", []):
            matchup = event.get("shortName", "")
            for comp in event.get("competitions", []):
                refs = [o.get("displayName", "") for o in comp.get("officials", []) if o.get("displayName")]
                if refs and matchup:
                    officials[matchup] = refs
        if officials:
            with open(cache_path, "wb") as f:
                pickle.dump(officials, f)
    except (ValueError, KeyError, TypeError, AttributeError):
        pass
    return officials

GAME_TIER_THRESHOLDS = {
    "NBA":    {"SOVEREIGN": 0.12, "ELITE": 0.08, "APPROVED": 0.04, "LEAN": 0.02},
    "MLB":    {"SOVEREIGN": 0.06, "ELITE": 0.03, "APPROVED": 0.015, "LEAN": 0.005},
    "NFL":    {"SOVEREIGN": 0.12, "ELITE": 0.08, "APPROVED": 0.04, "LEAN": 0.02},
    "NHL":    {"SOVEREIGN": 0.10, "ELITE": 0.06, "APPROVED": 0.03, "LEAN": 0.01},
    "WNBA":   {"SOVEREIGN": 0.12, "ELITE": 0.08, "APPROVED": 0.04, "LEAN": 0.02},
    "Soccer": {"SOVEREIGN": 0.10, "ELITE": 0.06, "APPROVED": 0.03, "LEAN": 0.01},
}


def fetch_soccer_rolling_averages():
    cache_path = os.path.join(CACHE_DIR, "soccer_rolling_avgs.pkl")
    if os.path.exists(cache_path):
        age_hours = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_hours < 24:
            with open(cache_path, "rb") as f:
                return pickle.load(f)
    rolling = {}
    for player, stats in PLAYER_AVERAGES_SOCCER.items():
        goals = stats.get("GOALS", 0.3)
        assists = stats.get("ASSISTS", 0.2)
        shots = stats.get("SHOTS", 3.0)
        rolling[player] = {
            "GOALS": goals,
            "ASSISTS": assists,
            "SHOTS": shots,
            "GOALS_std": round(goals * 0.80, 3),
            "ASSISTS_std": round(assists * 0.75, 3),
            "SHOTS_std": round(shots * 0.45, 3),
            "n_games": 10,
            "source": "hardcoded_with_std"
        }
    if rolling:
        with open(cache_path, "wb") as f:
            pickle.dump(rolling, f)
    return rolling

BDL_PLAYER_IDS = {
    "LeBron James": 237, "Luka Doncic": 140, "Nikola Jokic": 279, "Shai Gilgeous-Alexander": 484,
    "Giannis Antetokounmpo": 15, "Jayson Tatum": 484, "Stephen Curry": 115, "Kevin Durant": 135,
    "Anthony Davis": 14, "Damian Lillard": 153, "Devin Booker": 70, "Donovan Mitchell": 300,
    "Jimmy Butler": 85, "Trae Young": 571, "Domantas Sabonis": 395, "Karl-Anthony Towns": 508,
    "Bam Adebayo": 2, "Rudy Gobert": 185, "Tyrese Haliburton": 613, "Jalen Brunson": 86,
    "Cade Cunningham": 625, "Victor Wembanyama": 794, "Paolo Banchero": 731, "Evan Mobley": 694,
    "Darius Garland": 578, "Tobias Harris": 216, "Ja Morant": 606, "Zion Williamson": 400,
    "Jamal Murray": 333, "Michael Porter Jr.": 585, "Aaron Gordon": 5, "Jalen Williams": 746,
    "Alperen Sengun": 700, "Desmond Bane": 616, "Scottie Barnes": 689, "Franz Wagner": 709,
    "De'Aaron Fox": 170, "Pascal Siakam": 400, "Kawhi Leonard": 232, "Luguentz Dort": 601,
}


def fetch_underdog_props(sport):
    sport_map = {"NBA": "NBA", "MLB": "MLB", "NHL": "NHL", "NFL": "NFL", "WNBA": "WNBA"}
    sport_id = sport_map.get(sport)
    if not sport_id:
        return []
    # ── Cache layer (was missing — added for parity with all other fetch functions) ──
    cache_path = os.path.join(CACHE_DIR, f"underdog_props_{sport}.pkl")
    if os.path.exists(cache_path):
        age_mins = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_mins < 25:
            try:
                with open(cache_path, "rb") as _f:
                    cached = pickle.load(_f)
                if cached:
                    return cached
            except (ValueError, KeyError, TypeError, AttributeError):
                pass
    # Try new v1 lobbies endpoint first (discovered via DevTools May 2026)
    product_exp_id = "018e1234-5678-9abc-def0-123456789006"
    state_config_id = "725014ef-3570-4e93-871d-d69674ab3521"
    url_v1 = (
        f"https://api.underdogfantasy.com/v1/lobbies/content/lines"
        f"?include_live=true&product=fantasy"
        f"&product_experience_id={product_exp_id}"
        f"&show_mass_option_markets=false"
        f"&sport_id={sport_id}"
        f"&state_config_id={state_config_id}"
    )
    url_v2 = f"https://api.underdogfantasy.com/v2/over_under_lines?sport_id={sport_id}"
    url = url_v1
    try:
        ud_headers = {**HEADERS, "Origin": "https://underdogfantasy.com", "Referer": "https://underdogfantasy.com/pick-em"}
        resp = requests.get(url, headers=ud_headers, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 400 or resp.status_code == 403:
            # Fall back to v2
            resp = requests.get(url_v2, headers=ud_headers, timeout=REQUEST_TIMEOUT)
            url = url_v2
        if resp.status_code != 200:
            return []
        data = resp.json()
        props = []
        seen = set()

        # Detect v1 vs v2 response
        # v1 has "suggested_picks" wrapper, v2 has flat "over_under_lines" list
        is_v1 = "suggested_picks" in data
        sp = data["suggested_picks"] if is_v1 else data

        # Players: dict (v1) or list (v2)
        players_dict = sp.get("players", {})
        if isinstance(players_dict, dict):
            players_map = {pid: f"{p.get('first_name','').strip()} {p.get('last_name','').strip()}".strip()
                          for pid, p in players_dict.items()}
        elif isinstance(players_dict, list):
            players_map = {p["id"]: f"{p.get('first_name','').strip()} {p.get('last_name','').strip()}".strip()
                          for p in players_dict if isinstance(p, dict) and "id" in p}
        else:
            players_map = {}

        # Appearances: dict (v1) or list (v2)
        appearances_dict = sp.get("appearances", {})
        if isinstance(appearances_dict, dict):
            appearances_map = {aid: a.get("player_id","") for aid, a in appearances_dict.items()}
        elif isinstance(appearances_dict, list):
            appearances_map = {a["id"]: a.get("player_id","") for a in appearances_dict if isinstance(a, dict)}
        else:
            appearances_map = {}

        # over_under_lines: dict (v1) or list (v2)
        oul = sp.get("over_under_lines", {})
        if isinstance(oul, dict):
            lines_list = list(oul.values())
        elif isinstance(oul, list):
            lines_list = oul
        else:
            lines_list = []

        # Filter by sport
        sport_id = sport.upper()
        teams_dict = sp.get("teams", {})
        games_dict = sp.get("games", {})

        for line in lines_list:
            if line.get("status","") == "closed":
                continue

            line_val = line.get("stat_value")
            if line_val is None:
                continue

            # Get player name from options[0].selection_header (most reliable)
            options = line.get("options", [])
            if options:
                opt = options[0]
                name = opt.get("selection_header","").strip()
                stat_name = opt.get("stat_display","").strip()
                if not stat_name:
                    stat_name = opt.get("selection_subheader","").split(" ", 2)[-1] if opt.get("selection_subheader") else ""
            else:
                # Fallback: use over_under.appearance_stat
                ou = line.get("over_under", {})
                app_stat = ou.get("appearance_stat", {})
                app_id = app_stat.get("appearance_id","")
                player_id = appearances_map.get(app_id,"")
                name = players_map.get(player_id,"")
                stat_name = app_stat.get("display_stat","")

            if not name or not stat_name:
                continue

            # Sport filter: check player sport via appearances/games
            ou = line.get("over_under", {})
            app_stat = ou.get("appearance_stat", {})
            app_id = app_stat.get("appearance_id","")
            app_data = appearances_dict.get(app_id, {}) if isinstance(appearances_dict, dict) else {}
            match_id = str(app_data.get("match_id",""))
            game = games_dict.get(match_id, {}) if isinstance(games_dict, dict) else {}
            game_sport = game.get("sport_id","")

            if game_sport and game_sport.upper() != sport_id:
                continue

            key = (sport, name, stat_name, line_val)
            if key in seen:
                continue
            seen.add(key)
            props.append({
                "Player": name,
                "Prop": stat_name,
                "Line": float(line_val),
                "Side": "OVER",
                "Sport": sport,
                "source": "Underdog"
            })

        if not props and lines_list:
            # If sport filter removed everything, return without filter
            for line in lines_list[:50]:
                if line.get("status","") == "closed":
                    continue
                line_val = line.get("stat_value")
                options = line.get("options", [])
                if options and line_val:
                    opt = options[0]
                    name = opt.get("selection_header","").strip()
                    stat_name = opt.get("stat_display","").strip()
                    if name and stat_name:
                        key = (sport, name, stat_name, line_val)
                        if key not in seen:
                            seen.add(key)
                            props.append({"Player": name, "Prop": stat_name,
                                        "Line": float(line_val), "Side": "OVER",
                                        "Sport": sport, "source": "Underdog"})
        if props:
            try:
                with open(cache_path, "wb") as _f:
                    pickle.dump(props, _f)
            except (ValueError, KeyError, TypeError, AttributeError):
                pass
        return props
    except Exception as e:
        print(f"Underdog props error: {e}")
        return []


def fetch_cbs_injuries(sport):
    """
    CBS Sports injury feed — Tier 2 injury source.
    Free RSS, no key needed, different infrastructure from RotoWire.
    Provides redundancy when RotoWire/ESPN are unavailable.
    """
    CBS_SPORT_MAP = {
        "NBA": "nba", "MLB": "mlb", "NFL": "nfl",
        "NHL": "nhl", "WNBA": "wnba",
    }
    cbs_sport = CBS_SPORT_MAP.get(sport)
    if not cbs_sport:
        return []
    try:
        urls = [
            f"https://www.cbssports.com/rss/headlines/fantasy/{cbs_sport}/",
            f"https://www.cbssports.com/{cbs_sport}/players/injuries/",
        ]
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15",
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        }
        for url in urls:
            try:
                r = requests.get(url, headers=headers, timeout=8)
                if r.status_code != 200:
                    continue
                import xml.etree.ElementTree as ET
                root = ET.fromstring(r.content)
                channel = root.find("channel")
                if channel is None:
                    continue
                results = []
                for item in channel.findall("item")[:20]:
                    title_el = item.find("title")
                    desc_el  = item.find("description")
                    title = (title_el.text or "").strip() if title_el is not None else ""
                    desc  = (desc_el.text or "").strip()[:150] if desc_el is not None else ""
                    if not title:
                        continue
                    if ":" in title:
                        player, note = title.split(":", 1)
                    else:
                        player, note = title, desc
                    note_lower = note.lower()
                    if any(w in note_lower for w in ("out","ruled out","won't play","dnp")):
                        status = "OUT"
                    elif "doubtful" in note_lower:
                        status = "DOUBTFUL"
                    elif any(w in note_lower for w in ("questionable","limited","day-to-day")):
                        status = "QUESTIONABLE"
                    elif any(w in note_lower for w in ("probable","likely")):
                        status = "PROBABLE"
                    else:
                        status = "NEWS"
                    results.append({
                        "player": player.strip(),
                        "status": status,
                        "note":   note.strip()[:150],
                        "sport":  sport,
                        "source": "CBS Sports",
                    })
                if results:
                    return results
            except (ValueError, KeyError, TypeError, AttributeError):
                continue
        return []
    except (requests.RequestException, ValueError, KeyError):
        return []



def fetch_alt_lines(sport):
    """
    Fetch alternate spread lines from OddsAPI.
    Used to find playable lines when the standard spread has no edge.
    
    Example: PHI -1.5 (run line) → no edge
             PHI -0.5 → APPROVED edge (adjusted for easier cover)
             PHI +1.5 → ELITE edge (can lose by 1 and still win)
    
    Returns dict: {matchup: {team: [{line, home_odds, away_odds}]}}
    """
    if not ODDS_API_KEY:
        return {}
    sport_key = ODDS_API_SPORT_MAP.get(sport)
    if not sport_key:
        return {}
    # Only fetch for sports where alt lines matter
    if sport not in ("MLB","WNBA","NBA","NFL","NHL"):
        return {}
    cache_path = os.path.join(CACHE_DIR, f"alt_lines_{sport}.pkl")
    if os.path.exists(cache_path):
        age_mins = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_mins < 30:
            with open(cache_path, "rb") as f:
                return pickle.load(f)
    try:
        url = (f"{ODDS_API_BASE}/sports/{sport_key}/odds"
               f"?apiKey={ODDS_API_KEY}&regions=us,us2"
               f"&markets=alternate_spreads"
               f"&oddsFormat=american"
               f"&bookmakers=draftkings,fanduel,betmgm")
        resp = requests.get(url, headers=HEADERS, timeout=15)
        api_budget_increment("ODDS_API")
        if resp.status_code != 200:
            return {}
        events = resp.json()
        alt_data = {}
        for event in events:
            home = event.get("home_team","")
            away = event.get("away_team","")
            matchup = f"{away} @ {home}"
            lines = []
            for bm in event.get("bookmakers",[])[:2]:
                for mkt in bm.get("markets",[]):
                    if mkt.get("key") != "alternate_spreads":
                        continue
                    outcomes = mkt.get("outcomes",[])
                    # Group by point spread
                    for o in outcomes:
                        lines.append({
                            "team":  o.get("name",""),
                            "point": o.get("point",0),
                            "price": o.get("price",0),
                            "book":  bm.get("key",""),
                        })
            if lines:
                alt_data[matchup] = {
                    "home": home, "away": away,
                    "lines": lines,
                }
        if alt_data:
            with open(cache_path, "wb") as f:
                pickle.dump(alt_data, f)
        return alt_data
    except (requests.RequestException, ValueError, KeyError):
        return {}



def fetch_espn_game_ids(sport):
    slug_map = {"NBA": "basketball/nba", "MLB": "baseball/mlb", "NHL": "hockey/nhl", "NFL": "football/nfl", "WNBA": "basketball/wnba"}
    path = slug_map.get(sport)
    if not path:
        return {}
    cache_path = os.path.join(CACHE_DIR, f"espn_ids_{sport}.pkl")
    if os.path.exists(cache_path):
        age = (time.time() - os.path.getmtime(cache_path)) / 60
        if age < 30:
            with open(cache_path, "rb") as f:
                return pickle.load(f)
    game_ids = {}
    try:
        today_str = date.today().strftime("%Y%m%d")
        url = f"https://site.web.api.espn.com/apis/site/v2/sports/{path}/scoreboard?dates={today_str}"
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            return {}
        for event in resp.json().get("events", []):
            event_id = event.get("id", "")
            matchup = event.get("shortName", "")
            if event_id and matchup:
                game_ids[matchup] = event_id
        if game_ids:
            with open(cache_path, "wb") as f:
                pickle.dump(game_ids, f)
    except (ValueError, KeyError, TypeError, AttributeError):
        pass
    return game_ids


def fetch_espn_line_movement(sport, event_id):
    if not event_id:
        return []
    cache_path = os.path.join(CACHE_DIR, f"line_move_{event_id}.pkl")
    if os.path.exists(cache_path):
        age = (time.time() - os.path.getmtime(cache_path)) / 60
        if age < 15:
            with open(cache_path, "rb") as f:
                return pickle.load(f)
    sport_path = ESPN_CORE_SPORT_MAP.get(sport, "")
    if not sport_path:
        return []
    # Use site.web.api.espn.com (confirmed working on Streamlit Cloud)
    espn_sport_map = {"NBA": ("basketball","nba"), "MLB": ("baseball","mlb"), "NHL": ("hockey","nhl"), "NFL": ("football","nfl"), "WNBA": ("basketball","wnba")}
    if sport not in espn_sport_map:
        return []
    espn_sport, espn_league = espn_sport_map[sport]
    # Get game summary which includes odds/lines history
    url = f"https://site.web.api.espn.com/apis/site/v2/sports/{espn_sport}/{espn_league}/summary?event={event_id}&region=us&lang=en&contentorigin=espn"
    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}, timeout=10)
        if resp.status_code != 200:
            return []
        data = resp.json()
        # Extract odds info from header
        header = data.get("header", {})
        competitions = header.get("competitions", [{}])
        comp = competitions[0] if competitions else {}
        odds_list = comp.get("odds", [])
        movements = []
        for odd in odds_list:
            movements.append({
                "spread": odd.get("spread","—"),
                "over_under": odd.get("overUnder","—"),
                "home_ml": odd.get("homeTeamOdds",{}).get("moneyLine","—"),
                "away_ml": odd.get("awayTeamOdds",{}).get("moneyLine","—"),
                "provider": odd.get("provider",{}).get("name",""),
                "time": ""
            })
        if movements:
            with open(cache_path, "wb") as f:
                pickle.dump(movements, f)
        return movements
    except (pickle.UnpicklingError, OSError, EOFError, AttributeError):
        return []


def fetch_espn_predictor(sport, event_id):
    if not event_id:
        return {}
    cache_path = os.path.join(CACHE_DIR, f"predictor_{event_id}.pkl")
    if os.path.exists(cache_path):
        age = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age < 3:
            with open(cache_path, "rb") as f:
                return pickle.load(f)
    sport_path = ESPN_CORE_SPORT_MAP.get(sport, "")
    if not sport_path:
        return {}
    url = f"{ESPN_CORE_BASE}/sports/{sport_path}/events/{event_id}/competitions/{event_id}/predictor"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            return {}
        data = resp.json()
        home = data.get("homeTeam", {})
        away = data.get("awayTeam", {})
        predictor = {"home_win_pct": home.get("statistics", [{}])[0].get("value") if home.get("statistics") else None, "away_win_pct": away.get("statistics", [{}])[0].get("value") if away.get("statistics") else None, "home_projected_score": home.get("statistics", [{}, {}])[1].get("value") if home.get("statistics") and len(home.get("statistics", [])) > 1 else None, "away_projected_score": away.get("statistics", [{}, {}])[1].get("value") if away.get("statistics") and len(away.get("statistics", [])) > 1 else None}
        with open(cache_path, "wb") as f:
            pickle.dump(predictor, f)
        return predictor
    except (pickle.UnpicklingError, OSError, EOFError, AttributeError):
        return {}


def fetch_espn_player_gamelogs(sport, player_name, n_games=10):
    athlete_id = ESPN_ATHLETE_IDS.get(sport, {}).get(player_name)
    if not athlete_id:
        return None
    cache_path = os.path.join(CACHE_DIR, f"espn_gamelog_{sport}_{athlete_id}.pkl")
    if os.path.exists(cache_path):
        age = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age < 24:
            with open(cache_path, "rb") as f:
                return pickle.load(f)
    sport_path = ESPN_CORE_SPORT_MAP.get(sport, "")
    if not sport_path:
        return None
    season = 2025
    url = f"{ESPN_CORE_BASE}/sports/{sport_path}/seasons/{season}/athletes/{athlete_id}/eventlog?limit={n_games}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return None
        data = resp.json()
        game_stats = []
        for item in data.get("events", {}).get("items", [])[:n_games]:
            stats_ref = item.get("statistics", {}).get("$ref", "")
            if not stats_ref:
                continue
            try:
                stats_resp = requests.get(stats_ref, headers=HEADERS, timeout=REQUEST_TIMEOUT)
                if stats_resp.status_code != 200:
                    continue
                stats_data = stats_resp.json()
                game_stat = {}
                for split in stats_data.get("splits", {}).get("categories", []):
                    for stat in split.get("stats", []):
                        game_stat[stat.get("abbreviation", "").upper()] = stat.get("value", 0)
                if game_stat:
                    game_stats.append(game_stat)
                time.sleep(0.2)
            except (ValueError, KeyError, TypeError, AttributeError):
                continue
        if not game_stats:
            return None
        if sport == "NBA":
            avg = {"PTS": round(sum(g.get("PTS", 0) for g in game_stats) / len(game_stats), 1), "REB": round(sum(g.get("REB", 0) for g in game_stats) / len(game_stats), 1), "AST": round(sum(g.get("AST", 0) for g in game_stats) / len(game_stats), 1)}
            avg["PRA"] = round(avg["PTS"] + avg["REB"] + avg["AST"], 1)
        elif sport == "NFL":
            avg = {"PASS_YDS": round(sum(g.get("PASSYDS", g.get("YDS", 0)) for g in game_stats) / len(game_stats), 1), "RUSH_YDS": round(sum(g.get("RUSHYDS", g.get("RYDS", 0)) for g in game_stats) / len(game_stats), 1), "REC_YDS": round(sum(g.get("RECYDS", g.get("RECYD", 0)) for g in game_stats) / len(game_stats), 1), "TD": round(sum(g.get("TD", 0) for g in game_stats) / len(game_stats), 2)}
        else:
            avg = {}
        avg["n_games"] = len(game_stats)
        with open(cache_path, "wb") as f:
            pickle.dump(avg, f)
        return avg
    except (pickle.UnpicklingError, OSError, EOFError):
        return None


def fetch_player_id_bdl(player_name):
    """Search BallsDontLie for player ID by name."""
    if not BDL_API_KEY:
        return None
    cache_path = os.path.join(CACHE_DIR, f"bdl_pid_{normalize_name(player_name)}.pkl")
    if os.path.exists(cache_path):
        age_days = (time.time() - os.path.getmtime(cache_path)) / 86400
        if age_days < 7:
            with open(cache_path, "rb") as f:
                return pickle.load(f)
    try:
        r = requests.get(
            f"https://api.balldontlie.io/v1/players",
            headers={"Authorization": BDL_API_KEY},
            params={"search": player_name, "per_page": 5},
            timeout=10
        )
        if r.status_code == 200:
            data = r.json().get("data", [])
            if data:
                pid = data[0]["id"]
                with open(cache_path, "wb") as f:
                    pickle.dump(pid, f)
                return pid
    except (ValueError, KeyError, TypeError, AttributeError):
        pass
    return None



def fetch_mlb_confirmed_lineups():
    """
    Fetch confirmed MLB batting lineups for today's games.
    Uses statsapi.mlb.com — same API as mlb averages, already trusted.
    
    Returns dict: {team_abbr: [player1, player2, ...]} in batting order.
    Lineup is "confirmed" when it comes from today's actual game feed.
    
    Why this matters: cleanup hitter scratches move HR/RBI props significantly.
    A confirmed lineup vs a projected lineup is a real betting edge.
    """
    try:
        today_str = date.today().strftime("%Y-%m-%d")
        schedule_url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={today_str}&hydrate=lineups,probablePitcher"
        r = requests.get(schedule_url, timeout=10)
        if r.status_code != 200:
            return {}
        games = r.json().get("dates", [{}])[0].get("games", [])
        lineups = {}
        for game in games:
            game_id = game.get("gamePk")
            if not game_id:
                continue
            # Get lineups from game feed
            feed_url = f"https://statsapi.mlb.com/api/v1.1/game/{game_id}/feed/live?fields=gameData,liveData,boxscore,teams,batters,battingOrder,players,fullName,currentTeam,abbreviation"
            try:
                rf = requests.get(feed_url, timeout=8)
                if rf.status_code != 200:
                    continue
                feed = rf.json()
                # Extract home/away batting orders
                for side in ("home", "away"):
                    team_data = feed.get("liveData",{}).get("boxscore",{}).get("teams",{}).get(side,{})
                    batting_order = team_data.get("battingOrder", [])
                    players = team_data.get("players", {})
                    team_abbr = feed.get("gameData",{}).get("teams",{}).get(side,{}).get("abbreviation","")
                    if batting_order and team_abbr:
                        lineup = []
                        for pid in batting_order:
                            player_key = f"ID{pid}"
                            pdata = players.get(player_key, {})
                            pname = pdata.get("person",{}).get("fullName","")
                            pos = pdata.get("position",{}).get("abbreviation","")
                            if pname:
                                lineup.append({"name": pname, "position": pos, "batting_order": len(lineup)+1})
                        if lineup:
                            lineups[team_abbr] = {
                                "players": lineup,
                                "confirmed": len(lineup) >= 9,
                                "source": "MLB Stats API",
                                "fetched_at": datetime.now().strftime("%H:%M"),
                            }
            except (ValueError, KeyError, TypeError, AttributeError):
                continue
        return lineups
    except (requests.RequestException, ValueError, KeyError):
        return {}
# ═══════════════════════════════════════════════════════════════
# NFL READINESS SUITE
# Practice participation, inactives, O-line monitoring,
# depth chart snapshots, market open/close storage,
# prediction stability audit.
# ═══════════════════════════════════════════════════════════════

NFL_PRACTICE_PATH   = os.path.join(CACHE_DIR, "nfl_practice.json")
NFL_INACTIVES_PATH  = os.path.join(CACHE_DIR, "nfl_inactives.json")
NFL_DEPTH_SNAP_PATH = os.path.join(CACHE_DIR, "nfl_depth_snapshots.json")
OPENING_LINES_PATH  = os.path.join(CACHE_DIR, "opening_lines.json")
BOARD_SNAP_PATH     = os.path.join(CACHE_DIR, "board_snapshots.json")

# ── DraftKings Direct (curl_cffi) ─────────────────────────────

def fetch_draftkings_direct(sport):
    """Fetch DraftKings props directly using curl_cffi. Fallback when OddsPAPI is down."""
    try:
        from curl_cffi import requests as cf
        session = cf.Session(impersonate="chrome124")
    except ImportError:
        return []

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Origin": "https://sportsbook.draftkings.com",
        "Referer": "https://sportsbook.draftkings.com/",
    }

    # League IDs and player prop subcategory IDs
    league_map = {
        "NBA":  {"leagueId": "42648", "subCatId": "16477"},
        "MLB":  {"leagueId": "84240", "subCatId": "16477"},
        "NHL":  {"leagueId": "42133", "subCatId": "16477"},
        "WNBA": {"leagueId": "92483", "subCatId": "16477"},
        "NFL":  {"leagueId": "88670775", "subCatId": "16477"},
    }
    cfg = league_map.get(sport, league_map["NBA"])
    props = []

    cache_path = os.path.join(CACHE_DIR, f"draftkings_direct_{sport}.pkl")
    if os.path.exists(cache_path):
        age_mins = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_mins < 90:
            with open(cache_path, "rb") as f:
                cached = pickle.load(f)
            if cached:
                return cached

    try:
        lid = cfg["leagueId"]
        sid = cfg["subCatId"]

        url = "https://sportsbook-nash.draftkings.com/sites/US-SB/api/sportscontent/controldata/league/leagueSubcategory/v1/markets"
        params = {
            "isBatchable": "false",
            "templateVars": lid,
            "eventsQuery": f"$filter=leagueId eq '{lid}' AND clientMetadata/Subcategories/any(s: s/Id eq '{sid}')",
            "marketsQuery": f"$filter=clientMetadata/subCategoryId eq '{sid}' AND tags/all(t: t ne 'SportcastBetBuilder')",
            "include": "Events",
            "entity": "events",
        }

        r = session.get(url, params=params, headers=headers, timeout=15)
        if r.status_code != 200:
            return []

        data = r.json()
        events = data.get("events", [])
        markets = data.get("markets", [])
        selections = data.get("selections", [])

        # Build selection lookup by marketId
        sel_by_market = {}
        for sel in selections:
            mid = sel.get("marketId")
            if mid:
                sel_by_market.setdefault(mid, []).append(sel)

        for mkt in markets:
            mkt_name = mkt.get("name", "")
            mkt_id = mkt.get("id") or mkt.get("marketId")

            for sel in sel_by_market.get(mkt_id, []):
                label = sel.get("label", "")
                parts = sel.get("participants", [])
                player = parts[0].get("name","") if parts else ""
                if not player:
                    player = label
                line = sel.get("points") or sel.get("line") or sel.get("handicap")
                odds_am = sel.get("displayOdds", {}).get("american", "—")

                # Parse Over/Under from label
                if "Under" in label:
                    side = "UNDER"
                    if not player or player == label:
                        player = label.replace("Under","").strip()
                elif "Over" in label:
                    side = "OVER"
                    if not player or player == label:
                        player = label.replace("Over","").strip()
                else:
                    side = "OVER"
                # Extract line from label if not in fields
                if line is None:
                    import re as _re
                    _lm = _re.search(r"([\d.]+)", label)
                    if _lm:
                        try: line = float(_lm.group(1))
                        except Exception: pass

                if player and line is not None:
                    props.append({
                        "Player": player, "Prop": mkt_name,
                        "Line": float(str(line).replace("+", "")),
                        "Side": side,
                        "OverOdds": str(odds_am) if side == "OVER" else "—",
                        "UnderOdds": str(odds_am) if side == "UNDER" else "—",
                        "Book": "DraftKings", "Sport": sport,
                        "source": "draftkings_direct",
                    })

        # Cache
        if props:
            with open(cache_path, "wb") as f:
                pickle.dump(props, f)

    except Exception as _e:
            print(f"[WARN] {_e}")

    return props


# ── BetMGM Direct (curl_cffi) ─────────────────────────────────

def fetch_betmgm_direct(sport):
    """Fetch BetMGM props directly using curl_cffi."""
    try:
        from curl_cffi import requests as cf
        session = cf.Session(impersonate="chrome124")
    except ImportError:
        return []

    MGM_KEY = "N2Q4OGJjODYtODczMi00NjhhLWJlMWItOGY5MDUzMjYwNWM5"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Origin": "https://www.az.betmgm.com",
        "Referer": "https://www.az.betmgm.com/",
    }
    props = []

    cache_path = os.path.join(CACHE_DIR, f"betmgm_direct_{sport}.pkl")
    if os.path.exists(cache_path):
        age_mins = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_mins < 90:
            with open(cache_path, "rb") as f:
                cached = pickle.load(f)
            if cached:
                return cached

    # Sport config: sportId for listing fixtures
    sport_ids = {"NBA": 7, "MLB": 23, "NHL": 19, "WNBA": 7, "NFL": 11}
    sid = sport_ids.get(sport, 7)

    try:
        # Step 1: Get today's fixtures
        r1 = session.get(
            "https://www.az.betmgm.com/cds-api/bettingoffer/fixtures",
            params={
                "x-bwin-accessid": MGM_KEY,
                "lang": "en-us", "country": "US", "userCountry": "US",
                "subdivision": "US-AZ", "offerMapping": "Filtered",
                "sportIds": sid, "fixtureTypes": "Standard",
                "state": "Latest", "skip": 0, "take": 30, "sortBy": "StartDate",
            },
            headers=headers, timeout=15
        )
        if r1.status_code != 200:
            return []

        fixtures = r1.json().get("fixtures", [])

        # Step 2: For each fixture, get player props
        for fix in fixtures[:8]:
            fix_id = fix.get("id")
            if not fix_id:
                continue

            # Get all game IDs (market categories) for this fixture
            games = fix.get("games", [])
            prop_game_ids = []
            for g in games:
                gname = (g.get("name", {}).get("value", "") or "").lower()
                if any(kw in gname for kw in
                       ["point", "rebound", "assist", "strikeout", "hit",
                        "home run", "rbi", "goal", "shot", "save",
                        "yard", "touchdown", "pass", "rush", "pra",
                        "fantasy", "three", "steal", "block", "bases"]):
                    gid = g.get("id")
                    if gid:
                        prop_game_ids.append(str(gid))

            if not prop_game_ids:
                # Try fixture-offers without game filter
                prop_game_ids = [str(g.get("id","")) for g in games if g.get("id")]

            if not prop_game_ids:
                continue

            r2 = session.get(
                "https://www.az.betmgm.com/cds-api/bettingoffer/fixture-offers",
                params={
                    "x-bwin-accessid": MGM_KEY,
                    "lang": "en-us", "country": "US", "userCountry": "US",
                    "subdivision": "US-AZ",
                    "fixtureIds": fix_id,
                    "gameIds": ",".join(prop_game_ids[:10]),
                    "offerMapping": "Filtered",
                },
                headers=headers, timeout=10
            )
            if r2.status_code != 200:
                continue

            data2 = r2.json()
            fixture_data = data2.get("fixtures", [data2]) if isinstance(data2, dict) else data2

            for fd in fixture_data:
                for game in fd.get("games", []):
                    mkt_name = game.get("name", {}).get("value", "")
                    for result in game.get("results", []):
                        full_name = result.get("name", {}).get("value", "")
                        odds_d    = result.get("price", {}).get("americanOdds")
                        attr      = result.get("attr", "")

                        # Parse player name and side from full_name
                        player = full_name
                        side = "OVER"
                        if " Over " in full_name:
                            player = full_name.split(" Over ")[0].strip()
                            side = "OVER"
                        elif " Under " in full_name:
                            player = full_name.split(" Under ")[0].strip()
                            side = "UNDER"

                        line = attr or result.get("handicap")
                        if not player or line is None or line == "":
                            continue

                        try:
                            line_f = float(str(line).replace("+", ""))
                        except (ValueError, TypeError):
                            continue

                        odds_str = "—"
                        if odds_d is not None:
                            odds_str = f"{'+' if odds_d > 0 else ''}{int(odds_d)}"

                        props.append({
                            "Player": player, "Prop": mkt_name,
                            "Line": line_f, "Side": side,
                            "OverOdds": odds_str if side == "OVER" else "—",
                            "UnderOdds": odds_str if side == "UNDER" else "—",
                            "Book": "BetMGM", "Sport": sport,
                            "source": "betmgm_direct",
                        })

            time.sleep(0.3)

        if props:
            with open(cache_path, "wb") as f:
                pickle.dump(props, f)

    except Exception as _e:
            print(f"[WARN] {_e}")

    return props


# ── Caesars Direct (curl_cffi) ─────────────────────────────────

def fetch_caesars_direct(sport):
    """Fetch Caesars props directly via api.americanwagering.com."""
    try:
        from curl_cffi import requests as cf
        session = cf.Session(impersonate="chrome124")
    except ImportError:
        return []

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Origin": "https://sportsbook.caesars.com",
        "Referer": "https://sportsbook.caesars.com/",
    }
    props = []

    cache_path = os.path.join(CACHE_DIR, f"caesars_direct_{sport}.pkl")
    if os.path.exists(cache_path):
        age_mins = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_mins < 90:
            with open(cache_path, "rb") as f:
                cached = pickle.load(f)
            if cached:
                return cached

    sport_map = {
        "NBA": "basketball", "MLB": "baseball", "NHL": "icehockey",
        "WNBA": "basketball", "NFL": "americanfootball",
    }
    czr_sport = sport_map.get(sport, "basketball")
    base_url = f"https://api.americanwagering.com/regions/us/locations/az/brands/czr/sb/v4/sports/{czr_sport}"

    try:
        # Step 1: Get competitions (league IDs)
        r1 = session.get(f"{base_url}/competitions", headers=headers, timeout=15)
        if r1.status_code != 200:
            return []

        comps = r1.json()
        comp_list = comps if isinstance(comps, list) else comps.get("competitions", [])

        # Find the right competition for this sport
        target_names = {
            "NBA": ["nba"], "MLB": ["mlb", "major league"],
            "NHL": ["nhl", "national hockey"], "WNBA": ["wnba"],
            "NFL": ["nfl", "national football"],
        }
        targets = target_names.get(sport, ["nba"])
        comp_id = None

        for comp in comp_list:
            cname = (comp.get("name", "") or "").lower()
            cid = comp.get("id", "")
            if any(t in cname for t in targets):
                comp_id = cid
                break

        if not comp_id and comp_list:
            comp_id = comp_list[0].get("id", "")

        if not comp_id:
            return []

        # Step 2: Get player props for this competition
        prop_markets = [
            "Player Points", "Player Rebounds", "Player Assists",
            "Player Pts + Reb + Ast", "Player 3-Pointers",
            "Player Steals", "Player Blocks",
            "Pitcher Strikeouts", "Player Hits", "Player Home Runs",
            "Player RBIs", "Player Total Bases",
            "Player Goals", "Player Shots", "Player Saves",
            "Player Passing Yards", "Player Rushing Yards",
            "Player Receiving Yards", "Player Touchdowns",
        ]

        r2 = session.get(
            f"{base_url}/competitions/{comp_id}/tabs/SCHEDULE%7CPlayer%20Props",
            headers=headers, timeout=15
        )

        if r2.status_code == 200:
            data = r2.json()
            events = data.get("events", [])
            if not events:
                events = data.get("competitions", [{}])[0].get("events", []) if data.get("competitions") else []

            for event in events:
                for market in event.get("markets", []):
                    mname = market.get("name", "")
                    for sel in market.get("selections", []):
                        full_name = sel.get("name", "")
                        odds_d = sel.get("price", {}).get("d") or sel.get("price", {}).get("decimal")
                        odds_a = sel.get("price", {}).get("a") or sel.get("price", {}).get("american")
                        handicap = sel.get("points") or sel.get("handicap") or sel.get("line")

                        player = full_name
                        side = "OVER"
                        if " Over " in full_name:
                            player = full_name.split(" Over ")[0].strip()
                            side = "OVER"
                        elif " Under " in full_name:
                            player = full_name.split(" Under ")[0].strip()
                            side = "UNDER"

                        if not player or handicap is None:
                            continue

                        try:
                            line_f = float(str(handicap).replace("+", ""))
                        except (ValueError, TypeError):
                            continue

                        odds_str = "—"
                        if odds_a is not None:
                            odds_str = f"{'+' if float(odds_a) > 0 else ''}{int(float(odds_a))}"
                        elif odds_d is not None:
                            d = float(odds_d)
                            odds_str = f"+{int((d-1)*100)}" if d >= 2 else f"{int(-100/(d-1))}"

                        props.append({
                            "Player": player, "Prop": mname,
                            "Line": line_f, "Side": side,
                            "OverOdds": odds_str if side == "OVER" else "—",
                            "UnderOdds": odds_str if side == "UNDER" else "—",
                            "Book": "Caesars", "Sport": sport,
                            "source": "caesars_direct",
                        })

        if props:
            with open(cache_path, "wb") as f:
                pickle.dump(props, f)

    except Exception as _e:
            print(f"[WARN] {_e}")

    return props


# ── BetRivers Direct (Kambi backend) ──────────────────────────

def fetch_betrivers_direct(sport):
    """Fetch BetRivers props — Kambi backend, no auth needed."""
    try:
        from curl_cffi import requests as cf
        session = cf.Session(impersonate="chrome124")
    except ImportError:
        return []

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Origin": "https://az.betrivers.com",
        "Referer": "https://az.betrivers.com/",
    }
    props = []

    cache_path = os.path.join(CACHE_DIR, f"betrivers_direct_{sport}.pkl")
    if os.path.exists(cache_path):
        age_mins = (time.time() - os.path.getmtime(cache_path)) / 60
        if age_mins < 90:
            with open(cache_path, "rb") as f:
                return pickle.load(f)

    # Step 1: Get event list from Kambi
    sport_map = {"NBA": "basketball/nba", "MLB": "baseball/mlb", "NHL": "ice_hockey/nhl",
                 "WNBA": "basketball/wnba", "NFL": "american_football/nfl"}
    kambi_sport = sport_map.get(sport, "basketball/nba")

    try:
        r1 = session.get(
            f"https://eu-offering-api.kambicdn.com/offering/v2/rvn/listView/{kambi_sport}/all/all.json",
            params={"lang": "en_US", "market": "US-AZ", "useCombined": "true"},
            headers=headers, timeout=15
        )
        if r1.status_code != 200:
            return []

        events = r1.json().get("events", [])

        # Step 2: For each event, get player props
        for ev in events[:10]:
            ev_id = ev.get("event", {}).get("id")
            if not ev_id:
                continue

            r2 = session.get(
                f"https://az.betrivers.com/api/service/sportsbook/offering/playerprops",
                params={"groupId": ev_id, "pageNr": 1, "pageSize": 100, "cageCode": 602},
                headers=headers, timeout=10
            )
            if r2.status_code != 200:
                continue

            data = r2.json()
            items = data.get("items", data.get("offerings", []))
            if isinstance(items, dict):
                items = list(items.values())

            for item in items:
                # Kambi structure: criterion.label has prop name
                criterion = item.get("criterion", {})
                prop_label = criterion.get("label", "")

                for outcome in item.get("outcomes", []):
                    player = outcome.get("participantName", "") or outcome.get("label", "")
                    odds_am = outcome.get("americanOdds") or outcome.get("oddsAmerican")
                    line = outcome.get("line") or outcome.get("handicap") or outcome.get("overUnder")

                    # Parse Over/Under
                    side = "OVER"
                    otype = (outcome.get("type", "") or outcome.get("outcomeType", "")).upper()
                    if "UNDER" in otype or "Under" in str(outcome.get("label", "")):
                        side = "UNDER"

                    if not player or line is None:
                        continue

                    try:
                        line_f = float(str(line).replace("+", ""))
                    except (ValueError, TypeError):
                        continue

                    odds_str = "—"
                    if odds_am is not None:
                        odds_str = f"{'+' if float(odds_am) > 0 else ''}{int(float(odds_am))}"

                    props.append({
                        "Player": player, "Prop": prop_label,
                        "Line": line_f, "Side": side,
                        "OverOdds": odds_str if side == "OVER" else "—",
                        "UnderOdds": odds_str if side == "UNDER" else "—",
                        "Book": "BetRivers", "Sport": sport,
                        "source": "betrivers_direct",
                    })

            time.sleep(0.3)

        if props:
            with open(cache_path, "wb") as f:
                pickle.dump(props, f)

    except Exception as _e:
            print(f"[WARN] {_e}")

    return props


# ── Betr Direct (GraphQL, no auth) ────────────────────────────

def fetch_nfl_practice_participation():
    """
    NFL practice participation: DNP / Limited / Full.
    Pulled from ESPN injuries endpoint — details field contains
    practice status for NFL players.
    
    3-day trend matters most:
      DNP → DNP → DNP   = likely out
      DNP → Limited → Full = trending toward playing
      Full → Full → Full = healthy, no concern
    
    Returns dict: {player_name: {date: participation, trend: str}}
    """
    try:
        url = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/injuries"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if r.status_code != 200:
            return {}
        data = r.json()
        today_str = date.today().strftime("%Y-%m-%d")
        participation = {}
        for team in data.get("injuries", []):
            team_abbr = team.get("team", {}).get("abbreviation", "")
            for injury in team.get("injuries", []):
                athlete = injury.get("athlete", {})
                player  = athlete.get("displayName", "")
                detail  = injury.get("details", {})
                # ESPN practice field
                practice = detail.get("practiceStatus", "") or detail.get("detail", "")
                practice_lower = practice.lower()
                if "did not participate" in practice_lower or "dnp" in practice_lower:
                    pstatus = "DNP"
                elif "limited" in practice_lower:
                    pstatus = "Limited"
                elif "full" in practice_lower:
                    pstatus = "Full"
                else:
                    pstatus = None
                if player and pstatus:
                    if player not in participation:
                        participation[player] = {"team": team_abbr, "history": {}}
                    participation[player]["history"][today_str] = pstatus
        # Load stored history and merge
        stored = load_json_data(NFL_PRACTICE_PATH, {})
        for player, data_new in participation.items():
            if player in stored:
                stored[player]["history"].update(data_new["history"])
            else:
                stored[player] = data_new
        # Calculate 3-day trend
        for player, pdata in stored.items():
            hist = pdata.get("history", {})
            recent_days = sorted(hist.keys())[-3:]
            recent = [hist[d] for d in recent_days]
            if len(recent) >= 2:
                if recent[-1] == "Full" and recent[-2] in ("Limited", "DNP"):
                    pdata["trend"] = "↑ Trending UP"
                elif recent[-1] == "DNP" and all(r == "DNP" for r in recent):
                    pdata["trend"] = "⛔ DNP all week"
                elif recent[-1] == "Limited":
                    pdata["trend"] = "⚠️ Limited"
                elif recent[-1] == "Full":
                    pdata["trend"] = "✅ Full practice"
                else:
                    pdata["trend"] = recent[-1]
        save_json_data(NFL_PRACTICE_PATH, stored)
        return stored
    except Exception:
        return load_json_data(NFL_PRACTICE_PATH, {})



def fetch_nfl_inactives():
    """
    NFL official inactives — published 90 min before kickoff.
    Uses ESPN gamecenter endpoint which surfaces inactives
    once the official list is released.
    
    Returns dict: {team_abbr: [inactive_player_names]}
    """
    try:
        today_str = date.today().strftime("%Y%m%d")
        url = f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates={today_str}"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if r.status_code != 200:
            return {}
        events = r.json().get("events", [])
        inactives = {}
        for event in events:
            for comp in event.get("competitions", []):
                for team_data in comp.get("competitors", []):
                    team_abbr = team_data.get("team", {}).get("abbreviation", "")
                    roster    = team_data.get("roster", [])
                    team_inactives = []
                    for player in roster:
                        if player.get("active") is False or player.get("status","").upper() == "INACTIVE":
                            pname = player.get("athlete", {}).get("displayName", "")
                            if pname:
                                team_inactives.append(pname)
                    if team_inactives and team_abbr:
                        inactives[team_abbr] = team_inactives
        # Persist with timestamp
        if inactives:
            stamped = {"inactives": inactives, "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M")}
            save_json_data(NFL_INACTIVES_PATH, stamped)
            return inactives
        # Fall back to stored
        stored = load_json_data(NFL_INACTIVES_PATH, {})
        return stored.get("inactives", {})
    except Exception:
        return load_json_data(NFL_INACTIVES_PATH, {}).get("inactives", {})


# ── Feature 3: Offensive Line Monitoring ───────────────────────

def fetch_nhl_starting_goalies():
    """
    Fetch confirmed NHL starting goalies for today's games.
    Uses NHL official API — no bot protection, completely free.
    
    Starting goalie is the #1 factor in NHL props:
      - Opponent's shooter props affected by goalie quality
      - Team's scorer props affected by opposing goalie
      - Goalie saves/goals-against props directly
    
    Returns dict: {team_abbr: {"goalie": name, "confirmed": bool, "stats": {...}}}
    """
    try:
        today_str = date.today().strftime("%Y-%m-%d")
        # NHL schedule with goalie info
        url = f"https://api-web.nhle.com/v1/schedule/{today_str}"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0 BetCouncil/1.0"}, timeout=10)
        if r.status_code != 200:
            return {}

        data = r.json()
        goalies = {}

        # Navigate NHL schedule structure
        game_week = data.get("gameWeek", [])
        for day in game_week:
            for game in day.get("games", []):
                game_id = game.get("id")
                if not game_id:
                    continue
                for side in ("homeTeam", "awayTeam"):
                    team_data = game.get(side, {})
                    team_abbr = team_data.get("abbrev","")
                    # Check for goalie data in game object
                    goalie = team_data.get("goalieInNet", {}) or {}
                    goalie_name = ""
                    confirmed = False
                    if goalie:
                        first = goalie.get("firstName", {}).get("default","")
                        last  = goalie.get("lastName", {}).get("default","")
                        goalie_name = f"{first} {last}".strip()
                        confirmed = True

                    if team_abbr:
                        goalies[team_abbr] = {
                            "goalie":    goalie_name or "TBD",
                            "confirmed": confirmed,
                            "game_id":   game_id,
                            "opponent":  game.get("awayTeam" if side == "homeTeam" else "homeTeam", {}).get("abbrev",""),
                            "home":      side == "homeTeam",
                        }

        # If no goalies in schedule, try game center for confirmed starters
        if not any(g["confirmed"] for g in goalies.values()):
            for team_abbr, gdata in goalies.items():
                try:
                    gc_url = f"https://api-web.nhle.com/v1/gamecenter/{gdata['game_id']}/landing"
                    rg = requests.get(gc_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=6)
                    if rg.status_code == 200:
                        gc = rg.json()
                        side = "homeTeam" if gdata["home"] else "awayTeam"
                        starters = gc.get(side, {}).get("goalies", [])
                        for g in starters:
                            if g.get("starter"):
                                fn = g.get("firstName", {}).get("default","")
                                ln = g.get("lastName", {}).get("default","")
                                goalies[team_abbr]["goalie"]    = f"{fn} {ln}".strip()
                                goalies[team_abbr]["confirmed"] = True
                                break
                except Exception:
                    pass

        return goalies
    except (requests.RequestException, ValueError, KeyError):
        return {}


