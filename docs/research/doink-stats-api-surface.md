# Doink Stats API observed public surface

Snapshot dates: 2026-08-27 and 2026-08-28 UTC

## Scope and access rules

This review used unauthenticated public requests only. It did not use credentials, cookies, private routes, paid-game IDs, or attempts to defeat subscription controls.

Current-game tests used IDs from public `free_game_ids` arrays. The historical NFL test used a game ID from a publicly indexed Doink page:

- Public page: `https://doinksports.com/research/nfl/game/gm_aydyggwcszsichknj4dsxt5c`
- Page title: `Ravens at Bills - NFL | Doink Sports`
- The page redirects its overview to `/box-score` and embeds the same `gameId`.

The result is an observed, point-in-time route inventory for an undocumented service. It is not a claim that no other server-only or future routes exist, and it is not permission to ingest the service.

Doink Sports' Terms of Service, last updated 2024-01-12, prohibit automated or non-human access. BetCouncil production ingestion remains blocked unless Doink grants explicit written programmatic-use permission.

## Executive result

- Ten `stats.doinkapis.com` GET route shapes were confirmed from public frontend bundles and unauthenticated responses.
- Current NFL `/games/slate` returned `200` with empty `free_game_ids` and `game_slate` arrays, even while ESPN listed preseason games. Alternate `nfl_preseason` and `nfl-preseason` slugs were rejected; `nfl` is the frontend's league slug.
- No current public NFL game ID, current prop-price feed, or standalone current NFL odds route was confirmed.
- Public historical NFL IDs expose much more than the current-slate result suggested: box scores, settlement lines, team/player game logs, defense-vs-position logs, rosters, and an injuries envelope.
- The historical player/DVP log responses contain the outcome categories needed for prop research, including passing, rushing, receiving, targets, touchdowns, red-zone usage, usage shares, quarter/half/OT splits, rest, and historical settlement lines. They do **not** constitute current sportsbook prop offers or current prices.
- MLB and WNBA had populated current slates. Their game mappings identified Sportradar. NFL roster mappings named Sportradar, Unabated, and Sleeper; the tested box-score payload additionally contained OddsBlaze mappings. Weather icons were hosted by WeatherAPI.com.
- No connector, fetcher, or scheduled ingestion was added.

## Discovery methodology

### 1. Framework and infrastructure reconnaissance

The public site is a Next.js App Router application:

- HTML contains React Server Component `self.__next_f` payloads.
- Assets are under `/_next/static/chunks/`.
- Public route manifests enumerate human-facing research paths separately from stats API calls.

The stats host returned Flask/Werkzeug-style HTML `404` pages. Public responses were served through Cloudflare, allowed cross-origin requests, and identified the route methods as `OPTIONS, GET, HEAD`.

The following documentation/discovery paths returned HTML `404`:

- `/`
- `/openapi.json`
- `/docs`
- `/.well-known/openapi.json`
- `/.well-known/ai-plugin.json`
- `/swagger.json`
- `/api-docs`
- `/health`
- `/robots.txt`

`OPTIONS /v1/leagues/nfl/games/slate` returned `Allow: OPTIONS, GET, HEAD`. `HEAD` returned the same JSON content metadata as `GET`. No mutating method was sent.

### 2. Public JavaScript bundle inventory

One public request was made to each of these pages:

- `/research/mlb`
- `/research/nfl`
- `/research/nfl/hit-rater`
- the indexed Ravens-Bills overview
- its `box-score`, `player-props`, `touchdowns`, `over-under`, `team-props`, `sides`, and `injuries` pages

All script assets referenced by those pages were downloaded once and searched locally. The inventory contained:

- 11 public pages;
- 90 unique JavaScript assets;
- 3,511,450 total script bytes; and
- 7 assets containing route-producing `v1/leagues/` strings.

Relevant immutable asset names and SHA-256 prefixes at the snapshot:

| Asset | SHA-256 prefix | Observed route construction |
| --- | --- | --- |
| `24088-007497de107f918b.js` | `2931a179b5e91811` | game metadata, state |
| `88940-975de76d951dd0eb.js` | `d4dc2bb1d5455ffd` | weather forecast |
| `app/research/layout-5a647c8bff045808.js` | `d0fff5a480ddc09d` | slate, state, stats API base |
| `8656-ee50a43bd5878825.js` | `37f7f96a7fbd630a` | slate |
| `app/research/nfl/game/%5BgameId%5D/page-9ac44c6bce540e1b.js` | `c9009e1e6be5abdd` | weather forecast |
| `78270-cbcfa404aefefccd.js` | `ce663b52041407e3` | box score and `grade=true` |
| `59816-7991fc58225c76d2.js` | `6e9771e6e28bc800` | player/team/DVP game logs, injuries, roster |

