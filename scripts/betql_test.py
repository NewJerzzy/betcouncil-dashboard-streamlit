import json, os, sys, requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
API_URL = "https://api.betql.co/graphql"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Content-Type": "application/json",
    "Accept": "application/json",
}

TEST_QUERY = """
query GetEvents($after: DateTime!, $before: DateTime!, $league: LeagueEnum!, $limit: Int!) {
  events(after: $after, before: $before, eventType: TEAM, league: $league, limit: $limit) {
    id
    slugId
    startDate
    homeTeam { lastName }
    awayTeam { lastName }
    lines {
      type period homeSpread awaySpread homePrice awayPrice
      homeMoney awayMoney drawMoney total overPrice underPrice
      book { name }
    }
    communityStats {
      betType awayCount homeCount drawCount
    }
    homePlayerProps {
      player { fullName }
      props {
        propName propAbbreviation bookValue projectedValue direction stars
        book { name }
      }
    }
  }
}
"""

def main():
    from datetime import datetime, timezone, timedelta
    token = os.environ.get("GITHUB_TOKEN")
    now = datetime.now(timezone.utc)
    after = now.strftime("%Y-%m-%dT00:00:00.000Z")
    before = (now + timedelta(days=1)).strftime("%Y-%m-%dT23:59:59.999Z")
    body = {
        "operationName": "GetEvents",
        "query": TEST_QUERY,
        "variables": {"after": after, "before": before, "league": "MLB", "limit": 3},
    }
    r = requests.post(API_URL, json=body, headers=HEADERS, timeout=20)
    result = {"status": r.status_code, "len": len(r.text), "sample": r.text[:2500]}

    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_bettingpros_debug.json": {"content": json.dumps({"note": "TEMP betql schema test", "result": result}, default=str)}}},
    )
    print("push:", resp.status_code)
    return 0

if __name__ == "__main__":
    sys.exit(main())
