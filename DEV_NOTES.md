# BetCouncil v4.6 — Dev Notes
> Last updated: 2026-05-30 — read this at the START of every session

---

## Repo & Deploy
- **Repo:** `NewJerzzy/betcouncil-dashboard-streamlit`
- **Token:** `YOUR_GITHUB_TOKEN`
- **App:** `betcouncil-dashboard-app-zxseyipd6wydafpnwkszvw.streamlit.app`
- **Push cmd:** `GIT_ASKPASS=echo git push "https://YOUR_GITHUB_TOKEN@github.com/NewJerzzy/betcouncil-dashboard-streamlit.git" main`
- **Stack:** Streamlit + GitHub Gist persistence (11,163 lines, 137 functions)

---

## App Structure (tab line numbers)
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

## Key Functions & Locations
| Function | Line | Purpose |
|----------|------|---------|
| `_tier_why(r)` | 5557 | Plain-English tier reasoning for pick cards + summary |
| `generate_slip_summary()` | 5634 | Text report for slip analysis |
| `parse_bet_screenshot_ocr()` | 5755 | Main OCR entry point (Tesseract) |
| `parse_blob()` | ~5911 | Inner function — single-line blob parser (stat-anchored) |
| `is_player_name()` | ~5944 | Token-based name detection |
| `get_line()` | ~5866 | Line value extraction from OCR token |
| `_extract_line()` | ~5987 | Line value extraction inside blob parser |

---

## Session History — What Was Fixed (2026-05-30)

### OCR / Slip Analyzer (Tab 5) — most of this session
The slip analyzer was failing to parse screenshots. Root causes found and fixed:

1. **Expander collapsed on upload** — expander was `expanded=False`, button hidden
2. **PENDING picks filtered out** — open slips are PENDING, was skipping them (only kept WIN/LOSS)
3. **Nested expander** — OCR debug was inside a nested expander (Streamlit unsupported, silently breaks)
4. **No auto-parse** — required manual button click after upload
5. **Tesseract collapses slip to one line** — token parser found 0 picks because all content was 1 token. Fixed by adding `parse_blob()` — a stat-anchored parser that finds stats first, then works outward for player names and line values
6. **`O05` (capital-O zero)** — OCR reads `0` as `O`, so `0.5` became `O05`. Fixed with regex `\bO(\d{1,2})\b → \1`
7. **`6)` noise** — progress bar indicator read as line value. Fixed by stripping `)(][` before number matching
8. **Time strings `11h 38m`** — were matching as line values. Fixed by stripping `\d+[hm]` patterns
9. **Pagination `2/3`** — was matching `2` as line value. Fixed by stripping `\d+/\d+`
10. **`last_line_val` fallback** — 3rd pick's `0.5` fully OCR-garbled as `wtos`. Fixed by inheriting previous pick's line when current can't be extracted
11. **`_last_parsed_imgs` cache** — was blocking re-parse on Streamlit reruns, causing stale 1-pick result to persist. Removed cache, added `seek(0)`, switched to `_parsed_key` content-hash
12. **Infinite rerun loop** — parse ran every render because no guard. Fixed with `_parsed_key` hash that only re-parses on new uploads
13. **Summary missing "Why"** — `_tier_why()` added, explains tier in plain English. On-screen cards + text summary both show it
14. **No board warning** — when board not loaded, slip gets PASS/50% with no explanation. Fixed with yellow banner + explicit "run board first" message in Why text

### State Management
- `_parsed_key` — content hash of uploaded files, prevents re-parse loop
- `_auto_analyze` — set after parse, popped by analyze block to auto-run analysis once
- `analyzer_picks` — list of parsed picks for current slip
- `analyzer_results` — analysis results, persists until slip cleared

---

## Known Issues / Next Session Priorities

### HIGH — Fix Next Session
- [ ] **Trammell line shows 3.0** — `11h 3m` time string, the `3` survives stripping in some PSM modes. The time-strip regex `\d+[hm]` works in isolation but a specific Tesseract PSM output format may bypass it. Need to test with actual image + all 8 PSM/invert combos
- [ ] **Board must be run first for real analysis** — slip analyzer falls back to sparse historical averages when board is empty. Consider auto-triggering a lightweight board refresh when slip tab is opened
- [ ] **`signal_base` / `signal_def` not populated in no-board-match path** — these stay 0, so signal reasoning never fires even if historical data suggests it

### MEDIUM
- [ ] **`_tier_why` reasons joined with `\n         `** — display fine in text area but on-screen card renders them as one block. Should use `<br>` for card and `\n` for text
- [ ] **Losing screenshot detection** — `get_outcome()` doesn't distinguish individual pick outcomes from slip outcome for PrizePicks flex (partial wins possible). Currently marks all picks with entry outcome
- [ ] **MLB sport not always detected** — blob parser defaults to `MLB` hardcoded in UI layer (`bet.get("sport", "MLB")`). Should use detected sport from blob parser

### LOW
- [ ] **`PARLAYPLAY_COOKIES` session likely expired** — hardcoded session cookie, will need refresh
- [ ] **HEIC image support** — listed as accepted type but Pillow may not handle HEIC without `pillow-heif`

---

## Full Audit Checklist (run at session start)

```
1. Check Streamlit app is live and loads without error
2. Run board — verify data loads for at least NBA/MLB
3. Upload a PrizePicks screenshot to Enter Your Slip tab
   - Verify all picks parsed (not just 1)
   - Verify line values correct (0.5 not 3.0)
   - Verify analysis auto-runs
   - Verify Why reasoning shows on each card
4. Check System tab → error log for any runtime errors
5. Check OCR Debug text matches expected slip content
6. Manually add a pick and verify analysis runs
7. Log a bet and verify it saves to Gist
```

---

## Architecture Notes
- **Single file app** (`app.py`, ~11k lines) — all changes go here
- **No test suite** — test by running parser logic in standalone Python before pushing
- **Gist persistence** — history, locks, and settings stored in GitHub Gist (ID: `YOUR_GIST_ID`)
- **OCR pipeline:** Tesseract (8 passes: 2 invert × 4 PSM) → longest result → blob detection → parse_blob if compound stat found → token parser fallback
- **Analysis pipeline:** board match → full 5-signal model → fallback to historical PLAYER_AVERAGES dict → fallback to 50%/0 edge

---

## Before Every Push
```bash
python3 -c "import ast; ast.parse(open('app.py').read()); print('Syntax OK')"
```