The exhaustive search of these 90 referenced assets found the ten stats route shapes listed below. Human-facing strings such as `/player-props`, `/touchdowns`, `/team-props`, and `/sides` also occur in route manifests, but those are `doinksports.com/research/...` page paths, not evidence of equivalent `stats.doinkapis.com` endpoints.

### 3. Conservative direct probing

Each bundle-confirmed route was requested once with a public free-game ID or an ID embedded in the publicly indexed historical NFL response. Responses and schemas are summarized below.

The slate endpoint was also compared with harmless query variants:

- NFL base, `?date=2026-08-28`, `?season=2026`, and `?week=1` returned byte-identical 37-byte responses.
- MLB base, `?date=2026-08-28`, and `?free=true` returned byte-identical 69,310-byte responses.

Those query names were ignored in the tested snapshot; they are not documented parameters.

Guessed game suffixes for `odds`, `player-props`, `team-props`, `touchdowns`, `sides`, and `injuries` returned `404`. This does not prove that current product data has no private or server-only source; it only means no corresponding public stats route was observed or confirmed.

### 4. GitHub, Apidog, search-index, and archive research

- Exact web/GitHub searches for `stats.doinkapis.com`, `doinkapis v1 leagues games`, and Doink API repositories found no public Doink API repository, client, or route documentation. Similar-name results were unrelated.
- Exact Apidog searches for Doink Sports and `stats.doinkapis.com` found no matching public project. Returned sports projects belonged to unrelated vendors.
- Public search indexing produced multiple Doink NFL game URLs. The Ravens-Bills URL above was used because it was directly accessible without authentication.
- Wayback CDX returned no archived `stats.doinkapis.com` JSON URLs. A broader Doink page query did return historical NFL research pages, including old `/box-score`, `/hit-grid`, `/prop-progress`, `/over-under`, `/sides`, and `/team-props` page paths. These are page-path evidence, not stats-host route evidence.
- A later narrower CDX retry timed out once and then returned no rows. The successful broader result and live search-index result were sufficient to establish a public historical ID without guessing one.

## Confirmed observed GET routes

| Route | Unauthenticated result | Client refresh / response cache |
| --- | --- | --- |
| `/v1/leagues/{league}/games/slate` | `{free_game_ids, game_slate}` | client 60 s; `max-age=60` |
| `/v1/leagues/{league}/games/{game_id}` | `{game}` for free MLB/WNBA IDs | client 60 s |
| `/v1/leagues/{league}/games/{game_id}/state` | `{game_state}` for free MLB/WNBA IDs | client 10 s |
| `/v1/leagues/{league}/games/{game_id}/weather-forecast` | `{weather_forecast}` for a scheduled free MLB game | client 30 min; observed `max-age=600` |
| `/v1/leagues/{league}/games/{game_id}/box-score` | `{box_score}` for the indexed historical NFL ID | client 10 s; `max-age=5` |
| `/v1/leagues/{league}/players/{player_id}/game-logs` | `{vectorized_game_logs, averages}` for an NFL player in the historical response | client 1 h; `max-age=18000` |
| `/v1/leagues/{league}/teams/{team_id}/game-logs` | `{vectorized_game_logs}` for the historical NFL team | client 1 h; `max-age=18000` |
| `/v1/leagues/{league}/teams/{team_id}/dvp-game-logs?primary_position={position}[&position_rank={rank}]` | `{vectorized_game_logs}` for NFL `WR`, rank 1 | client 1 h; `max-age=18000` |
| `/v1/leagues/{league}/teams/{team_id}/injuries` | `{injuries: []}` for the historical NFL team at the snapshot | client configuration observed; `max-age=300` |
| `/v1/leagues/{league}/teams/{team_id}/players` | `{players}`; 117 NFL roster records for the historical team ID | client configuration observed; `max-age=14400` |

The box-score client also constructs `?grade=true`. It returned `200` and the same schema plus `game_grades`, `grades` containers, but those containers were empty for the historical sample.

