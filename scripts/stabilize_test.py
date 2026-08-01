import json, os, sys, types, importlib.util

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"

def main():
    import requests
    token = os.environ.get("GITHUB_TOKEN")
    st_stub = types.ModuleType("streamlit")
    class _Secrets(dict):
        def get(self, k, default=None):
            return dict.get(self, k, default)
    st_stub.secrets = _Secrets()
    st_stub.session_state = {}
    st_stub.cache_data = lambda *a, **kw: (lambda f: f)
    st_stub.cache_resource = lambda *a, **kw: (lambda f: f)
    sys.modules["streamlit"] = st_stub

    spec = importlib.util.spec_from_file_location("fetchers", "fetchers.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    results = {}
    tests = [
        ("fetch_ev_api_outliers", lambda: mod.fetch_ev_api_outliers("mlb")),
        ("fetch_ev_api_wnba", lambda: mod.fetch_ev_api_wnba()),
        ("fetch_ev_bvp_full", lambda: mod.fetch_ev_bvp()),
        ("fetch_ev_preview_full", lambda: mod.fetch_ev_preview()),
        ("fetch_ev_recap_full", lambda: mod.fetch_ev_recap()),
        ("fetch_ev_stats_hr_full", lambda: mod.fetch_ev_stats("hr")),
        ("fetch_ev_strikeouts_full", lambda: mod.fetch_ev_strikeouts()),
    ]
    for name, fn in tests:
        try:
            r = fn()
            results[name] = {"type": str(type(r)), "len": len(r) if hasattr(r, "__len__") else None,
                              "full": json.dumps(r, default=str)[:600]}
        except Exception as e:
            import traceback
            results[name] = {"error": str(e)[:300], "trace": traceback.format_exc()[:500]}

    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"betcouncil_bettingpros_debug.json": {"content": json.dumps({"note": "TEMP evsharps round2", "results": results}, default=str)}}},
    )
    print("push:", resp.status_code)
    return 0

if __name__ == "__main__":
    sys.exit(main())
