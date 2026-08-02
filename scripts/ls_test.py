import json, os, sys, traceback, io, contextlib, requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    token = os.environ.get("GITHUB_TOKEN")
    import importlib.util
    spec = importlib.util.spec_from_file_location("ls", "scripts/linestar_harvester.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    result = {}
    captured = io.StringIO()
    try:
        with contextlib.redirect_stdout(captured):
            rc = mod.main()
        result["return_code"] = rc
    except Exception as e:
        result["uncaught_exception"] = str(e)
        result["trace"] = traceback.format_exc()

    result["stdout_tail"] = captured.getvalue()[-3000:]

    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_bettingpros_debug.json": {"content": json.dumps({"note": "TEMP linestar full main test", "result": result}, default=str)}}},
    )
    print("push:", resp.status_code)
    return 0

if __name__ == "__main__":
    sys.exit(main())
