import requests
from bs4 import BeautifulSoup
import datetime
import json
import time
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

class BetCouncilEngine:
    def __init__(self):
        # --- CORE LEDGER ---
        self.bankroll = 529.64  
        self.emergency_floor = 0.12
        self.version = "3.4 - Master Production (Simultaneous)"
        
        # --- MAPPING DICTIONARIES ---
        self.SPORT_URL_SLUG = {
            "NBA": "nba", "MLB": "mlb", "NHL": "nhl", "NFL": "nfl",
            "WNBA": "wnba", "UFC": "ufc", "Golf": "golf",
            "Tennis": "tennis", "Soccer": "soccer",
        }
        
        self.SPORT_PATH_MAP = {
            "nba": "basketball/nba", "mlb": "baseball/mlb", "nhl": "hockey/nhl",
            "nfl": "football/nfl", "wnba": "basketball/wnba", "soccer": "soccer/champions-league",
            "ufc": "mma/ufc", "tennis": "tennis/atp", "golf": "golf/pga"
        }

        self.sources = {
            "GAMES": ["VegasInsider", "ESPN_JSON"],
            "PROPS": ["BettingPros", "OddsTrader", "SportsBettingDime"]
        }

        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        }

    def build_source_url(self, source, sport):
        slug = self.SPORT_URL_SLUG.get(sport.upper(), sport.lower())
        if source == "VegasInsider":
            return f"https://www.vegasinsider.com/{slug}/odds/las-vegas/"
        elif source == "ESPN_JSON":
            path = self.SPORT_PATH_MAP.get(sport.lower(), f"basketball/{slug}")
            return f"https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard"
        elif source == "BettingPros":
            return f"https://www.bettingpros.com/{slug}/picks/player-props/"
        elif source == "OddsTrader":
            return f"https://www.oddstrader.com/{slug}/player-props/"
        elif source == "SportsBettingDime":
            return f"https://www.sportsbettingdime.com/{slug}/props/"
        return None

    def parse_data(self, content, source_name):
        """Unified parser for both HTML and JSON sources."""
        data_points = []
        
        # Handle ESPN JSON
        if source_name == "ESPN_JSON":
            try:
                data = json.loads(content)
                for event in data.get("events", []):
                    data_points.append({
                        "target": event.get("shortName", "Unknown"),
                        "line": "Market Open", # ESPN API provides scores/matchups primarily
                        "source": source_name,
                        "category": "GAMES"
                    })
            except: pass
            return data_points

        # Handle HTML Sources
        soup = BeautifulSoup(content, "html.parser")
        if source_name == "VegasInsider":
            for row in soup.select("table.odds-table tr"):
                cells = row.select("td")
                if len(cells) >= 2:
                    data_points.append({
                        "target": cells[0].get_text(strip=True),
                        "line": cells[1].get_text(strip=True),
                        "source": source_name, "category": "GAMES"
                    })
        else:
            # Prop Sources: BettingPros, OddsTrader, SBD
            for card in soup.select(".prop-card, .player-prop-card, .props-table tr, .prop-row"):
                player = card.select_one(".player-name, .athlete-name, td:first-child, .player")
                line = card.select_one(".prop-line, .odds-value, td:nth-child(3), .odds")
                if player and line:
                    data_points.append({
                        "target": player.get_text(strip=True),
                        "line": line.get_text(strip=True),
                        "source": source_name, "category": "PROPS"
                    })
        return data_points

    def execute_single_sport_scan(self, sport):
        """Worker function for a single sport."""
        sport_results = []
        all_sources = self.sources["GAMES"] + self.sources["PROPS"]
        
        for source in all_sources:
            url = self.build_source_url(source, sport)
            if not url: continue
            try:
                resp = requests.get(url, headers=self.headers, timeout=8)
                if resp.status_code == 200:
                    points = self.parse_data(resp.text, source)
                    sport_results.extend(points)
            except: continue
        return sport_results

    def scan_all_simultaneously(self):
        """Launches 9 threads to scan all sports in parallel."""
        master_data = []
        start_time = time.time()
        sports = list(self.SPORT_URL_SLUG.keys())

        print(f"🛡️  BetCouncil {self.version}")
        print(f"📡 Initializing Global Scan: {', '.join(sports)}")

        with ThreadPoolExecutor(max_workers=len(sports)) as executor:
            future_to_sport = {executor.submit(self.execute_single_sport_scan, s): s for s in sports}
            
            for future in as_completed(future_to_sport):
                sport = future_to_sport[future]
                try:
                    data = future.result()
                    master_data.extend(data)
                    print(f"✅ {sport.ljust(7)} | Extracted {len(data)} data points")
                except Exception as e:
                    print(f"❌ {sport.ljust(7)} | Error: {e}")

        runtime = round(time.time() - start_time, 2)
        print(f"\n--- Global Scan Complete ({runtime}s) ---")
        self.generate_synthesis(master_data)

    def calculate_integrity(self, master_data):
        if not master_data: return 0
        # Check how many unique sources actually returned data
        active_sources = len(set(d['source'] for d in master_data))
        total_expected = len(self.sources["GAMES"]) + len(self.sources["PROPS"])
        return int((active_sources / total_expected) * 100)

    def generate_synthesis(self, master_results):
        integrity = self.calculate_integrity(master_results)
        print(f"🧠 THE BOARD OF 8 — CLARITY MODEL OUTPUT")
        print(f"Status: {'🛡️ SAFE' if integrity > 70 else '⚠️ VOLATILE'} | INTEGRITY: {integrity}%")
        print(f"Bankroll: ${self.bankroll} | Active Unit: ${round(self.bankroll * 0.0625, 2)}")
        
        # Filter for top tier targets (Sovereign/Elite)
        # This is where your weighted model scoring logic would live.
        print("\n> CURRENT SOVEREIGN TARGETS:")
        if not master_results:
            print("  [No data available for analysis]")
        else:
            # Example filtering for specific high-value players
            stars = ["LeBron", "Shai", "Luka", "Judge", "Ohtani"]
            found = [d for d in master_results if any(s in d['target'] for s in stars)]
            for item in found[:5]: # Show first 5 matches
                print(f"  ⭐ {item['target']} | {item['line']} ({item['source']})")

if __name__ == "__main__":
    engine = BetCouncilEngine()
    engine.scan_all_simultaneously()
