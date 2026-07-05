"""
diagnostics_panel.py — Single status summary for every module added this
build cycle. Reports PASS (real data returned) / EMPTY (ran, no data) /
ERROR (raised or wasn't computed at all) per module, per sport, so you
don't have to click through every expander to find out what's silently
returning nothing.

This does NOT re-run any scraper. It inspects variables the Game Lines
tab already computed in-place, via a dict passed in from app.py, so
checking status costs zero extra network calls.

Public API
----------
render_diagnostics(sport, computed_vars: dict)
    computed_vars: {var_name: value} snapshot of the local variables the
    calling code already has (e.g. {"_tr_signals": _tr_signals, ...}).
    Renders one st.expander with a status line per relevant module for
    that sport.
"""
import streamlit as st

# Which local variable(s) each module writes to, per sport. Missing key in
# computed_vars => ERROR (module didn't run / exception swallowed before
# assignment); present but empty/falsy => EMPTY; present and truthy => PASS.
_MODULE_VARS_BY_SPORT = {
    "NFL": [("Unified Sharp Signals (CLV/steam/RLM/key numbers)", "_usb")],
    "NBA": [
        ("Unified Sharp Signals", "_usb"),
        ("B2B Subtypes", "_b2b_signals"),
        ("Rest Asymmetry", "_rest_signals"),
        ("Pace Mismatches", "_pace_signals"),
    ],
    "MLB": [
        ("Unified Sharp Signals", "_usb"),
        ("Starter vs Bullpen", "_sb_signals"),
        ("Monthly Park Factors", "_pf_rows"),
    ],
    "SOCCER": [("Draw Value", "_draw_signals")],
    "UFC": [("Finish Rates by Weight Class", "_ufc_data")],
    "TENNIS": [("Surface Breakdown", "_tennis_rows")],
    "NHL": [("Unified Sharp Signals", "_usb")],
}

# Modules that apply to every sport regardless of the per-sport list above.
_UNIVERSAL_MODULES = [
    ("Arbitrage Detector", "_arbs"),
    ("Situational Trends (TeamRankings)", "_tr_signals"),
]


def render_diagnostics(sport: str, computed_vars: dict):
    sport_key = sport.upper()
    modules = list(_UNIVERSAL_MODULES) + _MODULE_VARS_BY_SPORT.get(sport_key, [])
    if not modules:
        return

    rows = []
    for label, varname in modules:
        if varname not in computed_vars:
            rows.append((label, "ERROR", "did not run / exception before assignment"))
            continue
        value = computed_vars[varname]
        if not value:
            rows.append((label, "EMPTY", "ran successfully, returned no data"))
        else:
            n = len(value) if hasattr(value, "__len__") else 1
            rows.append((label, "PASS", f"{n} result(s)"))

    n_pass = sum(1 for _, s, _ in rows if s == "PASS")
    n_empty = sum(1 for _, s, _ in rows if s == "EMPTY")
    n_error = sum(1 for _, s, _ in rows if s == "ERROR")

    _status_color = {"PASS": "#22c55e", "EMPTY": "#e8a020", "ERROR": "#e04040"}
    _status_icon = {"PASS": "✅", "EMPTY": "⚪", "ERROR": "🔴"}

    with st.expander(
        f"🔧 Module Status — {n_pass} live / {n_empty} empty / {n_error} error", expanded=True
    ):
        for label, status, detail in rows:
            clr = _status_color[status]
            icon = _status_icon[status]
            st.markdown(
                f'<div style="border-left:4px solid {clr};background:#0a0e14;border-radius:4px;'
                f'padding:0.4rem 0.8rem;margin-bottom:0.3rem;font-size:0.85rem;">'
                f'{icon} <b>{label}</b> — {status} ({detail})</div>',
                unsafe_allow_html=True,
            )
