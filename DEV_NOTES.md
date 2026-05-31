# BetCouncil v4.6 — Dev Notes
> Last updated: 2026-05-31 — read this at the START of every session

---

## Repo & Deploy
- **Repo:** `NewJerzzy/betcouncil-dashboard-streamlit`
- **Token:** `YOUR_GITHUB_TOKEN`
- **App:** `betcouncil-dashboard-app-zxseyipd6wydafpnwkszvw.streamlit.app`
- **Push cmd:** `GIT_ASKPASS=echo git push "https://YOUR_GITHUB_TOKEN@github.com/NewJerzzy/betcouncil-dashboard-streamlit.git" main`
- **Stack:** Streamlit + GitHub Gist persistence (~11,300 lines, 137 functions)

---

## App Structure (tab line numbers — approximate, shift after edits)
| Tab | Name | Line |
|-----|------|------|
| 0 | Summary Dashboard | 8308 |
| 1 | Full Board | 8784 |
| 2 | Game Lines | 8905 |
| 3 | Locks & Ledger | 9046 |
| 4 | History | 9503 |
| 5 | Log Bet / Slip Analyzer | 9730 |
| 6 | Player Lookup | 10162 |
| 7 | System / Audit | 10624 |

---

## Key Functions & Locations (approximate)
| Function | Line | Purpose |
|----------|------|---------|
| `_tier_why(r, html=False)` | 5557 | Plain-English tier reasoning. html=True → `<br>` for cards |
| `generate_slip_summary()` | 5634 | Text report for slip analysis |
| `parse_bet_screenshot_ocr()` | 5755 | Main OCR entry point (Tesseract) |
| `parse_blob()` | ~5911 | Inner — single-line blob parser (stat-anchored) |
| `compute_multi_signal_edge()` | 6293 | Core 5-signal edge model |
| `load_sport_data()` | ~7400 | Main board load — calls all 35 data sources |
| `prizepicks_breakeven_prob()` | 1525 | Breakeven calc for n-pick parlays |

---

## Architecture — Data Flow
```
load_sport_data(sport)
  ├── fetch_prizepicks / fetch_underdog / fetch_parlayplay  → raw props
  ├── fetch_mlb_rolling_averages / fetch_nba_rolling_averages → player avgs
  ├── fetch_mlb_probable_pitchers → pitcher ERA per team
  ├── fetch_weather_for_game → weather_adj per city
  ├── fetch_nba_team_defense / fetch_team_recent_defense → opp_def_rating
  └── for each prop:
        compute_multi_signal_edge(line, avg, opp_def_rating, ...) → base edge+prob
        over_edge += pitcher_adj + weather_adj + blowout_adj + ...  ← MLB adjustments
        over_prob += mlb_extra (pitcher+weather)  ← FIXED 2026-05-31

Slip Analyzer (Tab 5):
  upload → parse_bet_screenshot_ocr() → parse_blob() → analyzer_picks
  → board match (_norm_stat for space-safe compare)
  → compute_multi_signal_edge() or historical fallback
  → _tier_why(r, html=True) for cards, html=False for text
```

---

## Signal Weights
| Sport | base | defense | location | rest | pace | pitcher | weather |
|-------|------|---------|----------|------|------|---------|---------|
| NBA   | 0.45 | 0.30    | 0.15     | 0.05 | 0.05 | —       | —       |
| MLB   | 0.40 | 0.15    | 0.10     | 0.05 | 0.00 | 0.15*   | 0.15*   |
| NFL   | 0.40 | 0.35    | 0.10     | 0.10 | 0.05 | —       | —       |

*MLB pitcher+weather: fetched and applied as post-hoc adjustments to both edge AND prob (fixed 2026-05-31)

---

## Session History

### 2026-05-31 — Full Audit Session
All 8 audit findings fixed in one push:

| # | Fix | Status |
|---|-----|--------|
| 1 | OCR time-strip `\d+[hm]` → `\d+\s*[hm]` | ✅ |
| 2 | Duplicate O-digit regex removed | ✅ |
| 3 | UI sport default MLB → NBA | ✅ |
| 4 | `_tier_why(html=False)` param — `<br>` for cards, `\n` for text | ✅ |
| 5 | Pick cards call `_tier_why(r, html=True)` | ✅ |
| 6 | MLB prob updated after pitcher+weather adj (was edge-only) | ✅ |
| 7 | signal_base/signal_def already stored — confirmed OK | ✅ |
| 8 | 31 silent except+pass → log to st.session_state['errors'] | ✅ |

### 2026-05-30 — OCR Session (14 fixes)
Full list in git history. Key fixes: blob parser, O05 OCR, time/pagination strip,
infinite rerun loop, board stat name matching (spaces around +), _tier_why reasoning.

---

## Known Issues / Next Session Priorities

### MEDIUM
- [ ] **Losing screenshot detection** — individual pick outcomes for PrizePicks flex
      (partial wins possible). Currently marks all picks with entry outcome.
- [ ] **ParlayPlay session cookie likely expired** — check System tab for 401/403 errors
- [ ] **HEIC image support** — listed as accepted but needs `pillow-heif`
- [ ] **Board auto-refresh on slip tab** — when board empty, auto-fetch for detected sport

### LOW
- [ ] **MLB_PLAYER_TEAM_MAP completeness** — pitcher adj only fires if player is in this map.
      Spot-check: does it include today's active MLB roster?
- [ ] **Weight optimizer** — WEIGHT_OPTIMIZER_MIN_BETS threshold. How many bets logged?
      If below threshold, falls back to hardcoded weights. Check in System tab.

---

## Full Audit Checklist (run at session start)
```
1. Syntax check: python3 -c "import ast; ast.parse(open('app.py').read()); print('OK')"
2. Run board (MLB + NBA) — verify props load, check prop count > 0
3. Check System tab → error log — should be clean or show known sources
4. Upload PrizePicks screenshot → verify 3 picks parse, lines correct (0.5 not 3.0)
5. Confirm analysis auto-runs after screenshot upload
6. With board loaded: verify Why reasoning shows real data (not "no live board")
7. Check MLB picks show pitcher/weather context in Why reasoning
8. Log a test bet → verify saves to Gist
```

---

## Before Every Push
```bash
python3 -c "import ast; ast.parse(open('app.py').read()); print('Syntax OK')"
```
