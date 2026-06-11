# BetCouncil — Sportsbook API Endpoints Reference

## CONFIRMED WORKING (built into scraper + app)

### PrizePicks
- **URL:** `https://partner-api.prizepicks.com/projections?league_id={id}&per_page=250`
- **Method:** GET
- **Auth:** None (curl_cffi with Chrome impersonation)
- **League IDs:** NBA=7, MLB=2, NHL=12, WNBA=28, NFL=1

### DraftKings
- **URL:** `https://sportsbook-nash.draftkings.com/sites/US-SB/api/sportscontent/controldata/league/leagueSubcategory/v1/markets`
- **Method:** GET
- **Auth:** None
- **Params:** templateVars={leagueId}, eventsQuery, marketsQuery, include=Events, entity=events
- **League IDs:** NBA=42648, MLB=84240, NHL=42133, WNBA=92483, NFL=88670775
- **Response:** markets[], selections[] with label, displayOdds.american, participants[0].name

### FanDuel
- **Prices:** `https://smp.az.sportsbook.fanduel.com/api/sports/fixedodds/readonly/v1/getMarketPrices` (POST)
- **Events:** `https://api.sportsbook.fanduel.com/sbapi/event-page?_ak=FhMFpcPWXMeyZxOx&eventId={id}`
- **Content:** `https://api.sportsbook.fanduel.com/sbapi/content-managed-page?page=SPORT&eventTypeId={id}&_ak=FhMFpcPWXMeyZxOx`
- **API Key:** FhMFpcPWXMeyZxOx
- **Note:** PerimeterX blocks curl_cffi. Only works via OddsPAPI.

### BetMGM
- **Fixtures:** `https://www.az.betmgm.com/cds-api/bettingoffer/fixtures?x-bwin-accessid={key}&sportIds={id}`
- **Props:** `https://www.az.betmgm.com/cds-api/bettingoffer/fixture-offers?fixtureIds={id}&offerMapping=Filtered`
- **Access ID:** N2Q4OGJjODYtODczMi00NjhhLWJlMWItOGY5MDUzMjYwNWM5
- **Response:** fixtures[].optionMarkets[].options[] with name.value, price.americanOdds, attr

### Caesars
- **Base:** `https://api.americanwagering.com/regions/us/locations/az/brands/czr/sb/v4/sports/{sport}`
- **Competitions:** `{base}/competitions`
- **Props:** `{base}/competitions/{id}/tabs/SCHEDULE|Player Props`
- **Note:** 403 from Cloudflare on residential IP. Works via OddsPAPI only.

### Bovada
- **URL:** `https://www.bovada.lv/services/sports/event/coupon/events/A/description/{sport}/{league}`
- **Method:** GET
- **Auth:** None

## NEW BOOKS TO BUILD

### BetRivers (Kambi)
- **Props:** `https://az.betrivers.com/api/service/sportsbook/offering/playerprops?groupId={eventId}&pageNr=1&pageSize=100&cageCode=602`
- **Lines:** `https://eu-offering-api.kambicdn.com/offering/v2/rvn/event/{eventId}.json?lang=en_US&marketers=US-AZ`
- **Method:** GET
- **Auth:** None (cageCode=602 for Arizona)
- **Note:** Paginated — increment pageNr

### ESPN BET (theScore/PENN)
- **URL:** `https://sportsbook.us-default.thescore.bet/graphql/persisted_queries/{hash}`
- **Method:** GET
- **Hash:** 35c91eef7459e3a5edbc18424f85dfd6905fb0abf0a2a77660f6f34b51d4a72b
- **Headers:** apollographql-client-name: espnbet-espnbet-web, x-app: espnbet
- **Auth:** x-anonymous-authorization Bearer token (from cookies)

### Novig (Hasura/OpticOdds)
- **Ticker:** `https://api.novig.us/nbx/v1/live-event-ticker?liveLeagues=NFL,NBA,MLB,NHL,NCAAF,NCAAB,WNBA` (GET)
- **Props:** `https://api.novig.us/v1/graphql` (POST, operationName: EventMarkets_Query)
- **Auth:** None
- **Rate limit:** 600/window
- **Response:** data.event[].markets[] with player.full_name, strike, outcomes[].available

### Hard Rock Bet
- **URL:** `https://api.hardrocksportsbook.com/java-graphql/graphql` (POST)
- **Headers:** Origin: https://app.hardrock.bet
- **Auth:** None for GraphQL
- **Note:** Needs operationName from Payload tab

### ProphetX (WebSocket)
- **Gateway:** `wss://ws-mt1.pusher.com/app/c975574818f436e8dd4a?protocol=7&client=js&version=7.0.3`
- **Cluster:** mt1
- **App Key:** c975574818f436e8dd4a
- **Type:** Real-time streaming, not REST
