import json, os, sys, requests
GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
def main():
    token = os.environ.get("GITHUB_TOKEN")
    result = {}
    r = requests.get("https://api.smarkets.com/v3/events/", params={"type":"baseball_match","state":"upcoming"}, timeout=15)
    result["events"] = {"status": r.status_code, "sample": r.text[:1500]}
    try:
        events = r.json().get("events", r.json().get("results", []))
        result["num_events"] = len(events)
        if events:
            eid = events[0].get("id") if isinstance(events[0], dict) else events[0]
            result["sample_event"] = events[0]
            r2 = requests.get("https://api.smarkets.com/v3/markets/", params={"event_ids": eid}, timeout=15)
            result["markets"] = {"status": r2.status_code, "sample": r2.text[:1500]}
    except Exception as e:
        result["parse_error"] = str(e)[:300]
    resp = requests.patch(f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_dfsr_props_debug.json": {"content": json.dumps({"note":"TEMP smarkets full chain","result":result}, default=str)}}})
    print(resp.status_code)
if __name__ == "__main__": sys.exit(main())
