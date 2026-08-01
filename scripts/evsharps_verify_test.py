import json, os, sys, requests
sys.path.insert(0, '.')

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    token = os.environ.get("GITHUB_TOKEN")
    # minimal stub for streamlit so fetchers.py imports cleanly
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

    results = {}
    for fn_name in ["fetch_ev_mlb", "fetch_ev_movement", "fetch_ev_feed"]:
        try:
            fn = getattr(mod, fn_name)
            if fn_name == "fetch_ev_movement":
                r = fn("mlb")
            else:
                r = fn()
            results[fn_name] = {"type": str(type(r)), "len": len(r) if hasattr(r, "__len__") else None,
                                  "sample": str(r)[:500]}
        except Exception as e:
            import traceback
            results[fn_name] = {"error": str(e)[:300], "trace": traceback.format_exc()[:800]}

    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_bettingpros_debug.json": {"content": json.dumps({"note": "TEMP real fetchers.py evsharps test", "results": results}, default=str)}}},
    )
    print("push:", resp.status_code)
    return 0

if __name__ == "__main__":
    sys.exit(main())
