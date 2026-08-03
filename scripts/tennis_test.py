import json, os, sys, requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    token = os.environ.get("GITHUB_TOKEN")
    import types
    st_stub = types.ModuleType("streamlit")
    class _Secrets(dict):
        def get(self, k, default=None):
            return dict.get(self, k, default)
    st_stub.secrets = _Secrets()
    sys.modules["streamlit"] = st_stub

    import importlib.util
    spec = importlib.util.spec_from_file_location("fetchers", "fetchers.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    result = {}
    try:
        preds = mod.fetch_betslib_predictions("TENNIS")
        result["num_predictions"] = len(preds)
        result["sample"] = preds[0] if preds else None
    except Exception as e:
        import traceback
        result["error"] = str(e)
        result["trace"] = traceback.format_exc()[:1500]

    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_bettingpros_debug.json": {"content": json.dumps({"note": "TEMP real fetch_betslib_predictions tennis test", "result": result}, default=str)}}},
    )
    print("push:", resp.status_code)
    return 0

if __name__ == "__main__":
    sys.exit(main())
