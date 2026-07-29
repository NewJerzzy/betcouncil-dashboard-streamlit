# theScore Bet GraphQL — Real Findings (2026-07-29)

## Environment
- Real endpoint: `https://sportsbook.us-default.thescore.bet/graphql` (from `env.js`)
- WebSocket: `wss://sportsbook.us-default.thescore.bet/graphql/websocket`
- Hash confirmed current in live bundle `index-ab5134e6e9bdcfaf.js` (1.26MB): `4fcab2e9...`

## The Hash IS Current — But the Schema Gap Is 37 Errors, Not 1

Real HTTP 200 response with ALL feature flags properly set (false),
measured from Replit (neutral IP, no auth):

```
HTTP 200 | errors: 39 | data: False
Schema/type errors (not variable errors): 37
```

The prior session's "35 of 36 fixed" analysis was done against the WRONG endpoint
(`sportsbook.thescore.bet/api/graphql` → 405 Method Not Allowed).
The real endpoint is a subdomain.

## Full Error List With Feature Flags Set

| Line | Error |
|------|-------|
| 1231 | Cannot query field "abbreviation" on type "Team" |
| 1232 | Cannot query field "colour1" on type "Team" |
| 1233 | Cannot query field "logos" on type "Team" |
| 1191 | Unknown type "Country" |
| 1205 | Cannot query field "initials" on type "Player" |
| 1206 | Cannot query field "jerseyImage" on type "Player" |
| 1210 | Cannot query field "numberImage" on type "Player" |
| 1214 | Cannot query field "headshots" on type "Player" |
| 1218 | Cannot query field "country" on type "Player" |
| 1222 | Cannot query field "teams" on type "Player" |
| 1303 | Unknown type "RecommendedPropSelection" |
| 1269 | Unknown type "RecommendedProp" |
| 1327 | Unknown type "RecommendedPropSet" |
| 914  | Cannot query field "recommendedProps" on type "EventWrapper" |
| 921  | Unknown type "Interaction" |
| 923  | Unknown type "LinkInteraction" |
| 928  | Unknown type "OpenPlayerStatsSheetInteraction" |
| 934  | Unknown type "AddToBetslipInteraction" |
| 944  | Unknown type "AddFeaturedBetInteraction" |
| 950  | Unknown type "LocalFilterListInteraction" |
| 892  | Unknown type "BetSelector" |
| 873  | Unknown type "AvatarView" |
| 961  | Unknown type "MarketCardUI" |
| 985  | Unknown type "BaseballLiveInfo" |
| 997  | Unknown type "EventParticipant" |
| 1029 | Unknown type "FootballPossessionIndicator" |
| 1035 | Unknown type "RedCardIndicator" |
| 1040 | Unknown type "DotPossessionIndicator" |
| 1044 | Unknown type "PowerPlayIndicator" |
| 1055 | Unknown type "MarketParticipant" |
| 102  | Cannot query field "ui" on type "GridMarketCard" |
| 102  | Unknown argument "oddsFormat" on field "ui" of type "GridMarketCard" |

## Correct Required Variables

```js
{
  sectionId: "<node-id>",        // ID! REQUIRED — NOT competitionSlug
  includeRichEvent: false,       // Boolean! REQUIRED
  oddsFormat: "AMERICAN",        // OddsFormat! REQUIRED  
  selectedFilterId: null,        // required but nullable in practice
  pageType: "PAGE",              // PageType — but enum value may have changed
  // Optional booleans (all default false):
  isSubscription, includeRecommendedProps, isBrandingImageEnabled,
  isNewFeaturedBetParticipantLogoEnabled, isMarketHeaderRedesignEnabled,
  isFeaturedMarketCardRedesignEnabled, isDsModelRecommendedPropsEnabled
}
```

## Where sectionId Comes From

`sectionId` is a node relay ID obtained from `CompetitionPage`:
```
CompetitionPage(canonicalUrl: "/mlb") 
  → page.pageChildren[]
  → child.archetype === "CompetitionLines"
  → child.id  ← this is the sectionId
```

`CompetitionPage` returns 403 without auth. The browser Tampermonkey
context already has auth, so hooking fetch there gets it for free.

## The Fix: Intercept Instead of Replay

The 37 schema errors mean no data is returned from any call made outside
the browser. The persisted query document is stale — the schema was
substantially refactored (Team, Player, Country types all changed).

The correct approach for a Tampermonkey script is to intercept the site's
own fetch calls — the browser already has auth and correct sectionId,
and the server apparently still serves the site (possibly with partial 
execution or a different code path for authenticated users).
