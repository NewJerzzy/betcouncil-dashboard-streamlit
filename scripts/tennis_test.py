import json, os, sys, requests, traceback

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    token = os.environ.get("GITHUB_TOKEN")
    result = {}
    try:
        import types
        st_stub = types.ModuleType("streamlit")
        class _Secrets(dict):
            def get(self, k, default=None):
                return dict.get(self, k, default)
        st_stub.secrets = _Secrets()
        st_stub.session_state = {}
        st_stub.cache_data = lambda *a, **kw: (lambda f: f)
        st_stub.cache_resource = lambda *a, **kw: (lambda f: f)
        sys.modules["streamlit"] = st_stub

        import importlib.util
        spec = importlib.util.spec_from_file_location("fetchers", "fetchers.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        result["import_ok"] = True

        preds = mod.fetch_betslib_predictions("TENNIS")
        result["num_predictions"] = len(preds)
        result["sample"] = preds[0] if preds else None
    except Exception as e:
        result["error"] = str(e)
        result["trace"] = traceback.format_exc()

    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_oddsapiio_bovada_props_debug.json": {"content": json.dumps({"note": "TEMP tennis real traceback", "result": result}, default=str)}}},
    )
    print("push:", resp.status_code)
    return 0

if __name__ == "__main__":
    sys.exit(main())
