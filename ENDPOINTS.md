# BetCouncil — Master API Endpoints Reference
Updated: 2026-06-10

## CONFIRMED WORKING (in scraper + app)

### PrizePicks
- `https://partner-api.prizepicks.com/projections?league_id={id}&per_page=250`
- Method: GET via curl_cffi (Chrome TLS impersonation)
- Auth: None

### DraftKings
- `https://sportsbook-nash.draftkings.com/sites/US-SB/api/sportscontent/controldata/league/leagueSubcategory/v1/markets`
- Method: GET via curl_cffi
- Params: templateVars={leagueId}, eventsQuery, marketsQuery, include=Events, entity=events
- League IDs: NBA=42648, MLB=84240, NHL=42133, WNBA=92483, NFL=88670775
- Subcategory (player props): 16477
- Auth: None

### FanDuel
- Events: `https://api.sportsbook.fanduel.com/sbapi/event-page?_ak=FhMFpcPWXMeyZxOx&eventId={id}`
- Prices: `https://smp.az.sportsbook.fanduel.com/api/sports/fixedodds/readonly/v1/getMarketPrices`
- API Key: FhMFpcPWXMeyZxOx
- Note: PerimeterX blocks curl_cffi — only works via OddsPAPI

### BetMGM
- Fixtures: `https://www.az.betmgm.com/cds-api/bettingoffer/fixtures`
- Props: `https://www.az.betmgm.com/cds-api/bettingoffer/fixture-offers?fixtureIds={id}&offerMapping=Filtered`
- Access ID: N2Q4OGJjODYtODczMi00NjhhLWJlMWItOGY5MDUzMjYwNWM5
- Props in: optionMarkets[].options[] (name.value, price.americanOdds, attr)

### Caesars
- Competitions: `https://api.americanwagering.com/regions/us/locations/az/brands/czr/sb/v4/sports/{sport}/competitions`
- Props: `...competitions/{id}/tabs/SCHEDULE|Player Props`
- Note: 403 from Cloudflare — only works via OddsPAPI

### Bovada
- `https://www.bovada.lv/services/sports/event/coupon/events/A/description/{sport}/{league}`
- Method: GET, no auth

## NEW — READY TO BUILD

### BetRivers (Kambi)
- Props: `https://az.betrivers.com/api/service/sportsbook/offering/playerprops?groupId={eventId}&pageNr=1&pageSize=100&cageCode=602`
- Lines: `https://eu-offering-api.kambicdn.com/offering/v2/rvn/event/{eventId}.json?lang=en_US&marketers=US-AZ`
- Auth: None, paginated (pageSize up to 100)

### ESPN BET (theScore/PENN)
- `https://sportsbook.us-default.thescore.bet/graphql/persisted_queries/{sha256Hash}`
- Method: GET with query params
- Headers: apollographql-client-name=espnbet-espnbet-web, x-app=espnbet
- Hash: 35c91eef7459e3a5edbc18424f85dfd6905fb0abf0a2a77660f6f34b51d4a72b
- Auth: x-anonymous-authorization Bearer token (session-based)

### Novig (Hasura/OpticOdds)
- Ticker: `https://api.novig.us/nbx/v1/live-event-ticker?liveLeagues=NFL,NBA,MLB,NHL,NCAAF,NCAAB,WNBA`
- Props: `https://api.novig.us/v1/graphql` (POST, operationName=EventMarkets_Query)
- Auth: None
- Rate limit: 600/window
- `available` field = implied probability (not American odds)

### Hard Rock Bet
- `https://api.hardrocksportsbook.com/java-graphql/graphql`
- Method: POST (GraphQL)
- Headers: Origin=https://app.hardrock.bet, Referer=https://app.hardrock.bet/
- Needs: operationName from Payload tab

### ProphetX (WebSocket streaming)
- `wss://ws-mt1.pusher.com/app/c975574818f436e8dd4a?protocol=7&client=js&version=7.0.3`
- Cluster: mt1
- App Key: c975574818f436e8dd4a
- Real-time only, subscribe to channels for player-specific updates
