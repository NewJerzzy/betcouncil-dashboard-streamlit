---
name: Bobby's Bets open API
description: app.bobbysbets.com has a fully open REST API (no auth, no CF) with today's model picks, all props, live scoreboards, weather, and AI briefings
---

## Base URL
`https://app.bobbysbets.com`
nginx/1.24.0 Ubuntu — no Cloudflare, no auth on most endpoints.

## Sport slug map
| App sport | BB slug |
|-----------|---------|
| MLB | mlb |
| NFL | nfl |
| NHL | nhl |
| WNBA | wnba |
| Soccer | soccer |

## Open endpoints (no auth)

### Core picks + props
- `GET /api/{slug}/picks` — Bobby's curated model picks for today (graded A+/A/B+…)
- `GET /api/{slug}/props` — full board (e.g. 8 000+ MLB entries on big days)

### Metadata
- `GET /api/briefing?sport={slug}` — AI headline + subhead + spot for today
- `GET /api/slate/counts` — game counts all sports: `{nba,wnba,mlb,nhl,nfl,soccer,when}`

### Live scoreboards
- `GET /api/mlb/live/scoreboard` → `{games[], count, date}`
- `GET /api/wnba/live/scoreboard` → `{games[], fetched}`
- `GET /api/nhl/live/scoreboard` → `{games[], count, date}`
- `GET /api/world-cup/live` → `{matches[], fetched_at}`

### MLB player tools
- `GET /api/mlb/weather?team={abbr}` → `{team,stadium{name,dimensions,park_factor},weather{temp_f,wind_mph,wind_dir,humidity,condition},impact{summary,offense_boost,factors[]}}`
- `GET /api/mlb/pitcher-info?name={name}` → `{player{id,name,throws,bats,position,team}}`
- `GET /api/mlb/h2h?batter={id}&pitcher={id}` → `{batter,pitcher,games[],summary}`
- `GET /api/mlb/prop-gamelog?player={id}&stat={cat}` → `{games[]}`
- `GET /api/mlb/search?q={name}` → `{players[]}`

### Cross-book pricing
- `GET /api/prop-intel?sport={slug}&player={name}&stat={cat}&line={line}` → `{books[{book,overProb,american,best}],movement{series[],openProb,lastProb,movePts}}`
- `GET /api/best-prices?sport={slug}` → `{best{"{player}|{stat}|{line}|{Over/Under}":{book,odds,n_books}},edge{...}}`

## Auth-required (401)
`/api/picks`, `/api/games`, `/api/lines`, `/api/odds`, `/api/tail`, `/api/matchups`, `/api/schedule`

## Pick shape (MLB)
All picks include: `player_name, player_team, opponent_team, stat_category, line, label (Over/Under), odds_american, ev (%), grade (A+/A/B+/…), gradeScore, hit_rate_l5/l10/l15/l20, hit_rate_home/away/all, avg_stat_l5/l10, season_avg, current_streak, trend_direction, floor_value, ceiling_value, consistency_score, advanced_grade, is_model_pick (bool), ml_reasoning (AI text), opposing_pitcher_l3 {name,era,whip,k9,ip,hand}, dk_event_id, dk_outcome_id, game_date, game_time`

NFL picks add: `week, season, position, opp_rank, grade_score`

## Fetchers in fetchers.py
- `fetch_bobbys_bets_picks(sport, cache_minutes=15)` → list
- `fetch_bobbys_bets_props(sport, cache_minutes=15, min_grade=0)` → list
- `fetch_bobbys_bets_briefing(sport, cache_minutes=60)` → dict
- `fetch_bobbys_bets_scoreboard(sport, cache_minutes=3)` → list

**Why:** Cache pkl in CACHE_DIR (same pattern as mybookie/fanduel/etc.). No gist needed — API is always open.

## Wired in app_core.py
Isolated-batch block after VSIN splits block (~line 13905).
Session-state keys: `bobbys_picks`, `bobbys_props`, `bobbys_briefing`, `bobbys_scoreboard`
