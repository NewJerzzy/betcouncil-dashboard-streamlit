import json, os, sys, requests, traceback

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    token = os.environ.get("GITHUB_TOKEN")
    results = {}

    for name, path in [("prizepicks", "scripts/prizepicks_ssr_scraper.py"), ("underdog", "scripts/underdog_ssr_scraper.py")]:
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(name, path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            results[name] = {"import": "OK"}
        except Exception as e:
            results[name] = {"import_error": str(e), "trace": traceback.format_exc()[:1500]}

    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_bettingpros_debug.json": {"content": json.dumps({"note": "TEMP pp/ud import test", "results": results}, default=str)}}},
    )
    print("push:", resp.status_code)
    return 0

if __name__ == "__main__":
    sys.exit(main())