### League coverage at the first snapshot

| League slug | HTTP | Games | Free game IDs | Mapping providers |
| --- | ---: | ---: | ---: | --- |
| `mlb` | 200 | 37 | 31 | Sportradar |
| `wnba` | 200 | 7 | 6 | Sportradar |
| `nfl` | 200 | 0 | 0 | none in empty response |
| `nba` | 200 | 0 | 0 | none in empty response |
| `nhl` | 200 | 0 | 0 | none in empty response |
| `ncaafb` | 200 | 0 | 0 | none in empty response |
| `ncaamb` | 200 | 0 | 0 | none in empty response |

`ncaab` returned JSON `404` with `{"code":404,"message":"League not found"}`. Empty arrays are only point-in-time observations.

## Response schema inventory

Types below describe observed successful payloads. League-specific objects differ.

### Slate, metadata, and state

```text
Slate = {
  free_game_ids: string[],
  game_slate: Game[]
}

Metadata = { game: Game }

Team = {
  id, league, abbr, city, mascot, full_name, color: string
}
```

An observed MLB `Game` contained:

```text
{
  id, league: string,
  season: integer,
  game_time: ISO-8601 string,
  is_postseason: boolean,
  day_night: string,
  broadcast: { network: string },
  away_team, home_team: Team,
  away_pitcher, home_pitcher: Player,
  venue: {
    id, name, market, address, city, state, zip, country: string,
    capacity: integer,
    location: { lat, lng: string },
    field_orientation, stadium_type, surface, time_zone: string
  },
  state: MlbGameState,
  id_mappings: [{ provider, id }]
}
```

The WNBA game shape omitted MLB-only pitcher, broadcast, and park fields. Its venue added `sr_id`; its state used basketball period/clock/score fields.

```text
MlbGameState = {
  status: string,
  timestamp: ISO-8601 string,
  away, home: {
    runs, hits, errors: integer,
    inning_runs: (integer | "X")[]
  },
  runners: array
}

WnbaGameState = {
  status: string,
  timestamp: ISO-8601 string,
  period: string,
  clock: { minutes: integer, seconds: number, running: boolean },
  away, home: { points: integer, bonus: boolean, timeouts: integer }
}
```

The state `timestamp` was the only payload refresh timestamp in slate, metadata, and state responses. The original MLB slate's timestamps ranged from `2026-08-26T04:03:50.843819Z` to `2026-08-27T03:51:49.981729Z`.

### Weather

```text
{
  weather_forecast: [{
    time, last_updated: ISO-8601 string,
    closest_to_game_time, weather_available: boolean,
    text, icon, wind_dir: string,
    temp_f, humidity, wind_mph, chance_of_rain: number
  }]
}
```

The scheduled MLB sample returned four hourly rows. Weather rejected WNBA with JSON `400` and stated that it accepts only `mlb`, `nfl`, and `ncaafb`. A completed free MLB game returned JSON `404`; a scheduled free MLB game returned a forecast.

### Historical NFL box score

The reproducible historical response was 85,955 bytes and had:

```text
{
  box_score: {
    league: string,
    game: {
      id, league, season, season_type, week, game_time,
      is_postseason, primetime, state, venue, away_team, home_team
    },
    game_odds: { spread: number, over_under: number, home_is_favored: boolean },
    game_stats: {
      first_td_player_id,
      points, points_h1, points_h2, points_ot,
      points_q1, points_q2, points_q3, points_q4
    },
    away_team, home_team: {
      league, team,
      stats: {
        did_win, points and period splits, handicap and period splits,
        team_first_td, team_last_td,
        fourth_down_attempts, fourth_down_conversions,
        two_point_attempts, two_point_conversions,
        total_extra_point_opportunities
      }
    },
    away_players, home_players: [{
      league,
      player,
      position: { primary, rank },
      stats
    }]
  }
}
```

The sample had 13 away and 12 home player rows. Player identity objects included bio/team data and provider mappings. The union of player-stat fields covered:

- passing attempts/completions/yards/TDs/INTs, rating, sacks, air yards, target quality, pressure, and pocket time;
- rushing attempts/yards/TDs, scrambles, broken tackles, lost yards, yards after contact;
- receptions/targets/yards/TDs, air yards, catchable passes, drops, yards after catch/contact;
- combined rush/receive yards;
- first/last touchdown;
- red-zone attempts/targets;
- rush, target, and red-zone shares; and
- game, half, quarter, and overtime splits where present.

