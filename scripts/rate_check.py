import json, os, sys, requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    push_token = os.environ.get("GITHUB_TOKEN")
    result = {}
    for name, tok in [("PICK6_GIST_TOKEN", os.environ.get("TOKEN_A")), ("PICK6_GIST_TOKEN_2", os.environ.get("TOKEN_B"))]:
        if not tok:
            result[name] = "SECRET NOT SET"
            continue
        r = requests.get("https://api.github.com/rate_limit", headers={"Authorization": f"token {tok}"}, timeout=15)
        if r.status_code == 200:
            core = r.json().get("resources", {}).get("core", {})
            result[name] = {"limit": core.get("limit"), "used": core.get("used"), "remaining": core.get("remaining")}
            # also grab identity
            r2 = requests.get("https://api.github.com/user", headers={"Authorization": f"token {tok}"}, timeout=15)
            result[name]["user_id"] = r2.json().get("id") if r2.status_code == 200 else f"HTTP {r2.status_code}"
        else:
            result[name] = f"HTTP {r.status_code}: {r.text[:200]}"

    resp = requests.patch(f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {push_token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_dfsr_props_debug.json": {"content": json.dumps(result, default=str)}}})
    print(resp.status_code)

if __name__ == "__main__":
    sys.exit(main())