This is historical outcome and settlement data. It is not a feed of current prop offers or prices.

### Historical player/team/DVP logs

All three log routes return column-oriented JSON:

```text
{
  vectorized_game_logs: {
    "field.path": [value_for_game_1, value_for_game_2, ...],
    ...
  },
  averages?: object
}
```

The tested player log had 271 columns across 52 games. Columns included game/team/state metadata, historical spread/total/favorite, player position, rest, roster IDs, and the player stat categories above.

The team log contained team/game/settlement columns across 52 games. The DVP response contained opponent player identity plus the same stat families across 108 rows for the selected position/rank.

These are useful research statistics, but they are historical inputs/outcomes rather than current lines, current projections, or precomputed Doink recommendations.

### Roster and injuries

```text
Roster = {
  players: [{
    id, league, first_name, last_name, full_name, preferred_name,
    birthdate, height, weight, jersey_number, status,
    has_headshot, headshot_url,
    position, team,
    id_mappings: [{ provider, id }]
  }]
}

Injuries = { injuries: Injury[] }
```

The tested historical NFL team returned 117 roster records and an empty injuries array. Because the array was empty, the injury-item schema and current injury freshness were not established.

## Rate, refresh, and cache observations

- No `RateLimit`, `X-RateLimit-*`, or `Retry-After` headers appeared.
- A conservative sequence of 10 unauthenticated NFL slate GETs all returned `200`; none returned `429`.
- Observed response `max-age` values were: slate 60 s, box score 5 s, historical logs 18,000 s, injuries 300 s, roster 14,400 s, and weather 600 s.
- The frontend refreshes state every 10 s, box score every 10 s, slate/metadata every 60 s, weather every 30 min, and historical logs every hour.
- `last-modified` on tested responses reflected response generation time. It should not be interpreted as source-event freshness.

This small test does not establish the absence of a server-side rate limit.

## Upstream data versus Doink calculations

Confirmed upstream/provider evidence:

- current MLB/WNBA game mappings: Sportradar;
- NFL roster mappings: Sportradar, Unabated, Sleeper;
- tested NFL box-score player mappings: Sportradar, Unabated, Sleeper, and OddsBlaze;
- weather condition icons: WeatherAPI.com; and
- server-rendered sportsbook configuration: Odds API, Unabated, and OddsBlaze mappings.

The last configuration item is not itself a public price payload.

Confirmed Doink-owned shaping or calculations:

- Doink-normalized `gm_`, `tm_`, `pl_`, and `vn_` IDs and response envelopes;
- column-oriented `vectorized_game_logs`;
- derived averages container;
- usage shares, DVP selection, settlement-oriented handicap/outcome fields; and
- optional grade containers constructed by `?grade=true` (empty in the sample).

Raw provider mappings do not establish which upstream source supplied every stat or derived value. Treat the normalized and derived fields as Doink's application layer unless Doink documents otherwise.

Human-facing matchup factors, hit grids, prop progress, trends, current prop cards, and recommendation presentation were not confirmed as public stats-host payloads in this review.

## Missing or unconfirmed data

Not confirmed from a current public NFL slate/game:

- current NFL games or free game IDs;
- current sportsbook moneylines, spreads, or totals;
- current player/team/touchdown prop offers and prices;
- current injury records or their item schema;
- current box scores or live research refresh behavior; and
- current Doink projections, recommendations, matchup factors, hit grids, or prop-progress payloads.

Historical routes prove that the stats host exposes NFL facts and research-ready history. They do not prove that current or paid-game product data is intentionally available for programmatic use.

## BetCouncil decision

Do not add a Doink fetcher to `fetchers.py`, `app_core.py`, a workflow, or any other ingestion path. The current public surface does not establish a usable current NFL/prop-price feed, and Doink's terms make automated production ingestion unsuitable without written permission.

If Doink grants permission later:

1. obtain an explicit API contract and allowed route/rate scope;
2. re-confirm current schemas and freshness semantics;
3. determine whether current prices and injuries are licensed for redistribution; and
4. identify which fields are Doink calculations versus upstream licensed data.

Otherwise, source equivalent games, lines, props, injuries, and statistics directly from licensed providers.