import sys as _sys_reload_guard
import importlib as _importlib_reload_guard
if "fetchers" in _sys_reload_guard.modules:
    # Real fix (2026-08-18): app_core.py does "from fetchers import *" at
    # its own module level. The app_core reload below only re-executes
    # app_core's code -- it does NOT reload app_core's own dependencies.
    # On a long-running worker, that means app_core's wildcard import can
    # silently re-run against a stale, already-cached fetchers module,
    # missing any function added to fetchers.py after that worker started.
    # Confirmed live: fetch_sharpapi_lines/fetch_sharpapi_props genuinely
    # existed in the current fetchers.py source but were NameErrors at
    # runtime -- this is why. Reloading fetchers first, before app_core,
    # ensures app_core's wildcard import always sees the latest code.
    #
    # Real regression this introduced, fixed here too (2026-08-18): reloading
    # fetchers wipes its module-level _FETCH_HEALTH dict back to {} every
    # single rerun, since module-level state doesn't survive reload() --
    # confirmed live via Fetch Function Health dropping to "8 OK | 233 never
    # called" on a session that had genuinely made far more real calls than
    # that. Saving and restoring that dict's contents across the reload so
    # health tracking still accumulates properly across a session.
    _fh_preserved = getattr(_sys_reload_guard.modules["fetchers"], "_FETCH_HEALTH", None)
    _importlib_reload_guard.reload(_sys_reload_guard.modules["fetchers"])
    if _fh_preserved:
        try:
            _sys_reload_guard.modules["fetchers"]._FETCH_HEALTH.update(_fh_preserved)
        except Exception:
            pass
if "app_core" in _sys_reload_guard.modules:
    # CRITICAL: app_core.py's module-level code (session_state defaults,
    # Gist history/locks loading, etc) must re-run on EVERY Streamlit
    # script rerun, exactly like it did before the 2026-07-26 split when
    # it was inline in this file. Python's import system only executes a
    # module's top-level code ONCE per process and reuses the cached
    # module on every subsequent import -- so without this reload, only
    # the very first user session on a given server worker ever got
    # st.session_state.board_data (and everything else in that init block)
    # actually set; any second session hitting the same already-running
    # worker crashed with AttributeError on session_state.board_data,
    # confirmed as a real production error the day of the split.
    _importlib_reload_guard.reload(_sys_reload_guard.modules["app_core"])
import app_core as _app_core_module
# `from app_core import *` skips every leading-underscore name by Python
# convention (import *'s implicit __all__ excludes them) -- an explicit
# list of 13 such names was tried first, then had to be patched to 18
# after _bankroll_now caused a real production NameError; rather than
# keep discovering missed names one crash at a time, copy EVERYTHING
# from app_core's namespace (only Python's own dunder names excluded),
# which can't miss anything by construction.
for _name_copy_guard in dir(_app_core_module):
    if not _name_copy_guard.startswith("__"):
        globals()[_name_copy_guard] = getattr(_app_core_module, _name_copy_guard)
del _name_copy_guard

# Real, unconditional guard (2026-08-16, second attempt at this fix --
# first attempt used st.session_state.setdefault(), which Streamlit's
# SessionState object does not actually implement, confirmed via a real
# live traceback). Deliberately NOT nested inside the persistence_loaded
# gate above (in app_core.py) -- if that block throws partway through on
# some prior rerun after setting persistence_loaded=True but before
# reaching its own locks assignment, this still guarantees the key
# exists. This is now the single source of truth; no other call site
# needs its own defensive check.
if "locks" not in st.session_state:
    st.session_state["locks"] = []

# app_core.py holds everything that used to be here before the tab-rendering
# section: imports, constants, and ~181 pure helper/calc functions (887KB).
# Split 2026-07-26 to shrink app.py, which had grown past 1.5MB and required
# the Git Data API (not the simpler Contents API) for every edit. The
# tab-rendering code below this line stays here -- it's tightly sequential
# (each tab depends on variables computed by the ones before it in the same
# script run) and wasn't safe to split blind in the same pass.

# ══════════════════════════════════════════════════════════════════
# PERSISTENT SIDEBAR — visible across every tab, unlike anything inside
# st.tabs() itself. Three pieces: a quick sport-context selector (sets
# the same last_sport default Full Board's own selector already reads,
# doesn't duplicate its Load Board action), a steam-move indicator
# (reads whatever's already in session_state -- steam detection only
# actually runs during Full Board's own load flow via a local pkl
# cache, so this surfaces what's there rather than forcing a redundant
# reload from every single page view), and a Most Bet Tonight quick-
# glance using BetQL's community data (independently callable, doesn't
# depend on any other tab having loaded first).
with st.sidebar:
    st.markdown('<div style="font-size:11px;color:var(--bc-dim);text-transform:uppercase;letter-spacing:1px;">Sport Focus</div>', unsafe_allow_html=True)
    _sb_current = st.session_state.get("last_sport", "MLB")
    st.markdown(f'<div style="font-size:15px;font-weight:600;color:var(--bc-text);">{_sb_current}</div>', unsafe_allow_html=True)

    st.markdown("---")
    st.markdown('<div style="font-size:11px;color:var(--bc-dim);text-transform:uppercase;letter-spacing:1px;">🔥 Steam Moves</div>', unsafe_allow_html=True)
    _sb_steam = st.session_state.get("steam_moves", [])
    if _sb_steam:
        for _sm in _sb_steam[:4]:
            st.caption(f"⚡ {_sm.get('matchup','')} — {_sm.get('signal','line moved')}")
    else:
        st.caption("None detected yet this session — load Full Board to check.")

    st.markdown("---")
    st.markdown('<div style="font-size:11px;color:var(--bc-dim);text-transform:uppercase;letter-spacing:1px;">📊 Most Bet Tonight</div>', unsafe_allow_html=True)
    try:
        _sb_betql_sport = _sb_current.upper()
        if _sb_betql_sport not in ("MLB", "NBA", "NFL", "NHL"):
            st.caption(f"Not available for {_sb_current} right now.")
        else:
            _sb_games = fetch_betql_from_gist(_sb_betql_sport)
            _sb_ranked = []
            for _sg in _sb_games:
                _sc = _sg.get("community", [])
                _sml = next((c for c in _sc if c.get("bet_type") == "moneyline"), None)
                if _sml:
                    _stot = _sml.get("home_count", 0) + _sml.get("away_count", 0)
                    if _stot:
                        _sb_ranked.append((_stot, _sg.get("away_team",""), _sg.get("home_team","")))
            _sb_ranked.sort(reverse=True)
            if _sb_ranked:
                for _stot, _saway, _shome in _sb_ranked[:4]:
                    st.caption(f"🎯 {_saway} @ {_shome} — {_stot} picks")
            else:
                st.caption("No community data loaded for this sport right now.")
    except Exception:
        st.caption("Unavailable right now.")

tabs = st.tabs(["📋 Summary", "🎯 Pick For You", "🔮 Predictions", "🏟️ Game Lines", "📊 Full Board", "🛒 Line Shop", "🔭 Market Scanner", "🔍 Slip Analyzer", "🔎 Player Lookup", "📝 Log Bet", "🔒 Locks & Ledger", "🦈 SharpTrack", "📅 Preview", "📈 History", "⚙️ System"])

# ── FLOATING QUICK SLIP (persistent across every tab) ─────────────────────
# Sportsbooks keep the bet slip visible and stable no matter where the user
# navigates. Streamlit has no native floating overlay, so this renders a
# fixed-position widget every rerun, reading the same st.session_state.locks
# store the rest of the app already writes to (game-line locks, board locks,
# Log Bet entries) — nothing new to maintain, just a persistent view of it.
_qs_all_locks   = st.session_state.get("locks", []) or []
_qs_slip_id     = st.session_state.get("current_slip_id")
_qs_slip_locks  = [l for l in _qs_all_locks if l.get("timestamp","") == _qs_slip_id] if _qs_slip_id else []
_qs_show_locks  = _qs_slip_locks if _qs_slip_id else _qs_all_locks[-5:]
_qs_count       = len(_qs_slip_locks) if _qs_slip_id else len(_qs_all_locks)
_qs_label       = "Active Slip" if _qs_slip_id else "Recent Locks"

if _qs_count:
    _qs_rows_html = "".join(
        f'<div style="display:flex;justify-content:space-between;gap:8px;padding:3px 0;'
        f'border-bottom:1px solid #1a2a3a;font-size:11px;">'
        f'<span style="color:#e6edf3;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:120px;">'
        f'{l.get("player","")[:18]} {l.get("side","")} {l.get("prop","") or l.get("line","")}</span>'
        f'<span style="color:#f5c518;font-weight:700;">{l.get("tier","")[:3]}</span>'
        f'</div>'
        for l in list(reversed(_qs_show_locks))[:6]
    )
    st.markdown(
        f'''<div style="position:fixed;bottom:18px;right:18px;z-index:200;width:220px;
             background:linear-gradient(160deg,#0d1520f2,#060c14f2);backdrop-filter:blur(10px);
             border:1px solid rgba(30,144,255,0.40);border-radius:10px;
             box-shadow:0 6px 24px rgba(0,0,0,0.45), 0 0 0 1px rgba(232,160,32,0.08);
             padding:10px 12px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
            <span style="font-size:11px;font-weight:700;letter-spacing:0.6px;color:#f5c518;text-transform:uppercase;">
              🎯 {_qs_label}
            </span>
            <span style="font-size:11px;font-weight:700;color:#e6edf3;background:rgba(232,160,32,0.15);
                  border-radius:10px;padding:1px 8px;">{_qs_count}</span>
          </div>
          {_qs_rows_html}
        </div>''',
        unsafe_allow_html=True
    )

# ── Background EV Auto-Refresh (every 2 min) ─────────────────────────────────
# Silently re-fetches /api/ev, computes line movement deltas, and updates
# sharp alerts — no board reload required. Runs as long as the tab is open.
_EV_REFRESH_INTERVAL = 120   # seconds between EV snapshots

_now_ts = time.time()
_last_ev_refresh = st.session_state.get("ev_auto_refresh_ts", 0)
_board_loaded    = bool(st.session_state.get("board_loaded"))
_auto_refresh_on = st.session_state.get("ev_auto_refresh_enabled", True)

if _board_loaded and _auto_refresh_on and (_now_ts - _last_ev_refresh) >= _EV_REFRESH_INTERVAL:
    # Fetch fresh snapshot
    _bg_ev_raw = fetch_ev_api_live.__wrapped__() if hasattr(fetch_ev_api_live, "__wrapped__") else None
    try:
        import requests as _req
        _bg_r = _req.get("https://api-production-3a3b.up.railway.app/api/ev", timeout=10)
        if _bg_r.status_code == 200:
            _bg_ev_raw = _bg_r.json()
    except Exception:
        _bg_ev_raw = None

    if _bg_ev_raw and _bg_ev_raw.get("data"):
        # Compute movement deltas
        _bg_mv_lookup, _bg_alerts, _bg_snapshot = compute_ev_line_movement(
            _bg_ev_raw,
            st.session_state.get("ev_odds_snapshot", {})
        )
        # Update session state
        st.session_state["ev_odds_snapshot"]   = _bg_snapshot
        st.session_state["ev_auto_refresh_ts"] = _now_ts
        if _bg_mv_lookup:
            st.session_state["ev_movement_lookup"] = _bg_mv_lookup
        if _bg_alerts:
            # Merge new alerts with existing, keep latest 20
            existing = st.session_state.get("sharp_alerts", [])
            merged   = _bg_alerts + [a for a in existing if a not in _bg_alerts]
            st.session_state["sharp_alerts"] = merged[:20]
        # Also update the EV props for Line Shop / StatsHub
        _bg_props, _bg_sigs = extract_ev_props_for_app(
            _bg_ev_raw,
            sport_filter=st.session_state.get("last_sport_loaded")
        )
        if _bg_props:
            st.session_state["ev_api_props"]     = _bg_props
            st.session_state["ev_signal_lookup"] = _bg_sigs
            st.session_state["ev_api_updated"]   = _bg_ev_raw.get("updated", {})
        # Trigger silent rerun to push updated data to UI
        st.rerun()


with tabs[0]:
    # ═══════════════════════════════════════════════════════
    # SUMMARY TAB — DARK UI OVERHAUL
    # ═══════════════════════════════════════════════════════
    with st.expander("🧭 Quick Navigation — what's where", expanded=False):
        st.markdown(
            "**📊 Analysis** — Full Board, Game Lines, Predictions, Line Shop, Market Scanner\n\n"
            "**🎯 Betting Tools** — Pick For You, Slip Analyzer, Player Lookup, Log Bet\n\n"
            "**📈 Tracking** — Locks & Ledger, History, SharpTrack, Preview\n\n"
            "**⚙️ Admin** — System"
        )
    # ── Stale/dead feed banner — previously the only signal for a dead
    # sharp reference feed was buried in System tab's Harvester Health
    # Monitor. Surfaces here too so it's seen immediately, not just by
    # someone who thinks to check System. Reuses get_harvester_alerts'
    # existing change-detection (only newly-dead + sharp-tier sources,
    # not every source that's been dead for weeks).
    try:
        _hb_alerts = []
        _hb_sports = ["MLB", "NBA", "NFL", "WNBA"]
        if datetime.now().month not in (7, 8, 9):  # NHL's real season runs Oct-June
            _hb_sports.append("NHL")
        for _hb_sport in _hb_sports:
            _hb_alerts.extend(get_harvester_alerts(_hb_sport, persist=True))
        if _hb_alerts:
            _hb_names = ", ".join(sorted(set(a["name"] for a in _hb_alerts))[:6])
            st.markdown(
                f'<div style="background:#e0404022;border-left:3px solid #e04040;'
                f'border-radius:4px;padding:10px 14px;margin-bottom:12px;">'
                f'<div style="font-size:0.9rem;font-weight:700;color:#e04040;">'
                f'🔴 {len(_hb_alerts)} feed{"s" if len(_hb_alerts) != 1 else ""} just went dead: {_hb_names}</div>'
                f'<div style="font-size:0.78rem;color:var(--bc-dim);margin-top:2px;">'
                f'Check System → Harvester Health Monitor for details.</div>'
                f'</div>',
                unsafe_allow_html=True
            )
    except Exception:
        pass

    try:
        _glt_history = load_from_gist("game_board_grading_history", None) or {}
        _glt_window = st.radio("Game Lines Track Record", ["Last 7d", "Last 30d", "All Time"], horizontal=True, key="_glt_window", label_visibility="collapsed")
        _glt_cutoff = {
            "Last 7d": (date.today() - timedelta(days=7)).strftime("%Y-%m-%d"),
            "Last 30d": (date.today() - timedelta(days=30)).strftime("%Y-%m-%d"),
            "All Time": "0000-00-00",
        }[_glt_window]
        _glt_recs = [r for d, recs in _glt_history.items() if d >= _glt_cutoff for r in recs if r.get("outcome") in ("WIN", "LOSS", "PUSH")]
        if len(_glt_recs) >= 10:
            _glt_by_market = {}
            for r in _glt_recs:
                m = r.get("market", "?")
                _glt_by_market.setdefault(m, {"W": 0, "L": 0, "P": 0})
                _glt_by_market[m][{"WIN": "W", "LOSS": "L", "PUSH": "P"}[r["outcome"]]] += 1
            _glt_cols = st.columns(len(_glt_by_market) + 1)
            _glt_tot_w = sum(v["W"] for v in _glt_by_market.values())
            _glt_tot_l = sum(v["L"] for v in _glt_by_market.values())
            with _glt_cols[0]:
                _glt_wr = _glt_tot_w / (_glt_tot_w + _glt_tot_l) * 100 if (_glt_tot_w + _glt_tot_l) else 0
                st.metric("Overall", f"{_glt_wr:.1f}%", f"{_glt_tot_w}-{_glt_tot_l}")
            for _i, (m, v) in enumerate(sorted(_glt_by_market.items())):
                with _glt_cols[_i + 1]:
                    _wl = v["W"] + v["L"]
                    _wr = v["W"] / _wl * 100 if _wl else 0
                    st.metric(m, f"{_wr:.1f}%", f"{v['W']}-{v['L']}" + (f"-{v['P']}P" if v["P"] else ""))
            st.caption(f"Game Lines · {len(_glt_recs)} graded picks · {_glt_window.lower()}")

            _glt_losses = [r for r in _glt_recs if r.get("outcome") == "LOSS"]
            if len(_glt_losses) >= 5:
                with st.expander(f"📉 Loss Breakdown ({len(_glt_losses)} losses, {_glt_window.lower()})", expanded=False):
                    _lb_low_edge = sum(1 for r in _glt_losses if (r.get("edge") or 0) < 0.02)
                    _lb_low_tier = sum(1 for r in _glt_losses if r.get("tier") in ("LEAN", "PASS", ""))
                    _lb_other = len(_glt_losses) - _lb_low_edge
                    st.caption(
                        f"Low-edge picks (<2%): {_lb_low_edge} ({_lb_low_edge/len(_glt_losses)*100:.0f}%) · "
                        f"Low-tier picks: {_lb_low_tier} ({_lb_low_tier/len(_glt_losses)*100:.0f}%) · "
                        f"Other: {_lb_other}"
                    )
                    if _lb_low_edge / len(_glt_losses) > 0.4:
                        st.warning(f"⚠️ {_lb_low_edge} of {len(_glt_losses)} losses had <2% edge. Consider raising the minimum edge threshold.")
                    st.caption(
                        "Sharp-money-opposite, line-movement, weather, and injury tags aren't available for "
                        "already-graded picks — that data wasn't captured at snapshot time, only reconstructable "
                        "going forward if the snapshot itself is extended to record it."
                    )
    except Exception:
        pass

    _bb_briefing = st.session_state.get("bobbys_bets_briefing", {})
    if _bb_briefing.get("headline"):
        st.markdown(
            f'<div style="background:var(--bc-bg-card);border-left:3px solid var(--bc-blue);'
            f'border-radius:4px;padding:10px 14px;margin-bottom:12px;">'
            f'<div style="font-size:0.95rem;font-weight:700;color:var(--bc-text);">📰 {_bb_briefing["headline"]}</div>'
            + (f'<div style="font-size:0.82rem;color:var(--bc-dim);margin-top:2px;">{_bb_briefing.get("subhead","")}</div>' if _bb_briefing.get("subhead") else '')
            + '</div>',
            unsafe_allow_html=True
        )
    # ══════════════════════════════════════════════════════
    # WEEKLY TRACK RECORD BANNER — real W/L from actual resolved
    # bets, not a static claim. Only shows if there's a real
    # sample this week; says nothing rather than fabricate one.
    # ══════════════════════════════════════════════════════
    try:
        from datetime import timedelta as _td_wk
        _wk_cutoff = datetime.now() - _td_wk(days=7)
        _wk_resolved = [
            h for h in st.session_state.get("history", [])
            if h.get("outcome") in ("WIN", "LOSS")
            and str(h.get("tier", "")).upper() in ("SOVEREIGN", "ELITE")
        ]
        def _wk_parse(ts):
            try:
                return datetime.fromisoformat(str(ts)[:19])
            except Exception:
                return datetime.min
        _wk_resolved = [h for h in _wk_resolved if _wk_parse(h.get("timestamp","")) >= _wk_cutoff]
        _wk_wins = sum(1 for h in _wk_resolved if h.get("outcome") == "WIN")
        _wk_total = len(_wk_resolved)
        if _wk_total >= 5:
            _wk_pct = _wk_wins / _wk_total
            st.markdown(
                f'<div style="background:linear-gradient(90deg,#0a5fa8,#0a1628);border-left:4px solid #1e90ff;'
                f'border-radius:6px;padding:10px 16px;margin-bottom:12px;">'
                f'<span style="color:#fff;font-weight:700;font-size:14px;">🎯 SOVEREIGN/ELITE picks are '
                f'{_wk_wins}-{_wk_total - _wk_wins} ({_wk_pct:.0%}) this week</span>'
                f'</div>',
                unsafe_allow_html=True
            )
    except Exception:
        pass

    _board_all   = st.session_state.get("board_data", []) or []
    _sov_all     = sum(1 for p in _board_all if p.get("Tier","") == "SOVEREIGN")
    _elite_all   = sum(1 for p in _board_all if p.get("Tier","") == "ELITE")
    _total_props = len(_board_all)
    _avg_edge    = round(
        sum(float(p.get("Edge",0) or 0) for p in _board_all) / max(_total_props,1) * 100, 1
    ) if _board_all else 0.0
    _bi_top      = compute_bankroll_multiplier()
    _history_top = st.session_state.get("history", [])
    _resolved_top= [h for h in _history_top if h.get("outcome") in ("WIN","LOSS")]
    _recent_20   = _resolved_top[-20:] if len(_resolved_top) >= 20 else _resolved_top
    _win_rate_top= round(
        sum(1 for h in _recent_20 if h.get("outcome")=="WIN") / max(len(_recent_20),1) * 100, 1
    ) if _recent_20 else 0.0
    # CLV Avg card -- was reading CLV_PATH ("clv_tracking.json"), fed only
    # by _capture_clv_closing_lines(), which only ever processes bets with
    # outcome=="PENDING". No log_manual_bet() call site ever logs a bet as
    # PENDING (they all log an already-known WIN/LOSS/PUSH), so that path
    # never fires and this card was permanently stuck at 0.00 regardless
    # of real performance. Switched to get_clv_summary(), which reads the
    # clv_capture pipeline fixed 2026-07-13 (real placement snapshots +
    # resolve_clv_records). Props only here (percent); game-line CLV is
    # points, a different unit, and shown as a second card rather than
    # forced into the same number.
    _history_for_clv = st.session_state.get("history", [])
    _clv_sum_top = get_clv_summary(_history_for_clv)
    _clv_avg_top = _clv_sum_top.get("avg_clv") or 0.0
    _clv_avg_top_pct = _clv_avg_top * 100
    _clv_n_top = _clv_sum_top.get("n_resolved", 0)
    _game_clv_pts = [
        h.get("clv_capture", {}).get("clv_points") for h in _history_for_clv
        if h.get("clv_capture", {}).get("clv_resolved")
        and h.get("clv_capture", {}).get("bet_type") == "game"
        and h.get("clv_capture", {}).get("clv_points") is not None
    ]
    _clv_avg_game_top = round(sum(_game_clv_pts) / len(_game_clv_pts), 2) if _game_clv_pts else 0.0
    _clv_n_game_top = len(_game_clv_pts)

    # ── Real-data prep for the new hero/performance layout below ────────
    # Kelly fraction: average KellyAdvisedPct across today's loaded board
    # (real per-prop field already computed in load_sport_data); "—" if no
    # board loaded yet rather than a fabricated number.
    _kelly_vals = [float(p.get("KellyAdvisedPct", 0) or 0) for p in _board_all if p.get("KellyAdvisedPct")]
    _kelly_frac_avg = (sum(_kelly_vals) / len(_kelly_vals)) if _kelly_vals else None

    # Sovereign Score: % of today's board that's Sovereign or Elite tier --
    # a real "how strong is today's slate" read, not an invented metric.
    _sovereign_score = round((_sov_all + _elite_all) / _total_props * 100) if _total_props else None

    # Variance: std dev of the last 10 resolved bets' P&L as a fraction of
    # unit size -- real, derived from actual settled outcomes, not a canned
    # "Normal/High" label with nothing behind it.
    _recent_pnl = []
    for h in _resolved_top[-10:]:
        _w = float(h.get("wager", 0) or 0)
        if h.get("outcome") == "WIN":
            _recent_pnl.append(_w * float(h.get("payout_mult", 1.0) or 1.0) - _w if h.get("payout_mult") else _w)
        elif h.get("outcome") == "LOSS":
            _recent_pnl.append(-_w)
    if len(_recent_pnl) >= 3:
        _pnl_std = statistics.stdev(_recent_pnl)
        _pnl_mean_abs = sum(abs(x) for x in _recent_pnl) / len(_recent_pnl) or 1
        _variance_ratio = _pnl_std / _pnl_mean_abs
        _variance_label = "High" if _variance_ratio > 1.4 else "Low" if _variance_ratio < 0.6 else "Normal"
        _variance_color = "#e04040" if _variance_label == "High" else "#22c55e" if _variance_label == "Low" else "#e8a020"
    else:
        _variance_label, _variance_color = "—", "#6a7a8a"

    # CLV grade: reuses the existing, real compute_clv_grade() -- not a new
    # invented A/B/C/D scale next to the one that already exists.
    _clv_grade_label, _clv_grade_color = compute_clv_grade(_clv_avg_top_pct if _clv_n_top else None)

    # 7-day bankroll trajectory: reconstructed from real resolved-bet P&L
    # history (no persisted daily bankroll snapshot exists yet to read
    # directly, so this is a genuine derived reconstruction, not invented
    # numbers) -- cumulative P&L over the last 7 days of resolved bets,
    # walked backward from the current bankroll.
    from datetime import timedelta as _td_spark
    _spark_cutoff = datetime.now() - _td_spark(days=7)
    _spark_bets = [h for h in _resolved_top if h.get("timestamp","") >= _spark_cutoff.strftime("%Y-%m-%d")]
    _spark_points = [_bi_top.get("bankroll", st.session_state.get("bankroll", DEFAULT_BANKROLL))]
    _running = _spark_points[0]
    for h in reversed(_spark_bets):
        _w = float(h.get("wager", 0) or 0)
        _delta = (_w * float(h.get("payout_mult", 1.0) or 1.0) - _w) if h.get("outcome") == "WIN" else (-_w if h.get("outcome") == "LOSS" else 0)
        _running -= _delta
        _spark_points.append(_running)
    _spark_points = list(reversed(_spark_points))
    if len(_spark_points) >= 2:
        _sp_min, _sp_max = min(_spark_points), max(_spark_points)
        _sp_range = (_sp_max - _sp_min) or 1
        _sp_w, _sp_h = 110, 28
        _sp_pts = " ".join(
            f"{i/(len(_spark_points)-1)*_sp_w:.1f},{_sp_h - (v-_sp_min)/_sp_range*_sp_h:.1f}"
            for i, v in enumerate(_spark_points)
        )
        _sp_color = "#22c55e" if _spark_points[-1] >= _spark_points[0] else "#e04040"
        _spark_svg = f'<svg width="{_sp_w}" height="{_sp_h}" style="display:block;margin-top:4px;"><polyline points="{_sp_pts}" fill="none" stroke="{_sp_color}" stroke-width="1.5"/></svg>'
    else:
        _spark_svg = ""

    _hr_pct = _win_rate_top  # already computed above, real rolling-20 hit rate
    _hr_deg = min(360, max(0, _hr_pct / 100 * 360))
    _hr_color = "#22c55e" if _hr_pct >= 55 else "#4db8ff" if _hr_pct >= 52.4 else "#e8a020" if _hr_pct >= 48 else "#e04040"

    # CLV trend sparkline: real per-bet CLV values from resolved history's
    # clv_capture (percent, props only -- same unit already used for
    # _clv_avg_top_pct above), last 10 resolved bets with a resolved CLV
    # value. Not invented -- if fewer than 2 real points exist, no sparkline
    # renders rather than fabricating a flat/fake line.
    _clv_trend_vals = [
        h["clv_capture"]["clv_vs_novig"] * 100 for h in _resolved_top[-15:]
        if h.get("clv_capture", {}).get("clv_resolved") and h.get("clv_capture", {}).get("bet_type") != "game"
        and h.get("clv_capture", {}).get("clv_vs_novig") is not None
    ][-10:]
    if len(_clv_trend_vals) >= 2:
        _ct_min, _ct_max = min(_clv_trend_vals), max(_clv_trend_vals)
        _ct_range = (_ct_max - _ct_min) or 1
        _ct_w, _ct_h = 90, 22
        _ct_pts = " ".join(
            f"{i/(len(_clv_trend_vals)-1)*_ct_w:.1f},{_ct_h - (v-_ct_min)/_ct_range*_ct_h:.1f}"
            for i, v in enumerate(_clv_trend_vals)
        )
        _ct_color = "#22c55e" if _clv_trend_vals[-1] > _clv_trend_vals[0] else "#e04040" if _clv_trend_vals[-1] < _clv_trend_vals[0] else "var(--bc-dim)"
        _clv_spark_svg = (
            f'<svg width="{_ct_w}" height="{_ct_h}" style="display:block;margin-top:4px;" '
            f'title="Last {len(_clv_trend_vals)} resolved bets\' CLV%">'
            f'<polyline points="{_ct_pts}" fill="none" stroke="{_ct_color}" stroke-width="1.5"/></svg>'
            f'<span style="display:block;margin-top:5px;font-size:0.68rem;color:{_ct_color};font-weight:600;">{_clv_trend_vals[-1]:+.1f}%</span>'
        )
    else:
        _clv_spark_svg = ""

    # Bankroll pulse-on-change: only animates on the render where the value
    # genuinely differs from the last one seen this session, not on every
    # rerun -- avoids a constantly-pulsing number that would be more
    # distracting than informative.
    _bankroll_now_hero = _bi_top.get("bankroll", st.session_state.get("bankroll", DEFAULT_BANKROLL))
    _prev_bankroll_hero = st.session_state.get("_prev_bankroll_hero")
    if _prev_bankroll_hero is None or _prev_bankroll_hero == _bankroll_now_hero:
        _bankroll_pulse_cls = ""
    elif _bankroll_now_hero > _prev_bankroll_hero:
        _bankroll_pulse_cls = " bankroll-pulse-up"
    else:
        _bankroll_pulse_cls = " bankroll-pulse-down"
    st.session_state["_prev_bankroll_hero"] = _bankroll_now_hero
    # 7-day change label under the sparkline, real value from the same
    # reconstruction used to draw it -- not decorative, actionable.
    _spark_chg_label = ""
    if len(_spark_points) >= 2 and _spark_points[0]:
        _spark_chg_pct = (_spark_points[-1] - _spark_points[0]) / abs(_spark_points[0]) * 100
        _spark_chg_color = "#22c55e" if _spark_chg_pct > 0 else "#e04040" if _spark_chg_pct < 0 else "var(--bc-dim)"
        _spark_chg_label = f'<span style="display:block;margin-top:5px;font-size:0.68rem;color:{_spark_chg_color};font-weight:600;">{_spark_chg_pct:+.1f}% (7d)</span>'

    st.html(f"""
    <div style="display:flex;gap:16px;margin-bottom:16px;flex-wrap:wrap;">
        <div class="command-card" style="flex:1;min-width:180px;text-align:left;padding:14px 16px;">
            <div class="command-label">Current Bankroll</div>
            <div class="command-value{_bankroll_pulse_cls}" style="color:#22c55e;font-size:1.9rem;" title="7-day trajectory reconstructed from resolved bet history">${_bankroll_now_hero:.2f}</div>
            {_spark_svg}
            {_spark_chg_label}
        </div>
        <div class="command-card" style="flex:1;min-width:180px;text-align:left;padding:14px 16px;" title="Average Kelly-advised stake across today's loaded board">
            <div class="command-label">Kelly Fraction</div>

            <div class="command-value" style="font-size:1.9rem;">{f"{_kelly_frac_avg:.1%}" if _kelly_frac_avg is not None else "—"}</div>
            <div style="font-size:0.75rem;color:var(--bc-dim);margin-top:2px;">Recommended stake %</div>
        </div>
        <div class="command-card" style="flex:1;min-width:180px;text-align:left;padding:14px 16px;">
            <div class="command-label">Unit Size</div>
            <div class="command-value" style="font-size:1.9rem;">${active_unit():.2f}</div>
            <div style="font-size:0.75rem;color:var(--bc-dim);margin-top:2px;">Auto from bankroll + Kelly</div>
        </div>
    </div>
    """)
    st.html(f"""
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:16px;">
        <div class="command-card" style="display:flex;flex-direction:column;align-items:center;padding:14px 16px;" title="Rolling 20-bet hit rate">
            <div style="width:64px;height:64px;border-radius:50%;background:conic-gradient({_hr_color} {_hr_deg}deg, rgba(255,255,255,0.08) 0deg);display:flex;align-items:center;justify-content:center;">
                <div style="width:48px;height:48px;border-radius:50%;background:var(--bc-bg-card);display:flex;align-items:center;justify-content:center;font-weight:800;font-size:0.9rem;color:#ffffff;">{_hr_pct:.0f}%</div>
            </div>
            <div class="command-label" style="margin-top:8px;">Hit Rate (L20)</div>
        </div>
        <div class="command-card" style="padding:14px 16px;" title="Weighted closing-line value vs Pinnacle">
            <div class="command-value" style="color:{_clv_grade_color};font-size:1.3rem;">{_clv_grade_label}</div>
            <div class="command-label">CLV Grade</div>
            {_clv_spark_svg}
        </div>
        <div class="command-card" style="padding:14px 16px;" title="Volatility of the last 10 settled bets' results">
            <div class="command-value" style="color:{_variance_color};font-size:1.3rem;">{_variance_label}</div>
            <div class="command-label">Variance</div>
        </div>
        <div class="command-card" style="padding:14px 16px;" title="Share of today's board rated Sovereign or Elite tier">
            <div class="command-value" style="font-size:1.3rem;">{f"{_sovereign_score}%" if _sovereign_score is not None else "—"}</div>
            <div class="command-label">Sovereign Score</div>
        </div>
    </div>
    """)
    if _clv_n_game_top:
        st.caption(f"Game-line CLV avg: {_clv_avg_game_top:+.2f}pts (n={_clv_n_game_top}, points not percent -- different unit from prop CLV above)")

    # Market Climate -- "is the market moving today," visible on page load
    # without triggering a board fetch. Uses game_board_snapshots (the
    # headless twice-daily generator, scripts/game_board_snapshot_headless.py)
    # directly from Gist rather than the in-session steam/RLM detection
    # inside analyze_game_edge(), which only exists after a full per-sport
    # board load.
    try:
        _climate_snaps = load_from_gist("game_board_snapshots", None) or {}
        _climate = compute_market_climate(_climate_snaps)
        if _climate["verdict"] == "No data yet today":
            st.caption("📡 Market Climate: No line-movement check has run yet today. This updates twice a day (around 11am and 4pm ET) — check back after the next one.")
        elif _climate["verdict"] == "Quiet":
            st.caption(f"📡 Market Climate: Calm. {_climate['n_snapshots_today']} check(s) so far today across {', '.join(_climate['sports_covered'])} — no game's line has moved enough to flag.")
        else:
            _m = _climate["movers"][0]
            _extra = f" (+{len(_climate['movers'])-1} more)" if len(_climate["movers"]) > 1 else ""
            st.warning(f"📡 Market Climate: Moving. **{_m['matchup']}** ({_m['market']}) — our edge on this shifted from {_m['edge_am']:+.0%} to {_m['edge_pm']:+.0%} "
                       f"since this morning (tier {_m['tier_am']}→{_m['tier_pm']}){_extra}. Either real news is moving this game, or our number is behind — worth a second look before betting it.")
    except Exception:
        pass

    # Game Density -- "am I about to get slammed with tip-offs at once."
    # Schedule-only fetch, no board load. Real gap: nothing in this
    # codebase tracked start-time clustering before this.
    try:
        _density_sports = [s for s in ("NBA","MLB","NHL","WNBA","NFL")
                            if detect_season_regime(s).get("regime") != "Off-season"]
        _density_times = fetch_todays_game_start_times(_density_sports)
        _density = compute_game_density(_density_times)
        if _density["n_games"] and _density["verdict"] == "Clustered":
            _pw = _density["peak_window_start"]
            _pw_local = _pw.strftime("%I:%M%p UTC").lstrip("0") if _pw else "?"
            st.warning(f"🕐 Game Density: Bunched up. {_density['peak_count']} of today's {_density['n_games']} games "
                       f"all tip off within 90 minutes of {_pw_local} — you'll be making several decisions at once in that window. Consider doing your analysis before then.")
        elif _density["n_games"]:
            st.caption(f"🕐 Game Density: Spread out. {_density['n_games']} games today, and no more than {_density['peak_count']} of them start close together — plenty of time to analyze each one.")
    except Exception:
        pass

    # Pipeline Integrity -- the real version of this already exists
    # (Harvester Health Monitor, System tab, checks actual Gist
    # captured_at ages against expected refresh intervals) -- just wasn't
    # visible before the board loads. Pointer + red/yellow/green count
    # here, not a rebuild.
    try:
        from fetchers import get_harvester_alerts, harvester_display_name
        _pi_sport = st.session_state.get("last_sport", "NBA")
        _pi_alerts = get_harvester_alerts(_pi_sport)
        _pi_sharp_dead = [harvester_display_name(a["name"]) for a in _pi_alerts if a["tier"] == "sharp"]
        if _pi_sharp_dead:
            st.error(f"🔌 Data Check: **{', '.join(_pi_sharp_dead)}** — one of our benchmark sharp-book price feeds — hasn't updated recently. "
                     f"Edges that lean on it may be based on stale prices right now. See System tab → Harvester Health for details.")
        elif _pi_alerts:
            st.caption(f"🔌 Data Check: {len(_pi_alerts)} data source(s) are updating slower than usual. Probably fine, but see System tab → Harvester Health if something looks off.")
        else:
            st.caption("🔌 Data Check: all data sources are current.")
    except Exception:
        pass

    # ── Market Climate bar (Sharp Movement / RLM / Book Discrepancy) ────
    # Reuses the real _climate computed above (recomputed here since it
    # was scoped inside that try block) plus two more real, already-
    # tracked signals: RLM mentions in today's board signal notes, and
    # the real multibook_discrepancies list already populated elsewhere.
    try:
        _mc_climate_snaps = load_from_gist("game_board_snapshots", None) or {}
        _mc_climate = compute_market_climate(_mc_climate_snaps)
        _mc_sharp_pct = min(100, len(_mc_climate.get("movers", [])) * 25) if _mc_climate["verdict"] == "Moving" else (10 if _mc_climate["verdict"] == "Quiet" else 0)
        _mc_rlm_count = sum(1 for p in _board_all if "RLM" in str(p.get("SignalNotes", "")))
        _mc_rlm_pct = min(100, _mc_rlm_count * 20)
        _mc_disc = st.session_state.get("multibook_discrepancies", [])
        _mc_disc_pct = min(100, len(_mc_disc) * 15)
        st.html(f"""
        <div class="command-card" style="padding:14px 16px;margin-bottom:16px;">
            <div class="command-label" style="margin-bottom:10px;">Market Climate</div>
            <div style="display:flex;flex-direction:column;gap:8px;">
                <div style="display:flex;align-items:center;gap:10px;">
                    <span style="font-size:0.75rem;color:var(--bc-muted);width:130px;border-bottom:1px dotted var(--bc-dim);cursor:help;" title="Whether betting lines are actively moving right now. Lines move when real money comes in on one side of a bet.">Sharp Movement</span>
                    <div style="flex:1;height:5px;background:rgba(255,255,255,0.08);border-radius:3px;"><div style="width:{_mc_sharp_pct}%;height:100%;background:#4db8ff;border-radius:3px;"></div></div>
                    <span style="font-size:0.75rem;color:var(--bc-dim);width:60px;text-align:right;">{_mc_climate["verdict"]}</span>
                </div>
                <div style="display:flex;align-items:center;gap:10px;">
                    <span style="font-size:0.75rem;color:var(--bc-muted);width:130px;border-bottom:1px dotted var(--bc-dim);cursor:help;" title="A line moving the OPPOSITE way from where most public bets are placed — often a sign that large/sharp bettors are betting the other side, even though most people are betting the other way.">Reverse Line Move</span>
                    <div style="flex:1;height:5px;background:rgba(255,255,255,0.08);border-radius:3px;"><div style="width:{_mc_rlm_pct}%;height:100%;background:#e8a020;border-radius:3px;"></div></div>
                    <span style="font-size:0.75rem;color:var(--bc-dim);width:60px;text-align:right;">{_mc_rlm_count} flagged</span>
                </div>
                <div style="display:flex;align-items:center;gap:10px;">
                    <span style="font-size:0.75rem;color:var(--bc-muted);width:130px;border-bottom:1px dotted var(--bc-dim);cursor:help;" title="Cases where different sportsbooks are offering noticeably different odds or lines on the same bet right now — sometimes a sign one book hasn't updated yet, which can mean a better price is available elsewhere.">Book Discrepancy</span>
                    <div style="flex:1;height:5px;background:rgba(255,255,255,0.08);border-radius:3px;"><div style="width:{_mc_disc_pct}%;height:100%;background:#f5c518;border-radius:3px;"></div></div>
                    <span style="font-size:0.75rem;color:var(--bc-dim);width:60px;text-align:right;">{len(_mc_disc)} found</span>
                </div>
            </div>
        </div>
        """)
    except Exception:
        _logger.debug("Market Climate bar failed silently")

    # ── Daily Insight Summary -- one plain sentence combining real data
    # already computed above (board strength, tier counts, CLV trend),
    # not a "quest" or gamified summary, just a quick digest.
    _dis_n_sov = _sov_all
    _dis_n_elite = _elite_all
    if _dis_n_sov or _dis_n_elite:
        _dis_strength = "Strong"
    elif _total_props:
        _dis_strength = "Moderate" if any(p.get("Tier") == "APPROVED" for p in _board_all) else "Weak"
    else:
        _dis_strength = "No board loaded"
    _dis_clv_part = ""
    if len(_clv_trend_vals) >= 2:
        _dis_clv_chg = _clv_trend_vals[-1] - _clv_trend_vals[0]
        _dis_clv_part = f" CLV trend: {_dis_clv_chg:+.1f}%."
    st.caption(
        f"📋 Today's board strength: {_dis_strength}. "
        f"{_dis_n_sov} Sovereign, {_dis_n_elite} Elite pick(s).{_dis_clv_part}"
    )

    # ── Session Prep (collapsed by default -- progressive disclosure) ──
    with st.expander("🏦 Bankroll Health"):
        _day_start_prep = float(st.session_state.get("day_start_br", 0) or 0)
        _bankroll_prep = float(st.session_state.get("bankroll", DEFAULT_BANKROLL) or 0)
        if _day_start_prep:
            _day_chg_pct = (_bankroll_prep - _day_start_prep) / _day_start_prep * 100
            _dc_color = "#22c55e" if _day_chg_pct >= 0 else "#e04040"
            st.markdown(f'Today: <span style="color:{_dc_color};font-weight:700;">{_day_chg_pct:+.1f}%</span> (${_bankroll_prep - _day_start_prep:+.2f}) vs. day-start bankroll of ${_day_start_prep:.2f}', unsafe_allow_html=True)
        else:
            st.caption("No day-start bankroll recorded yet.")

    with st.expander("⚠️ Exposure Risk"):
        _team_totals = {}
        for lock in st.session_state.get("locks", []):
            _t = lock.get("team", "")
            if _t:
                _team_totals[_t] = _team_totals.get(_t, 0) + float(lock.get("wager", 0) or 0)
        if _team_totals:
            _worst_team, _worst_amt = max(_team_totals.items(), key=lambda kv: kv[1])
            _bankroll_now_prep = float(st.session_state.get("bankroll", DEFAULT_BANKROLL) or 1)
            _worst_pct = _worst_amt / _bankroll_now_prep * 100 if _bankroll_now_prep else 0
            _exp_color = "#e04040" if _worst_pct > 20 else "#e8a020" if _worst_pct > 10 else "#22c55e"
            st.markdown(f'Highest single-team exposure today: <span style="color:{_exp_color};font-weight:700;">{_worst_team}</span> — ${_worst_amt:.2f} ({_worst_pct:.1f}% of bankroll)', unsafe_allow_html=True)
        else:
            st.caption("No active locks with team data yet today.")

    with st.expander("📡 Model Freshness Check"):
        try:
            if _pi_sharp_dead:
                st.error(f"{', '.join(_pi_sharp_dead)} — sharp reference feed(s) stale. Edges leaning on them may be behind.")
            elif _pi_alerts:
                st.warning(f"{len(_pi_alerts)} data source(s) updating slower than usual.")
            else:
                st.success("All data sources current.")
        except NameError:
            st.caption("Data freshness check unavailable right now.")

    st.markdown("---")

    # ── Cross-Source Check: quick rollup of how many of today's top
    # plays agree or disagree with the free public comparison sources.
    # Display only — counts side/direction disagreements, doesn't touch
    # SEM/tiers/weights. Only checks SOVEREIGN/ELITE plays (keeps it fast
    # and keeps the count meaningful — LEAN/PASS disagreements aren't
    # interesting). Props: FavoredProps. Games: Dimers.
    # Each source only counted where it actually has comparable
    # directional data for that pick — silence, not a guess, when absent.
    try:
        _xs_top_props = [p for p in _board_all if p.get("Tier") in ("SOVEREIGN", "ELITE")]

        _xs_checked = 0
        _xs_agree = 0
        _xs_disagree = 0
        _xs_disagree_list = []

        for _xp in _xs_top_props[:60]:  # cap for render speed
            _xp_sport = _xp.get("Sport", "")
            if _xp_sport not in ("MLB", "WNBA"):
                continue
            _xp_player = _xp.get("Player", "")
            _xp_side = str(_xp.get("Side", "OVER")).upper()
            _xp_prop_l = str(_xp.get("Prop", "")).lower()

            try:
                _fp_rows = fetch_favoredprops_from_gist("sportsbook", _xp_sport) or []
                _fp_rows += fetch_favoredprops_from_gist("dfs", _xp_sport) or []
            except Exception:
                _fp_rows = []
            for _fpr in _fp_rows:
                if str(_fpr.get("player", "")).lower() == _xp_player.lower() and str(_fpr.get("stat_type", "")).lower() in _xp_prop_l:
                    _fp_bet = str(_fpr.get("bet", "")).upper()
                    _fp_side = "OVER" if _fp_bet.startswith("O") else ("UNDER" if _fp_bet.startswith("U") else "")
                    if _fp_side:
                        _xs_checked += 1
                        if _fp_side == _xp_side:
                            _xs_agree += 1
                        else:
                            _xs_disagree += 1
                            _xs_disagree_list.append(f"{_xp_player} {_xp.get('Prop','')}: you have {_xp_side}, FavoredProps has {_fp_side}")
                    break

        if _xs_checked > 0:
            _xs_c1, _xs_c2, _xs_c3 = st.columns(3)
            _xs_c1.metric("Cross-Checked", _xs_checked)
            _xs_c2.metric("Agree", _xs_agree)
            _xs_c3.metric("Disagree", _xs_disagree)
            if _xs_disagree_list:
                with st.expander(f"⚠️ {_xs_disagree} disagreement(s) with public sources — see details"):
                    for _line in _xs_disagree_list[:20]:
                        st.caption(_line)
            st.caption("Cross-Source Check: SOVEREIGN/ELITE plays only, vs FavoredProps (props). Display only — doesn't change your model.")
    except Exception:
        pass

    st.markdown("---")

    col_left, col_right = st.columns([4, 1.2])

    with col_left:

        # ═══════════════════════════════════════════════════
        # SECTION 1 — TODAY'S CARD (first thing user sees)
        # ═══════════════════════════════════════════════════
        # ── 1. RECOMMENDED ACTION ──────────────────────────
        board = st.session_state.get("board_data", []) or []
        game_analysis = st.session_state.get("game_analysis", [])
        sov_count     = sum(1 for p in board if p.get("Tier","") == "SOVEREIGN")
        elite_count   = sum(1 for p in board if p.get("Tier","") == "ELITE")
        approved_count= sum(1 for p in board if p.get("Tier","") == "APPROVED")
        lean_count    = sum(1 for p in board if p.get("Tier","") == "LEAN")
        elite_plus    = sov_count + elite_count   # kept for day verdict logic
        game_edge_count = sum(1 for g in game_analysis if g.get("best_edge",0) >= 0.02)

        # Day verdict — uses elite_plus (SOV+ELITE combined)
        if elite_plus >= 4:
            action_label, action_color = "Strong Betting Day", "#22c55e"
            action_desc = "Multiple high-conviction plays confirmed by Pinnacle. Favor props over games today."
        elif elite_plus >= 2:
            action_label, action_color = "Selective Betting Day", "#e8a020"
            action_desc = "A few strong plays available. Be selective — stick to Sovereign and Elite tier only."
        elif elite_plus >= 1:
            action_label, action_color = "Light Betting Day", "#e8a020"
            action_desc = "Limited quality. Consider 1 pick max or sitting out."
        else:
            action_label, action_color = "No Strong Plays Today", "#e04040"
            action_desc = "No high-conviction plays. Best move is to wait for a better slate."

        st.html(f"""
        <div style="background:{action_color}11;border:1px solid {action_color}33;border-radius:8px;padding:1.2rem;margin-bottom:1.5rem;">
            <div style="color:{action_color};font-size:1.3rem;font-weight:700;margin-bottom:0.4rem;">⚡ {action_label.upper()}</div>
            <p style="color:var(--bc-muted);font-size:1.0rem;margin-bottom:1rem;">{action_desc}</p>
            <div style="display:flex;gap:0.8rem;">
                <div style="flex:1;background:var(--bc-bg-card);border-radius:6px;padding:0.7rem;text-align:center;border:0.5px solid var(--bc-border);">
                    <div style="color:#c8840a;font-size:0.85rem;text-transform:uppercase;letter-spacing:0.05em;">👑 SOV</div>
                    <div style="color:#c8840a;font-size:1.6rem;font-weight:700;">{sov_count}</div>
                </div>
                <div style="flex:1;background:var(--bc-bg-card);border-radius:6px;padding:0.7rem;text-align:center;border:0.5px solid var(--bc-border);">
                    <div style="color:#0ea5a0;font-size:0.85rem;text-transform:uppercase;letter-spacing:0.05em;">⭐ ELITE</div>
                    <div style="color:#0ea5a0;font-size:1.6rem;font-weight:700;">{elite_count}</div>
                </div>
                <div style="flex:1;background:var(--bc-bg-card);border-radius:6px;padding:0.7rem;text-align:center;border:0.5px solid var(--bc-border);">
                    <div style="color:var(--bc-blue);font-size:0.85rem;text-transform:uppercase;letter-spacing:0.05em;">✓ APP</div>
                    <div style="color:var(--bc-blue);font-size:1.6rem;font-weight:700;">{approved_count}</div>
                </div>
                <div style="flex:1;background:var(--bc-bg);border-radius:6px;padding:0.7rem;text-align:center;border:1px solid #4a5a6a44;">
                    <div style="color:var(--bc-dim);font-size:0.85rem;text-transform:uppercase;letter-spacing:0.05em;">📊 LEAN</div>
                    <div style="color:var(--bc-dim);font-size:1.6rem;font-weight:700;">{lean_count}</div>
                </div>
                <div style="flex:1;background:var(--bc-bg);border-radius:6px;padding:0.7rem;text-align:center;border:1px solid var(--bc-border);">
                    <div style="color:var(--bc-muted);font-size:0.85rem;text-transform:uppercase;letter-spacing:0.05em;">Total at Risk</div>
                    <div style="color:var(--bc-text);font-size:1.4rem;font-weight:700;">{round(sum(safe_float(p.get("Kelly",0)) for p in board if p.get("Tier") in ("SOVEREIGN","ELITE","APPROVED")), 1)}u</div>
                </div>
                <div style="flex:1;background:var(--bc-bg);border-radius:6px;padding:0.7rem;text-align:center;border:1px solid var(--bc-border);">
                    <div style="color:var(--bc-muted);font-size:0.85rem;text-transform:uppercase;letter-spacing:0.05em;">Game Edges</div>
                    <div style="color:var(--bc-text);font-size:1.4rem;font-weight:700;">{game_edge_count}</div>
                </div>
            </div>
        </div>
        """)

        # ── MATCHUPS ────────────────────────────────────────
        games_list = st.session_state.games or []
        if games_list:
            st.markdown('''<div style="display:flex;align-items:center;gap:0.75rem;margin:1rem 0 0.8rem;"><div style="flex:1;height:1px;background:var(--bc-bg2);"></div><span style="color:var(--bc-dim);font-size:1.0rem;text-transform:uppercase;letter-spacing:0.08em;">Today's Matchups</span><div style="flex:1;height:1px;background:var(--bc-bg2);"></div></div>''', unsafe_allow_html=True)
            games_html = '<div style="display:grid;grid-template-columns:1fr 1fr;gap:0.6rem;margin-bottom:0.5rem;">'
            for g in games_list[:6]:
                matchup = g.get("Matchup", g.get("matchup",""))
                total = g.get("Total", g.get("total",""))
                date_str = g.get("Date","")
                games_html += f"""
                <div style="background:var(--bc-bg);border:1px solid var(--bc-border);border-radius:6px;padding:0.7rem;">
                    <div style="color:var(--bc-text);font-weight:600;font-size:1.0rem;">{matchup}</div>
                    <div style="display:flex;justify-content:space-between;margin-top:0.3rem;">
                        <span style="color:var(--bc-muted);font-size:1.0rem;">{date_str}</span>
                        <span style="color:#b8c6d6;font-size:1.0rem;">O/U {total}</span>
                    </div>
                </div>"""
            games_html += '</div>'
            st.markdown(games_html, unsafe_allow_html=True)

        # ── INJURY ALERTS ───────────────────────────────────
        injury_props = [p for p in board if p.get("Injury")]
        rw_inj_today  = st.session_state.get("rw_injuries", [])
        cbs_inj_today = st.session_state.get("cbs_injuries", [])
        espn_inj_today= st.session_state.get("espn_injuries", [])
        # Combine all supplemental injury sources
        _all_supp_inj = rw_inj_today + cbs_inj_today + espn_inj_today
        rw_inj_serious = [i for i in _all_supp_inj if i.get("status") in ("OUT","DOUBTFUL","QUESTIONABLE")]
        # NFL practice participation trends
        _nfl_practice_alerts = []
        _summary_sport = st.session_state.get("last_sport", "NBA")
        if _summary_sport == "NFL":
            _practice_data = st.session_state.get("nfl_practice", {})
            for _pname, _pdata in _practice_data.items():
                if "DNP" in _pdata.get("trend","") or "Limited" in _pdata.get("trend",""):
                    _nfl_practice_alerts.append({
                        "player": _pname, "status": _pdata.get("trend",""),
                        "note": f"Practice: {_pdata.get('trend','')}",
                        "source": "ESPN Practice"
                    })
        if injury_props or rw_inj_serious:
            st.markdown('''<div style="display:flex;align-items:center;gap:0.75rem;margin:1rem 0 0.8rem;"><div style="flex:1;height:1px;background:var(--bc-bg2);"></div><span style="color:var(--bc-dim);font-size:1.0rem;text-transform:uppercase;letter-spacing:0.08em;">Injury Alerts</span><div style="flex:1;height:1px;background:var(--bc-bg2);"></div></div>''', unsafe_allow_html=True)
            inj_html = '<div style="background:#e0404011;border:1px solid #e0404033;border-radius:8px;padding:1rem;margin-bottom:0.5rem;">'
            seen_inj = set()
            # Board-level injuries (affect today's props)
            for ip in injury_props[:4]:
                player = ip.get("Player","")
                if player not in seen_inj:
                    seen_inj.add(player)
                    inj_html += (f'<div style="margin-bottom:0.5rem;">'
                                 f'<span style="color:#e04040;font-weight:700;">{player}</span> '
                                 f'<span style="color:#b8c6d6;font-size:1.0rem;">— {ip.get("Injury","Questionable")}: Monitor usage impact</span>'
                                 f'</div>')
            # RotoWire additional injuries not already shown
            for rw in rw_inj_serious[:6]:
                pname = rw.get("player","")
                if pname and pname not in seen_inj:
                    seen_inj.add(pname)
                    _sc = {"OUT":"#e04040","DOUBTFUL":"#e04040","QUESTIONABLE":"#e8a020"}.get(rw["status"],"#e8a020")
                    inj_html += (f'<div style="margin-bottom:0.4rem;">'
                                 f'<span style="color:{_sc};font-weight:700;">{pname}</span> '
                                 f'<span style="color:{_sc};font-size:0.85rem;">[{rw["status"]}]</span> '
                                 f'<span style="color:var(--bc-muted);font-size:0.9rem;">— {rw.get("note","")[:100]}</span> '
                                 f'<span style="color:#4a6a8a;font-size:0.8rem;">[RotoWire]</span>'
                                 f'</div>')
            inj_html += '</div>'
            st.markdown(inj_html, unsafe_allow_html=True)

        # ── SHARP MONEY ALERTS ──────────────────────────────
        sharp_alerts_s = st.session_state.get("sharp_alerts", [])
        steam_moves_s = st.session_state.get("steam_moves", [])
        all_sharp = sharp_alerts_s + steam_moves_s
        st.markdown('''<div style="display:flex;align-items:center;gap:0.75rem;margin:1rem 0 0.5rem;"><div style="flex:1;height:1px;background:var(--bc-bg2);"></div><span style="color:#e8a020;font-size:1.0rem;text-transform:uppercase;letter-spacing:0.08em;">⚡ Sharp Money</span><div style="flex:1;height:1px;background:var(--bc-bg2);"></div></div>''', unsafe_allow_html=True)
        if all_sharp:
            _sharp_html = []
            for _sa in all_sharp[:4]:
                _sa_c = {"line_move":"#e8a020","steam":"#e04040","public_vs_sharp":"#378add"}.get(_sa.get("type",""),"#6a7a8a")
                _sharp_html.append(f'<div style="background:var(--bc-bg-card);border-left:3px solid {_sa_c};border-radius:4px;padding:0.4rem 0.8rem;margin-bottom:0.3rem;font-size:1.05rem;color:var(--bc-text);">{_sa.get("message","")}</div>')
            st.markdown("".join(_sharp_html), unsafe_allow_html=True)
        else:
            st.markdown('<div style="color:var(--bc-dim);font-size:1.0rem;padding:0.2rem 0;">No sharp money movement detected — load board to scan.</div>', unsafe_allow_html=True)

        # ── PUBLIC VS. SHARP MONEY (Action Network tickets%/money% divergence) ──
        # Separate data source from the Sharp Money section above (that one is
        # EVSharps/Pinnacle line-movement based). This one is Action Network's
        # public betting splits — the actual "public is on X, big money is on Y,
        # here's why" signal. The detection logic already existed in
        # fetch_public_betting/compute_sharp_public_divergence with fully-built
        # narrative strings; it was just never displayed anywhere because the
        # reader functions looked up the wrong session_state key (fixed above).
        _pbd = st.session_state.get("public_betting_data", {})
        _pbd_narratives = []
        for _pbg in _pbd.values():
            _pbd_narratives.extend(_pbg.get("sharp_signals", []))
        st.markdown('''<div style="display:flex;align-items:center;gap:0.75rem;margin:1rem 0 0.5rem;"><div style="flex:1;height:1px;background:var(--bc-bg2);"></div><span style="color:#378add;font-size:1.0rem;text-transform:uppercase;letter-spacing:0.08em;">📊 Public vs. Sharp Money</span><div style="flex:1;height:1px;background:var(--bc-bg2);"></div></div>''', unsafe_allow_html=True)
        if not _pbd:
            st.markdown('<div style="color:var(--bc-dim);font-size:1.0rem;padding:0.2rem 0;">No public betting data loaded — load board to scan.</div>', unsafe_allow_html=True)
        elif not _pbd_narratives:
            st.markdown('<div style="color:var(--bc-dim);font-size:1.0rem;padding:0.2rem 0;">🟢 Quiet day — public and sharp money aligned across today\'s slate, no divergence detected.</div>', unsafe_allow_html=True)
        else:
            _n = len(_pbd_narratives)
            _day_label = ("🔥 Heavy divergence day" if _n >= 6 else
                          "⚡ Moderate divergence day" if _n >= 3 else
                          "🟡 Light divergence day")
            st.markdown(f'<div style="color:var(--bc-text);font-size:1.05rem;font-weight:600;margin-bottom:0.4rem;">{_day_label} — {_n} public/sharp split{"s" if _n != 1 else ""} across today\'s slate</div>', unsafe_allow_html=True)
            _pbd_html = [f'<div style="background:var(--bc-bg-card);border-left:3px solid #378add;border-radius:4px;padding:0.4rem 0.8rem;margin-bottom:0.3rem;font-size:1.0rem;color:var(--bc-text);white-space:pre-line;">{_note}</div>' for _note in _pbd_narratives[:6]]
            st.markdown("".join(_pbd_html), unsafe_allow_html=True)



        # ═══════════════════════════════════════════════════
        # SECTION 2 — TOP PLAYS QUEUE
        # ═══════════════════════════════════════════════════
        # ── BEST BET QUEUE ─────────────────────────────────
        # Deduplicate by player — only show each player once
        _seen_players_bbq = set()
        _top_plays = []
        for _bbq_p in sorted(board, key=lambda x: (["SOVEREIGN","ELITE","APPROVED","LEAN","PASS"].index(x.get("Tier","PASS")) if x.get("Tier","PASS") in ["SOVEREIGN","ELITE","APPROVED","LEAN","PASS"] else 99, -float(x.get("Edge",0) or 0))):
            if _bbq_p.get("Tier") not in ("SOVEREIGN","ELITE"): continue
            _bbq_key = normalize_name(_bbq_p.get("Player",""))
            if _bbq_key not in _seen_players_bbq:
                _seen_players_bbq.add(_bbq_key)
                _top_plays.append(_bbq_p)
            if len(_top_plays) >= 6: break
        if _top_plays:
            st.markdown("""<div style="display:flex;align-items:center;gap:0.75rem;margin:0.5rem 0 0.8rem;">
                <div style="flex:1;height:1px;background:var(--bc-bg2);"></div>
                <span style="color:var(--bc-dim);font-size:1.0rem;text-transform:uppercase;letter-spacing:0.08em;">🎯 Best Bet Queue</span>
                <div style="flex:1;height:1px;background:var(--bc-bg2);"></div></div>""", unsafe_allow_html=True)
            for _qi, _qp in enumerate(_top_plays):
                _qe = _qp.get("Edge",0)
                _qc = "#22c55e" if _qp.get("Tier")=="SOVEREIGN" else "#378add"
                _qpin = "📌 " if _qp.get("PinnacleConfirms") else ""
                # Build inline Why drivers
                _q_drivers, _q_risks = generate_why_drivers(_qp)
                _q_why = ""
                if _q_drivers:
                    _q_why = " · ".join(
                        f'<span style="color:{c};font-size:10px;">{l} <b>{v}</b></span>'
                        for l, v, c in _q_drivers
                    )
                if _q_risks:
                    _q_why += (" &nbsp;|&nbsp; "
                        + " · ".join(
                            f'<span style="color:{c};font-size:10px;">⚠️ {l} {v}</span>'
                            for l, v, c in _q_risks
                        ))
                st.markdown(
                    f'<div style="background:var(--bc-bg);border:1px solid var(--bc-border);'
                    f'border-left:3px solid {_qc};border-radius:6px;'
                    f'padding:0.5rem 0.8rem 0.4rem;margin-bottom:0.4rem;">'
                    f'<div style="display:flex;align-items:center;gap:0.8rem;">'
                    f'<span style="color:{_qc};font-weight:700;font-size:1.1rem;min-width:22px;">#{_qi+1}</span>'
                    f'<span style="color:var(--bc-text);font-weight:600;flex:1;">{_qp.get("Player","")} '
                    f'{_qp.get("Side","OVER")} {_qp.get("Line","")}</span>'
                    f'<span style="color:var(--bc-muted);font-size:0.9rem;">{_qp.get("Prop","")}</span>'
                    f'<span style="color:{_qc};font-weight:700;">Edge {_qe:.1%}</span>'
                    f'<span style="color:#7f77dd;">{_qpin}</span>'
                    f'</div>'
                    + (f'<div style="margin-top:3px;padding-left:30px;">{_q_why}</div>'
                       if _q_why else "")
                    + f'</div>',
                    unsafe_allow_html=True
                )
                _bbq_already_locked = any(
                    normalize_name(l.get("player","")) == normalize_name(_qp.get("Player","")) and
                    str(l.get("line","")) == str(_qp.get("Line",""))
                    for l in st.session_state.get("locks", [])
                )
                _bbq_lock_col, _bbq_why_col = st.columns([1, 5])
                with _bbq_lock_col:
                    if _bbq_already_locked:
                        st.caption("🔒 Locked")
                    else:
                        _bbq_lock_key = f"bbq_lock_{_qi}_{normalize_name(_qp.get('Player',''))[:20]}"
                        if st.button("🔒 Lock", key=_bbq_lock_key, use_container_width=True):
                            _bbq_sport = _qp.get("Sport", st.session_state.get("last_sport", SPORTS[0]))
                            if _lock_board_prop(_qp, _bbq_sport, "Best Bet Queue"):
                                st.success(f"Locked {_qp.get('Player','')} {_qp.get('Prop','')}")
                                st.rerun()
                            else:
                                st.info("Already locked")
                with _bbq_why_col:
                    with st.expander(f"Why this pick — {_qp.get('Player','')}", expanded=False):
                        st.markdown(
                            render_signal_chart(_qp, st.session_state.get("last_sport", SPORTS[0])),
                            unsafe_allow_html=True
                        )


        # ═══════════════════════════════════════════════════
        # SECTION 3 — LOCK OF THE DAY
        # ═══════════════════════════════════════════════════
        # ── LOCK OF THE DAY — PROP ─────────────────────────
        if board:
            st.markdown(
                '<div style="background:linear-gradient(135deg,#0d1a0d,#0a1a2a);border:1px solid #22c55e44;border-radius:10px;padding:0.6rem 1.2rem;margin:1rem 0 0.6rem;display:flex;align-items:center;gap:0.8rem;">'
                '<span style="font-size:1.4rem;">🔒</span>'
                '<span style="color:#22c55e;font-size:1.15rem;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;">Lock of the Day</span>'
                '<div style="flex:1;height:1px;background:#22c55e33;"></div>'
                '</div>',
                unsafe_allow_html=True
            )
            sorted_board = sorted(board, key=lambda x: x.get("Edge",0), reverse=True)
            lock_prop = sorted_board[0]
            tier = lock_prop.get("Tier","LEAN")
            tier_color = TIER_COLORS.get(tier, "#6a7a8a")
            prob = float(lock_prop.get("Prob") or 0.5)
            ev_2 = lock_prop.get("EV_2pick","—") or "—"
            pinnacle_prob = lock_prop.get("PinnacleProb","—") or "—"
            pinnacle_confirms = lock_prop.get("PinnacleConfirms", False)
            better_line = lock_prop.get("BetterLineNote","") or ""
            edge = float(lock_prop.get("Edge") or 0)
            avg = float(lock_prop.get("Avg") or lock_prop.get("Line") or 0)
            lock_score = min(100, int(abs(edge)*300 + (prob - 0.5)*200 + (50 if pinnacle_confirms else 0)))
            _avg_display = f"{avg:.1f}" if avg else "—"
            _prob_display = f"{prob:.1%}"
            _ev2_display = str(ev_2)
            _pinn_display = str(pinnacle_prob)
            # Pre-compute conditionals to avoid f-string quote conflicts
            _pinn_badge = '<span style="color:#7f77dd;font-size:1.0rem;">&#128302; PINNACLE CONFIRMED</span>' if pinnacle_confirms else ""
            _better_html = f'<div style="color:#22c55e;font-size:1.0rem;margin-bottom:0.5rem;">&#9889; {better_line}</div>' if better_line else ""
            _risk_note = lock_prop.get("PinnacleNote","monitor lineup")[:50]
            _player_line = f'{lock_prop.get("Player","")} &mdash; {lock_prop.get("Side","")} {lock_prop.get("Line","")} {lock_prop.get("Prop","")}'
            _lock_html = f"""
            <div style="background:var(--bc-bg);border:1px solid var(--bc-border);border-top:3px solid #22c55e;border-radius:8px;padding:1.2rem;margin-bottom:1rem;">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.6rem;">
                    <span style="background:{tier_color}22;color:{tier_color};padding:0.2rem 0.7rem;border-radius:20px;font-size:1.15rem;font-weight:700;">{tier}</span>
                    {_pinn_badge}
                </div>
                <div style="font-size:1.3rem;font-weight:700;color:var(--bc-text);margin-bottom:0.8rem;">{_player_line}</div>
                <div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:0.5rem;margin-bottom:0.8rem;">
                    <div style="background:var(--bc-bg-card);border-radius:5px;padding:0.5rem;text-align:center;">
                        <div style="color:var(--bc-muted);font-size:1.0rem;text-transform:uppercase;">Season Avg</div>
                        <div style="color:var(--bc-text);font-weight:700;">{_avg_display}</div>
                    </div>
                    <div style="background:var(--bc-bg-card);border-radius:5px;padding:0.5rem;text-align:center;">
                        <div style="color:var(--bc-muted);font-size:1.0rem;text-transform:uppercase;">Hit Prob</div>
                        <div style="color:#22c55e;font-weight:700;">{_prob_display}</div>
                    </div>
                    <div style="background:var(--bc-bg-card);border-radius:5px;padding:0.5rem;text-align:center;">
                        <div style="color:var(--bc-muted);font-size:1.0rem;text-transform:uppercase;">Pinnacle</div>
                        <div style="color:#7f77dd;font-weight:700;">{_pinn_display}</div>
                    </div>
                    <div style="background:var(--bc-bg-card);border-radius:5px;padding:0.5rem;text-align:center;">
                        <div style="color:var(--bc-muted);font-size:1.0rem;text-transform:uppercase;">2-Pick EV</div>
                        <div style="color:#22c55e;font-weight:700;">{_ev2_display}</div>
                    </div>
                </div>
                {_better_html}
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <span style="color:#22c55e;font-weight:700;font-size:1.0rem;">&#128274; Lock Quality: {lock_score}/100</span>
                    <span style="color:#e04040;font-size:1.0rem;">Risk: {_risk_note}</span>
                </div>
            </div>"""
            # Use st.markdown — components.html iframes don't inherit CSS vars
            _lock_html_fixed = (_lock_html
                .replace("var(--bc-bg)", "#000000")
                .replace("var(--bc-bg-card)", "#0d1b2e")
                .replace("var(--bc-border)", "#1a3a5c")
                .replace("var(--bc-text)", "#ffffff")
                .replace("var(--bc-muted)", "#8ab4d4")
                .replace("var(--bc-dim)", "#4a6a8a")
                .replace("var(--bc-blue)", "#1e90ff")
                .replace("var(--bc-blue-bright)", "#4db8ff")
            )
            _lock_html_fixed = "\n".join(_ln.strip() for _ln in _lock_html_fixed.splitlines())
            st.markdown(_lock_html_fixed, unsafe_allow_html=True)
            # ── Why This Is A Play — Signal Contribution Table ──
            _sig_table = render_signal_contribution_table(lock_prop)
            if _sig_table:
                st.markdown(
                    f'<div style="background:var(--bc-bg-card);border:0.5px solid var(--bc-border);'
                    f'border-top:none;border-radius:0 0 8px 8px;'
                    f'padding:0.5rem 1rem;margin-top:-4px;margin-bottom:8px;">'
                    f'{_sig_table}</div>',
                    unsafe_allow_html=True
                )
            # Track from Summary tab lock card
            _tlk_key = f"sum_track_{lock_prop.get('Player','').replace(' ','_')[:15]}"
            if st.button("📝 Track This Bet", key=_tlk_key, type="secondary"):
                track_bet_dialog(lock_prop)
            # Signal chart visible by default — no expander needed
            # Why This Play is the key differentiator, should be visible
            try:
                chart_html = render_signal_chart(lock_prop, st.session_state.get("last_sport", SPORTS[0]))
                if chart_html:
                    st.markdown(
                        f'<div style="margin-top:-4px;margin-bottom:12px;">'
                        f'{chart_html}</div>',
                        unsafe_allow_html=True
                    )
            except (ValueError, KeyError, TypeError, AttributeError):
                pass


        # ═══════════════════════════════════════════════════
        # SECTION 4 — GAME LOCK
        # ═══════════════════════════════════════════════════
        # ── LOCK OF THE DAY — GAME ─────────────────────────
        if game_analysis:
            st.markdown('''<div style="display:flex;align-items:center;gap:0.75rem;margin:1rem 0 0.8rem;"><div style="flex:1;height:1px;background:var(--bc-bg2);"></div><span style="color:var(--bc-dim);font-size:1.0rem;text-transform:uppercase;letter-spacing:0.08em;">Lock of the Day — Game</span><div style="flex:1;height:1px;background:var(--bc-bg2);"></div></div>''', unsafe_allow_html=True)
            best_game = max(game_analysis, key=lambda x: x.get("best_edge",0))
            bb = best_game.get("best_bet",{})
            if bb:
                st.html(f"""
                <div style="background:var(--bc-bg);border:1px solid var(--bc-border);border-top:3px solid #378add;border-radius:8px;padding:1.2rem;margin-bottom:1rem;">
                    <div style="font-size:1.0rem;color:var(--bc-blue);text-transform:uppercase;font-weight:700;margin-bottom:0.3rem;">{bb.get("type","Game")} Lock</div>
                    <div style="font-size:1.2rem;font-weight:700;color:var(--bc-text);margin-bottom:0.5rem;">{best_game.get("matchup","")} — {bb.get("pick","")}</div>
                    <div style="display:flex;gap:1.5rem;margin-bottom:0.5rem;">
                        <span style="color:var(--bc-blue);font-weight:700;">Edge: {abs(bb.get("edge",0)):.1%}</span>
                        <span style="color:#7f77dd;font-size:1.0rem;">{bb.get("note","")[:80]}</span>
                    </div>
                    <div style="display:flex;gap:0.8rem;font-size:1.0rem;color:var(--bc-muted);">
                        <span>Spread: {best_game.get("games",{}).get("Spread","—") if isinstance(best_game.get("games"),dict) else "—"}</span>
                        <span>Total: {best_game.get("games",{}).get("Total","—") if isinstance(best_game.get("games"),dict) else "—"}</span>
                    </div>
                </div>
                """)
        if game_analysis:
            _best_g = max(game_analysis, key=lambda x: x.get("best_edge",0))
            _game_edge = float(_best_g.get("best_edge",0) or 0)
            _game_score = min(100, int(
                min(30, _game_edge * 150) +
                20 +
                (10 if _game_edge >= 0.10 else 5 if _game_edge >= 0.05 else 0)
            ))
            _gscore_icon = "🟢" if _game_score >= 80 else "🟡" if _game_score >= 60 else "🟠" if _game_score >= 40 else "🔴"
            st.markdown(f'<div style="background:var(--bc-bg-card);border:0.5px solid var(--bc-border);border-radius:6px;padding:0.6rem 1rem;margin-top:0.3rem;"><span style="color:var(--bc-dim);font-size:1.0rem;">LOCK QUALITY SCORE: </span><span style="color:var(--bc-text);font-weight:700;">{_game_score}/100 {_gscore_icon}</span></div>', unsafe_allow_html=True)

        # ── BEST GAME QUEUE ─────────────────────────────────
        _top_games = sorted(
            [g for g in game_analysis if g.get("best_edge",0) >= 0.015 and g.get("best_bet")],
            key=lambda x: x.get("best_edge",0), reverse=True
        )[:5]
        if len(_top_games) >= 2:
            st.markdown('''<div style="display:flex;align-items:center;gap:0.75rem;margin:1rem 0 0.8rem;"><div style="flex:1;height:0.5px;background:var(--bc-border);"></div><span style="color:var(--bc-dim);font-size:1.0rem;text-transform:uppercase;letter-spacing:0.08em;">🏟️ Best Game Queue</span><div style="flex:1;height:0.5px;background:var(--bc-border);"></div></div>''', unsafe_allow_html=True)
            for _gi, _tg in enumerate(_top_games, 1):
                _tbb    = _tg.get("best_bet", {})
                _tge    = float(_tg.get("best_edge",0) or 0)
                _ttype  = _tbb.get("type","")
                _tpick  = _tbb.get("pick","")
                _tnote  = _tbb.get("note","")[:70]
                _ttier  = _tg.get("tier","LEAN") if _tg.get("tier") else ("SOVEREIGN" if _tge>=0.06 else "ELITE" if _tge>=0.03 else "APPROVED")
                _tc     = TIER_COLORS.get(_ttier,"#6a7a8a")
                st.markdown(f'''
                <div style="background:var(--bc-bg-card);border:0.5px solid var(--bc-border);border-left:3px solid {_tc};border-radius:8px;padding:0.9rem 1rem;margin-bottom:0.5rem;">
                    <div style="display:flex;justify-content:space-between;align-items:center;">
                        <div>
                            <span style="color:var(--bc-dim);font-size:0.85rem;">#{_gi} &nbsp;</span>
                            <span style="color:var(--bc-text);font-weight:600;">{_tg.get("matchup","")} — {_ttype} {_tpick}</span>
                        </div>
                        <div style="text-align:right;">
                            <span style="color:{_tc};font-weight:700;font-size:1.0rem;">Edge {abs(_tge):.1%}</span>
                            <span style="color:var(--bc-dim);font-size:0.85rem;margin-left:0.5rem;">{_ttier}</span>
                        </div>
                    </div>
                    <div style="color:var(--bc-muted);font-size:0.9rem;margin-top:0.3rem;">{_tnote}</div>
                </div>
                ''', unsafe_allow_html=True)


        # ═══════════════════════════════════════════════════
        # SECTION 5 — PARLAY
        # Note: intentionally AFTER Players to Avoid so
        # the "singles only" message doesn't contradict
        # the Best Bet Queue shown above.
        # ═════════════════════════��═════════════════════════
        # ── PARLAY OF THE DAY — PROPS ──────────────────────
        st.markdown('''<div style="display:flex;align-items:center;gap:0.75rem;margin:1rem 0 0.8rem;"><div style="flex:1;height:1px;background:var(--bc-border);"></div><span style="color:var(--bc-dim);font-size:1.0rem;text-transform:uppercase;letter-spacing:0.08em;">Parlay of the Day — Props</span><div style="flex:1;height:1px;background:var(--bc-border);"></div></div>''', unsafe_allow_html=True)
        # Filter to current sport only, SOVEREIGN/ELITE tier
        _cur_sport = st.session_state.get("last_sport", "NBA")
        # Dedup parlay props by player
        _seen_pp = set()
        parlay_props = []
        for _ppp in sorted(board, key=lambda x: x.get("Edge",0), reverse=True):
            if _ppp.get("Tier","") not in ["SOVEREIGN","ELITE"]: continue
            if _ppp.get("Sport","") != _cur_sport: continue
            _ppk = normalize_name(_ppp.get("Player",""))
            if _ppk not in _seen_pp:
                _seen_pp.add(_ppk)
                parlay_props.append(_ppp)
            if len(parlay_props) >= 4: break
        n_parlay = st.session_state.get("parlay_size", 3)
        parlay_props = parlay_props[:n_parlay]

        # ── Correlated leg edge discounting ───────────────
        # When legs share a team or same-player props, the independence
        # assumption breaks down. Discount each correlated leg's effective
        # probability proportional to the pairwise correlation coefficient.
        # This is the correct treatment per Kelly theory — correlated bets
        # have lower effective edge than the sum of their individual edges.
        def _apply_corr_discount(legs):
            if len(legs) < 2:
                return legs
            discounted = list(legs)
            for i, p1 in enumerate(discounted):
                for j, p2 in enumerate(discounted):
                    if j <= i:
                        continue
                    p1_player = normalize_name(p1.get("Player",""))
                    p2_player = normalize_name(p2.get("Player",""))
                    p1_prop   = p1.get("Prop","")
                    p2_prop   = p2.get("Prop","")
                    p1_team   = p1.get("Team", p1.get("team",""))
                    p2_team   = p2.get("Team", p2.get("team",""))
                    corr = 0.0
                    if p1_player and p1_player == p2_player:
                        pair_key = tuple(sorted([p1_prop, p2_prop]))
                        corr = PROP_CORRELATION_PAIRS.get(pair_key, 0.50)
                    elif p1_team and p1_team == p2_team:
                        corr = TEAM_GAME_CORRELATION
                    if corr > 0.15:
                        # Discount effective prob toward 0.5 proportional to corr
                        discount = 1.0 - corr * 0.25
                        for idx in (i, j):
                            raw_prob = float(discounted[idx].get("Prob", 0.55))
                            raw_edge = float(discounted[idx].get("Edge", 0))
                            adj_prob = 0.5 + (raw_prob - 0.5) * discount
                            adj_edge = raw_edge * discount
                            discounted[idx] = {
                                **discounted[idx],
                                "Prob":         round(adj_prob, 4),
                                "Edge":         round(adj_edge, 4),
                                "_corr_disc":   round(1.0 - discount, 3),
                            }
            return discounted
        parlay_props = _apply_corr_discount(parlay_props)
        if len(parlay_props) >= 2:
            parlay_probs = [p.get("Prob", 0.55) for p in parlay_props]
            combined = parlay_prob(parlay_probs)
            be = prizepicks_breakeven_prob(len(parlay_props))
            ev = calculate_prizepicks_ev(combined, len(parlay_props))
            # Only show if positive EV — otherwise show warning
            if ev > 0:
                ev_color = "#22c55e"
                tier_dot = TIER_COLORS
                legs_html = ""
                for p in parlay_props:
                    dot_c = tier_dot.get(p.get("Tier",""),"#6a7a8a")
                    legs_html += f'<div style="background:var(--bc-bg-card);border-radius:5px;padding:0.5rem 0.7rem;margin-bottom:0.4rem;display:flex;align-items:center;gap:0.5rem;"><span style="width:7px;height:7px;border-radius:50%;background:{dot_c};flex-shrink:0;"></span><span style="color:var(--bc-text);font-size:1.0rem;">{p.get("Player","")} {p.get("Side","")} {p.get("Line","")} {p.get("Prop","")}</span><span style="color:var(--bc-dim);font-size:1.0rem;margin-left:auto;">{p.get("EV_2pick","—")}</span></div>'
                st.html(f"""
                <div style="background:var(--bc-bg);border:1px solid #22c55e33;border-radius:8px;padding:1.2rem;margin-bottom:1rem;">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.5rem;">
                        <span style="color:var(--bc-text);font-weight:700;">{len(parlay_props)}-Pick Prop Parlay · {PRIZEPICKS_MULTIPLIERS.get(len(parlay_props),3)}x</span>
                        <span style="color:#22c55e;font-weight:700;font-size:1rem;">{ev:+.1%} EV ▶ PLAY</span>
                    </div>
                    <div style="display:flex;gap:1.5rem;font-size:1.0rem;margin-bottom:0.7rem;">
                        <span style="color:#b8c6d6;">Combined: <span style="color:var(--bc-text);">{combined:.1%}</span></span>
                        <span style="color:var(--bc-muted);">Breakeven: {be:.1%}</span>
                    </div>
                    {legs_html}
                </div>
                """)
            else:
                # Identify which props are recommended as singles
                _single_plays = [p for p in parlay_props if p.get("Edge",0) >= 0.08]
                _single_html = ""
                for _sp in _single_plays[:3]:
                    _single_html += f'<div style="color:var(--bc-text);font-size:0.9rem;padding:0.2rem 0;">· {_sp.get("Player","")} {_sp.get("Side","")} {_sp.get("Line","")} {_sp.get("Prop","")} <span style="color:#22c55e;">({_sp.get("Edge",0):+.1%} edge)</span></div>'
                st.html(f"""
                <div style="background:var(--bc-bg-card);border:0.5px solid var(--bc-border);border-left:3px solid #e8a020;border-radius:8px;padding:1rem;margin-bottom:0.5rem;">
                    <div style="color:#e8a020;font-weight:600;margin-bottom:0.4rem;">⚠️ Singles Only — Skip the Parlay Today</div>
                    <div style="color:var(--bc-muted);font-size:0.95rem;line-height:1.6;">
                        These props have positive edge individually, but combining them drops the
                        combined probability to <strong>{combined:.1%}</strong> — below the
                        <strong>{be:.1%}</strong> breakeven needed for a {len(parlay_props)}-pick parlay.<br><br>
                        <strong style="color:var(--bc-text);">Recommended as singles:</strong>
                        {_single_html if _single_html else "<div style='color:var(--bc-muted);'>Take the top edge plays individually.</div>"}
                        <br><div style="color:var(--bc-dim);font-size:0.85rem;margin-top:0.3rem;">
                        Note: The Best +EV Props section below shows the same plays ranked by individual edge — those are your singles targets.
                        </div>
                    </div>
                </div>
                """)
        else:
            st.markdown('<div style="color:var(--bc-dim);font-size:1.0rem;padding:0.3rem 0;">Need 2+ SOVEREIGN/ELITE props to build a parlay.</div>', unsafe_allow_html=True)

        # ── PLAYERS TO AVOID (always visible) ──────────────
        st.markdown('''<div style="display:flex;align-items:center;gap:0.75rem;margin:1rem 0 0.8rem;"><div style="flex:1;height:1px;background:var(--bc-border);"></div><span style="color:#e04040;font-size:1.0rem;text-transform:uppercase;letter-spacing:0.08em;">Players to Avoid</span><div style="flex:1;height:1px;background:var(--bc-border);"></div></div>''', unsafe_allow_html=True)
        avoid_props = [p for p in sorted(board, key=lambda x: x.get("Edge",0))
                       if p.get("Edge",0) < 0
                       and p.get("Sport","") == _cur_sport][:5]
        if avoid_props:
            _fade_html = []
            for ap in avoid_props:
                _ap_avg = ap.get("Avg", 0) or 0
                _ap_line = ap.get("Line", 0) or 0
                _ap_edge = ap.get("EdgePct","—")
                _ap_reason = ap.get("PinnacleNote","") or f"Model projects avg {_ap_avg:.1f} vs line {_ap_line} — line is too high"
                _fade_html.append(f'<div style="background:var(--bc-bg-card);border-left:3px solid #e04040;border-radius:4px;padding:0.6rem 0.9rem;margin-bottom:0.4rem;"><div style="display:flex;align-items:center;justify-content:space-between;"><span style="color:var(--bc-text);font-weight:600;font-size:1.0rem;">{ap.get("Player","")} — {ap.get("Side","")} {ap.get("Line","")} {ap.get("Prop","")}</span><span style="color:#e04040;font-weight:600;font-size:1.0rem;">FADE {_ap_edge}</span></div><div style="font-size:1.0rem;color:var(--bc-muted);margin-top:3px;">{_ap_reason[:90]}</div></div>')
            st.markdown("".join(_fade_html), unsafe_allow_html=True)
        else:
            st.markdown('<div style="background:var(--bc-bg);border:1px solid var(--bc-border);border-radius:6px;padding:0.6rem 0.9rem;color:var(--bc-dim);font-size:1.05rem;">✅ No strong fades today — all props show positive or neutral edge.</div>', unsafe_allow_html=True)


        # ═══════════════════════════════════════════════════
        # SECTION 6 — DASHBOARD + ANALYTICS (secondary)
        # ═══���═══════════════════════════════════════════════
        st.markdown("---")
        # ══════════════════════════════════════════════════════
        # PROFESSIONAL DASHBOARD — 5 insight cards
        # ══════════════════════════════════════════════════════
        st.markdown("---")
        _d1, _d2, _d3, _d4, _d5 = st.columns(5)

        # Card 1 — Edge Distribution
        with _d1:
            _tier_counts = {"SOVEREIGN":0,"ELITE":0,"APPROVED":0,"LEAN":0,"PASS":0}
            for _p in board:
                _t = _p.get("Tier","PASS")
                _tier_counts[_t] = _tier_counts.get(_t, 0) + 1
            _tier_html = "".join([
                f'<div style="display:flex;justify-content:space-between;font-size:11px;padding:1px 0;">'
                f'<span style="color:var(--bc-muted);">{t}</span>'
                f'<span style="color:{"#22c55e" if t in ("SOVEREIGN","ELITE") else "#e8f0f8"};font-weight:{"700" if t in ("SOVEREIGN","ELITE") else "400"};">{c}</span>'
                f'</div>'
                for t, c in _tier_counts.items() if c > 0
            ])
            st.markdown(
                f'<div style="background:var(--bc-bg);border:1px solid var(--bc-border);border-radius:8px;padding:0.8rem;">'
                f'<div style="color:var(--bc-dim);font-size:10px;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.4rem;">📊 Edge Distribution</div>'
                f'{_tier_html}</div>',
                unsafe_allow_html=True
            )

        # Card 2 — Sport Exposure
        with _d2:
            _sport_exp = {}
            _total_locked = max(1, sum(1 for _p in board if _p.get("Tier") in ("SOVEREIGN","ELITE","APPROVED")))
            for _p in board:
                if _p.get("Tier") in ("SOVEREIGN","ELITE","APPROVED"):
                    _s = _p.get("Sport", _p.get("sport","?"))
                    _sport_exp[_s] = _sport_exp.get(_s, 0) + 1
            _exp_html = "".join([
                f'<div style="display:flex;justify-content:space-between;font-size:11px;padding:1px 0;">'
                f'<span style="color:var(--bc-muted);">{s}</span>'
                f'<span style="color:var(--bc-text);">{round(c/_total_locked*100)}%</span>'
                f'</div>'
                for s, c in sorted(_sport_exp.items(), key=lambda x: -x[1])[:5]
            ])
            _exp_fallback = '<div style="color:var(--bc-dim);font-size:11px;">Load board first</div>'
            st.markdown(
                f'<div style="background:var(--bc-bg);border:1px solid var(--bc-border);border-radius:8px;padding:0.8rem;">'
                f'<div style="color:var(--bc-dim);font-size:10px;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.4rem;">🎯 Sport Exposure</div>'
                f'{_exp_html or _exp_fallback}</div>',
                unsafe_allow_html=True
            )

        # Card 3 — CLV Tracker
        with _d3:
            try:
                _clv = get_clv_summary(st.session_state.get("history", []))
                _clv = _clv if isinstance(_clv, dict) else {}
            except Exception:
                _clv = {}
            if _clv and isinstance(_clv.get("avg_clv"), (int, float)):
                _clv_color = "#22c55e" if _clv.get("avg_clv", 0) > 0 else "#e04040"
                _sharp_edge = _clv.get("consensus_sharp_edge", _clv.get("pinnacle_avg_edge", 0)) or 0
                _sharp_color = "#22c55e" if _sharp_edge > 0 else "#e04040"
                _n_books = _clv.get("n_sharp_books", 1)
                _book_label = f"vs {_n_books} sharp book{'s' if _n_books > 1 else ''}"
                _clv_html = (
                    f'<div style="font-size:20px;font-weight:700;color:{_clv_color};">{_clv.get("avg_clv", 0):+.2f}</div>'
                    f'<div style="font-size:10px;color:var(--bc-muted);">Avg CLV</div>'
                    f'<div style="font-size:11px;color:{_sharp_color};margin-top:3px;">{_book_label}: {_sharp_edge:+.1%}</div>'
                    f'<div style="font-size:10px;color:var(--bc-dim);">{_clv.get("total_tracked", _clv.get("n_resolved", 0))} bets tracked</div>'
                )
            else:
                _clv_html = '<div style="font-size:11px;color:var(--bc-dim);">CLV activates<br>after 5 bets</div>'
            st.markdown(
                f'<div style="background:var(--bc-bg);border:1px solid var(--bc-border);border-radius:8px;padding:0.8rem;">'
                f'<div style="color:var(--bc-dim);font-size:10px;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.4rem;">📈 CLV Tracker</div>'
                f'{_clv_html}</div>',
                unsafe_allow_html=True
            )

        # Card 4 — Signal Health
        with _d4:
            _sig_perf = load_json_data(SIGNAL_PERFORMANCE_PATH, [], mem_ttl=60)
            _sig_resolved = [p for p in _sig_perf if p.get("outcome") in ("WIN","LOSS")]
            if len(_sig_resolved) >= 10:
                _sig_html = ""
                for _sig, _lbl in [
                    ("signal_defense_positive","Defense"),
                    ("signal_base_positive","Base"),
                    ("signal_sharp_flag","Sharp"),
                    ("signal_usage_boost","Usage"),
                ]:
                    _with = [r for r in _sig_resolved if r.get(_sig,0)==1]
                    if len(_with) >= 3:
                        _wr = sum(r["win"] for r in _with) / len(_with)
                        _overall = sum(r["win"] for r in _sig_resolved) / len(_sig_resolved)
                        _lift = _wr - _overall
                        _c = "#22c55e" if _lift > 0.02 else ("#e04040" if _lift < -0.02 else "#8a9ab0")
                        _sig_html += (
                            f'<div style="display:flex;justify-content:space-between;font-size:11px;padding:1px 0;">'
                            f'<span style="color:var(--bc-muted);">{_lbl}</span>'
                            f'<span style="color:{_c};">{_lift:+.1%}</span>'
                            f'</div>'
                        )
            else:
                _sig_html = f'<div style="font-size:11px;color:var(--bc-dim);">Signal health<br>activates at 10 bets</div>'
            st.markdown(
                f'<div style="background:var(--bc-bg);border:1px solid var(--bc-border);border-radius:8px;padding:0.8rem;">'
                f'<div style="color:var(--bc-dim);font-size:10px;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.4rem;">⚡ Signal Health</div>'
                f'{_sig_html}</div>',
                unsafe_allow_html=True
            )

        # Card 5 — Tier Performance
        with _d5:
            _resolved = [h for h in st.session_state.get("history", []) if h.get("outcome") in ("WIN","LOSS")]
            if len(_resolved) >= 10:
                _tier_perf_html = ""
                for _tier, _color in [("SOVEREIGN","#22c55e"),("ELITE","#378add"),("APPROVED","#e8a020"),("LEAN","#8a9ab0")]:
                    _tr = [h for h in _resolved if h.get("tier","") == _tier]
                    if len(_tr) >= 3:
                        _twr = sum(1 for h in _tr if h.get("outcome")=="WIN") / len(_tr)
                        _tier_perf_html += (
                            f'<div style="display:flex;justify-content:space-between;font-size:11px;padding:1px 0;">'
                            f'<span style="color:{_color};">{_tier[:3]}</span>'
                            f'<span style="color:var(--bc-text);">{_twr:.0%}</span>'
                            f'<span style="color:var(--bc-dim);">n={len(_tr)}</span>'
                            f'</div>'
                        )
            else:
                _tier_perf_html = '<div style="font-size:11px;color:var(--bc-dim);">Tier performance<br>activates at 10 bets</div>'
            st.markdown(
                f'<div style="background:var(--bc-bg);border:1px solid var(--bc-border);border-radius:8px;padding:0.8rem;">'
                f'<div style="color:var(--bc-dim);font-size:10px;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.4rem;">🏆 Tier Performance</div>'
                f'{_tier_perf_html}</div>',
                unsafe_allow_html=True
            )
        st.markdown("---")

        # ── PARLAY OF THE DAY — GAMES ──────────────────────
        st.markdown('''<div style="display:flex;align-items:center;gap:0.75rem;margin:1rem 0 0.8rem;"><div style="flex:1;height:1px;background:var(--bc-bg2);"></div><span style="color:var(--bc-dim);font-size:1.0rem;text-transform:uppercase;letter-spacing:0.08em;">Parlay of the Day — Games</span><div style="flex:1;height:1px;background:var(--bc-bg2);"></div></div>''', unsafe_allow_html=True)
        top_games = sorted([g for g in game_analysis if g.get("best_bet") and g.get("best_edge",0)>=0.02], key=lambda x: x.get("best_edge",0), reverse=True)[:3]
        # Compute prop-to-prop correlation for parlay picks
        _top_for_corr = [p for p in board if p.get("Tier") in ("SOVEREIGN","ELITE")][:5]
        if len(_top_for_corr) >= 2:
            try:
                _corr_score, _corr_pairs = compute_parlay_correlation(_top_for_corr)
                if _corr_score > 0.40 and _corr_pairs:
                    # compute_parlay_correlation() returns plain, already-
                    # readable sentences (e.g. "Chase DeLauter has multiple
                    # props"), not a {pair, reason} structure -- the old
                    # code tried to split one out that never existed,
                    # which is why this rendered with empty parens.
                    _cp_reason = _corr_pairs[0] if isinstance(_corr_pairs[0], str) else str(_corr_pairs[0])
                    st.warning(f"⚠️ These top picks overlap more than usual ({_corr_score:.0%} correlated): {_cp_reason}. "
                               f"If one of these misses, the others are likely to miss too — treat this as one bigger bet, not several independent ones.")
            except (TypeError, KeyError, IndexError, ValueError):
                pass
        if len(top_games) >= 2:
            _kelly_legs = []
            for g in top_games:
                bb = g.get("best_bet", {})
                _bb_odds = bb.get("odds", "-110")
                _kelly_legs.append({
                    "prob": min(0.65, 0.5 + g.get("best_edge", 0.05)),
                    "odds_american": _bb_odds,
                    "tier": bb.get("tier", ""),
                    "sport": g.get("Sport", g.get("sport", "")),
                    "matchup": g.get("matchup", ""),
                    "player": g.get("matchup", ""),
                    "prop": bb.get("type", ""),
                })
            _bankroll_games = st.session_state.get("bankroll", 100.0)
            _gk = correlated_parlay_kelly(_kelly_legs, _bankroll_games)
            g_combined = _gk.get("joint_prob_correlated", parlay_prob([l["prob"] for l in _kelly_legs]))
            g_ev = _gk.get("edge", 0.0)
            g_ev_color = "#378add" if g_ev > 0 else "#e04040"
            g_legs = ""
            for g in top_games:
                bb = g.get("best_bet",{})
                g_legs += f'<div style="background:var(--bc-bg-card);border-radius:5px;padding:0.5rem 0.7rem;margin-bottom:0.4rem;"><span style="color:var(--bc-blue);font-size:1.0rem;">{bb.get("type","")}</span> <span style="color:var(--bc-text);font-size:1.0rem;">{g.get("matchup","")} — {bb.get("pick","")}</span> <span style="color:var(--bc-dim);font-size:1.0rem;">({bb.get("edge_pct","")})</span></div>'
            _gk_warn_html = ""
            if _gk.get("warnings"):
                _gk_warn_html = "".join(f'<div style="font-size:0.85rem;color:#e8a020;margin-top:0.3rem;">{w}</div>' for w in _gk["warnings"][:2])
            st.html(f"""
            <div style="background:var(--bc-bg);border:1px solid var(--bc-border);border-radius:8px;padding:1.2rem;margin-bottom:1rem;">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.5rem;">
                    <span style="color:var(--bc-text);font-weight:700;">{len(top_games)}-Game Parlay</span>
                    <span style="color:{g_ev_color};font-weight:700;">{g_ev:+.1%} edge</span>
                </div>
                <div style="font-size:1.0rem;color:var(--bc-muted);margin-bottom:0.7rem;">Combined (correlation-adj): <span style="color:var(--bc-text);">{g_combined:.1%}</span> · Suggested wager: <span style="color:#22c55e;">${_gk.get("wager",0):.2f}</span> ({_gk.get("kelly_pct",0):.1%} bankroll)</div>
                {g_legs}
                {_gk_warn_html}
            </div>
            """)
        else:
            _game_analysis_count = len(game_analysis) if game_analysis else 0
            if _game_analysis_count > 0:
                st.markdown('<div style="background:var(--bc-bg);border:1px solid var(--bc-border);border-radius:6px;padding:0.7rem 1rem;color:var(--bc-dim);font-size:1.05rem;">⚠️ No game edges meet the 2% minimum today. All detected lines appear fairly priced.</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div style="color:var(--bc-dim);font-size:1.0rem;padding:0.5rem;">Load the board to see game parlays.</div>', unsafe_allow_html=True)

        # ── GAMES TO AVOID (always visible) ────────────────
        st.markdown('''<div style="display:flex;align-items:center;gap:0.75rem;margin:1rem 0 0.8rem;"><div style="flex:1;height:1px;background:var(--bc-bg2);"></div><span style="color:#e04040;font-size:1.0rem;text-transform:uppercase;letter-spacing:0.08em;">Games to Avoid</span><div style="flex:1;height:1px;background:var(--bc-bg2);"></div></div>''', unsafe_allow_html=True)
        avoid_games = [g for g in game_analysis if g.get("best_edge",0) < -0.05][:3]
        if avoid_games:
            _ag_html = []
            for ag in avoid_games:
                bb = ag.get("best_bet",{})
                _ag_reason = bb.get("note","") or "Model finds negative value — public is overloading this side"
                _ag_edge = ag.get("best_edge",0)
                _ag_html.append(f'<div style="background:var(--bc-bg-card);border-left:3px solid #e04040;border-radius:4px;padding:0.6rem 0.9rem;margin-bottom:0.4rem;"><div style="display:flex;align-items:center;justify-content:space-between;"><span style="color:var(--bc-text);font-weight:600;font-size:1.0rem;">{ag.get("matchup","")} — {bb.get("pick","FADE")}</span><span style="color:#e04040;font-weight:600;font-size:1.0rem;">AVOID {_ag_edge:+.1%}</span></div><div style="font-size:1.0rem;color:var(--bc-muted);margin-top:3px;">{_ag_reason[:90]}</div></div>')
            st.markdown("".join(_ag_html), unsafe_allow_html=True)
        else:
            st.markdown('<div style="background:var(--bc-bg);border:1px solid var(--bc-border);border-radius:6px;padding:0.6rem 0.9rem;color:var(--bc-dim);font-size:1.05rem;">✅ No strong game fades today — all detected edges are positive.</div>', unsafe_allow_html=True)

        # ── CONFIDENCE MATRIX ──────────────────────────────
        st.markdown('''<div style="display:flex;align-items:center;gap:0.75rem;margin:1rem 0 0.8rem;"><div style="flex:1;height:1px;background:var(--bc-bg2);"></div><span style="color:var(--bc-dim);font-size:1.0rem;text-transform:uppercase;letter-spacing:0.08em;">Master Slip Confidence Matrix</span><div style="flex:1;height:1px;background:var(--bc-bg2);"></div></div>''', unsafe_allow_html=True)
        if parlay_props:
            avg_edge = sum(p.get("Edge",0) for p in parlay_props)/len(parlay_props) if parlay_props else 0
            math_score = min(30, int(avg_edge * 200))
            corr_score = min(30, 25 - sum(1 for i in range(len(parlay_props)-1) for j in range(i+1,len(parlay_props)) if PLAYER_TEAM_MAP.get(parlay_props[i].get("Player","")) == PLAYER_TEAM_MAP.get(parlay_props[j].get("Player","")))*5)
            pinn_confirmed = sum(1 for p in parlay_props if p.get("PinnacleConfirms"))
            market_score = min(20, 14 + pinn_confirmed*2)
            vol_score = min(20, 15 + sum(1 for p in parlay_props if p.get("SEM","") not in ["Low","Very Low"])*(-2))
            total_score = math_score + corr_score + market_score + vol_score
            score_color = "#22c55e" if total_score >= 75 else "#e8a020" if total_score >= 55 else "#e04040"
            _mc = "#22c55e" if market_score >= 17 else "#e8a020"
            _vc = "#22c55e" if vol_score >= 17 else "#e8a020"
            st.html(f"""
            <div style="background:var(--bc-bg);border:1px solid #22c55e33;border-radius:8px;padding:1.5rem;margin-bottom:1rem;text-align:center;">
                <div style="font-size:2.8rem;font-weight:800;color:{score_color};">{total_score}<span style="font-size:1rem;color:#b8c6d6;">/100</span></div>
                <div style="color:var(--bc-muted);font-size:1.0rem;margin-bottom:1rem;">MASTER SLIP CONFIDENCE</div>
                <div style="display:flex;flex-direction:column;gap:0.5rem;text-align:left;">
                    <div style="display:flex;justify-content:space-between;background:var(--bc-bg-card);border-radius:5px;padding:0.5rem 0.8rem;"><span style="color:#b8c6d6;font-size:1.0rem;">Math Matrix <span style="color:var(--bc-dim);">(30%)</span></span><span style="color:#22c55e;font-weight:700;">{math_score}/30</span></div>
                    <div style="display:flex;justify-content:space-between;background:var(--bc-bg-card);border-radius:5px;padding:0.5rem 0.8rem;"><span style="color:#b8c6d6;font-size:1.0rem;">Correlation <span style="color:var(--bc-dim);">(30%)</span></span><span style="color:#22c55e;font-weight:700;">{corr_score}/30</span></div>
                    <div style="display:flex;justify-content:space-between;background:var(--bc-bg-card);border-radius:5px;padding:0.5rem 0.8rem;"><span style="color:#b8c6d6;font-size:1.0rem;">Market Drift <span style="color:var(--bc-dim);">(20%)</span></span><span style="color:{_mc};font-weight:700;">{market_score}/20</span></div>
                    <div style="display:flex;justify-content:space-between;background:var(--bc-bg-card);border-radius:5px;padding:0.5rem 0.8rem;"><span style="color:#b8c6d6;font-size:1.0rem;">Volatility Risk <span style="color:var(--bc-dim);">(20%)</span></span><span style="color:{_vc};font-weight:700;">{vol_score}/20</span></div>
                </div>
            </div>
            """)

        # ── BEST +EV PROPS ─────────────────────────────────
        st.markdown('''<div style="display:flex;align-items:center;gap:0.75rem;margin:1rem 0 0.8rem;"><div style="flex:1;height:1px;background:var(--bc-bg2);"></div><span style="color:var(--bc-dim);font-size:1.0rem;text-transform:uppercase;letter-spacing:0.08em;">Best +EV Props (2-pick, need 57.7%)</span><div style="flex:1;height:1px;background:var(--bc-bg2);"></div></div>''', unsafe_allow_html=True)
        # Dedup Best EV by player
        _seen_ev2 = set()
        plus_ev = []
        for _p2 in sorted(board, key=lambda x: x.get("Edge",0), reverse=True):
            if _p2.get("Edge",0) <= 0: continue
            _pk2 = normalize_name(_p2.get("Player",""))
            if _pk2 not in _seen_ev2:
                _seen_ev2.add(_pk2)
                plus_ev.append(_p2)
            if len(plus_ev) >= 6: break
        avoid = [p for p in sorted(board, key=lambda x: x.get("Edge",0)) if p.get("Edge",0) < -0.05][:3]
        ev_html = ""
        for bp in plus_ev:
            ev_html += f'<div style="background:var(--bc-bg-card);border-left:3px solid #22c55e;border-radius:4px;padding:0.5rem 0.8rem;margin-bottom:0.4rem;display:flex;align-items:center;flex-wrap:wrap;gap:0.4rem;"><span style="color:var(--bc-text);font-weight:600;font-size:1.0rem;">{bp.get("Player","")}</span><span style="color:#b8c6d6;font-size:1.0rem;">{bp.get("Side","")} {bp.get("Line","")} {bp.get("Prop","")}</span><span style="color:#7f77dd;font-size:1.0rem;">{bp.get("Tier","")}</span><span style="color:#22c55e;font-weight:700;font-size:1.0rem;margin-left:auto;">{bp.get("EdgePct","—")} · EV {bp.get("EV_2pick","—")}</span></div>'
        for ap in avoid:
            ev_html += f'<div style="background:var(--bc-bg-card);border-left:3px solid #e04040;border-radius:4px;padding:0.5rem 0.8rem;margin-bottom:0.4rem;display:flex;align-items:center;gap:0.4rem;"><span style="color:var(--bc-text);font-weight:600;font-size:1.0rem;">{ap.get("Player","")}</span><span style="color:#b8c6d6;font-size:1.0rem;">{ap.get("Side","")} {ap.get("Line","")} {ap.get("Prop","")}</span><span style="color:#e04040;font-weight:700;font-size:1.0rem;">⚠ AVOID</span><span style="color:#e04040;font-size:1.0rem;margin-left:auto;">{ap.get("EdgePct","—")}</span></div>'
        if ev_html:
            st.markdown(ev_html, unsafe_allow_html=True)
        else:
            st.markdown('<div style="color:var(--bc-dim);font-size:1.0rem;">Load the board to see +EV props.</div>', unsafe_allow_html=True)

        # Full Prop Board moved to Tab 1 (Full Board tab)
        st.markdown(
            '<div style="background:var(--bc-bg);border:1px solid var(--bc-border);border-radius:6px;padding:0.8rem 1rem;text-align:center;">' +
            '<span style="color:var(--bc-dim);font-size:1.05rem;">Full prop board is in the </span>' +
            '<span style="color:var(--bc-blue);font-weight:600;font-size:1.05rem;">📊 Full Board</span>' +
            '<span style="color:var(--bc-dim);font-size:1.05rem;"> tab → Click a 🔒 to lock picks</span>' +
            '</div>',
            unsafe_allow_html=True
        )


        st.markdown('''<div style="display:flex;align-items:center;gap:0.75rem;margin:1rem 0 0.8rem;"><div style="flex:1;height:1px;background:var(--bc-bg2);"></div><span style="color:var(--bc-dim);font-size:1.0rem;text-transform:uppercase;letter-spacing:0.08em;">Daily Risk Status</span><div style="flex:1;height:1px;background:var(--bc-bg2);"></div></div>''', unsafe_allow_html=True)
        same_team_count = 0
        players = [p.get("Player","") for p in parlay_props]
        for i in range(len(players)):
            for j in range(i+1, len(players)):
                if PLAYER_TEAM_MAP.get(players[i]) and PLAYER_TEAM_MAP.get(players[i]) == PLAYER_TEAM_MAP.get(players[j]):
                    same_team_count += 1
        risk_color = "#e04040" if same_team_count >= 2 else "#e8a020" if same_team_count == 1 else "#22c55e"
        risk_label = "HIGH RISK" if same_team_count >= 2 else "MODERATE RISK" if same_team_count == 1 else "LOW RISK"
        risk_note = f"{same_team_count} same-team leg(s) detected — blowout risk elevated." if same_team_count else "No same-team concentration. Standard Kelly sizing recommended."
        st.markdown(f'<div style="background:{risk_color}11;border:1px solid {risk_color}33;border-radius:8px;padding:1rem;margin-bottom:0.5rem;"><div style="color:{risk_color};font-weight:700;font-size:1.0rem;margin-bottom:0.4rem;">⚠ {risk_label}</div><p style="color:#b8c6d6;font-size:1.0rem;margin:0;">{risk_note}</p></div>', unsafe_allow_html=True)

        # ── MASTER DAILY SLIP ──────────────────────────────
        st.markdown('''<div style="display:flex;align-items:center;gap:0.75rem;margin:1rem 0 0.8rem;"><div style="flex:1;height:1px;background:var(--bc-bg2);"></div><span style="color:var(--bc-dim);font-size:1.0rem;text-transform:uppercase;letter-spacing:0.08em;">Master Daily Slip</span><div style="flex:1;height:1px;background:var(--bc-bg2);"></div></div>''', unsafe_allow_html=True)
        # Dedup slip_picks by player
        _seen_sk = set()
        _slip_src = parlay_props if parlay_props else sorted(board, key=lambda x: x.get("Edge",0), reverse=True)
        slip_picks = []
        for _skp in _slip_src:
            _skk = normalize_name(_skp.get("Player",""))
            if _skk not in _seen_sk:
                _seen_sk.add(_skk)
                slip_picks.append(_skp)
            if len(slip_picks) >= 8: break
        if slip_picks:
            unit = active_unit()
            payout = unit * PRIZEPICKS_MULTIPLIERS.get(len(slip_picks), 3)
            slip_html = '<div style="background:var(--bc-bg);border:1px solid #22c55e33;border-radius:8px;padding:1.2rem;margin-bottom:1rem;">'
            slip_html += f'<div style="color:var(--bc-muted);font-size:1.0rem;margin-bottom:0.7rem;">Props (PrizePicks) — {len(slip_picks)}-pick Flex · ${unit:.0f} entry to pay ${payout:.0f}</div>'
            for i, sp in enumerate(slip_picks):
                slip_html += f'<div style="display:flex;align-items:center;gap:0.5rem;padding:0.4rem 0;border-bottom:1px solid #1e2d3d;"><span style="color:#22c55e;font-weight:700;min-width:16px;">{i+1}.</span><span style="color:var(--bc-text);font-size:1.0rem;">{sp.get("Player","")} {sp.get("Side","")} {sp.get("Line","")} {sp.get("Prop","")}</span><span style="color:var(--bc-dim);font-size:1.0rem;margin-left:auto;">{sp.get("Tier","")}</span></div>'
            slip_html += '<div style="display:flex;justify-content:space-between;margin-top:0.8rem;"><span style="color:#b8c6d6;font-size:1.0rem;">Entry: <span style="color:var(--bc-text);">${:.0f}</span></span><span style="color:#22c55e;font-weight:700;">Payout: ${:.0f}</span></div>'.format(unit, payout)
            slip_html += '</div>'
            st.markdown(slip_html, unsafe_allow_html=True)

        # ── ALT LINE UPGRADES ──────────────────────────────
        st.markdown('''<div style="display:flex;align-items:center;gap:0.75rem;margin:1rem 0 0.8rem;"><div style="flex:1;height:1px;background:var(--bc-bg2);"></div><span style="color:var(--bc-dim);font-size:1.0rem;text-transform:uppercase;letter-spacing:0.08em;">Alt Line Upgrades</span><div style="flex:1;height:1px;background:var(--bc-bg2);"></div></div>''', unsafe_allow_html=True)
        alt_upgrades = st.session_state.get("alt_line_upgrades", [])
        if alt_upgrades:
            _au_html = []
            for au in alt_upgrades[:5]:
                _au_html.append(f'<div style="background:var(--bc-bg-card);border-left:3px solid #7f77dd;border-radius:4px;padding:0.5rem 0.8rem;margin-bottom:0.4rem;"><span style="color:var(--bc-text);font-weight:600;font-size:1.0rem;">{au.get("Player","")}</span> <span style="color:#b8c6d6;font-size:1.0rem;">{au.get("Side","")} {au.get("AltLine","")} {au.get("Prop","")}</span> <span style="color:#7f77dd;font-size:1.0rem;">Alt EV: {au.get("AltEV","—")}</span></div>')
            st.markdown("".join(_au_html), unsafe_allow_html=True)
        else:
            st.markdown('<div style="color:var(--bc-muted);font-size:1.05rem;padding:0.3rem 0;">Load board to check for alt line upgrades.</div>', unsafe_allow_html=True)
        _alt_ups = st.session_state.get("alt_line_upgrades", [])
        if _alt_ups:
            _au2_html = []
            for _au in _alt_ups[:5]:
                _au2_html.append(f'<div style="background:var(--bc-bg-card);border-left:3px solid #22c55e;border-radius:4px;padding:0.5rem 0.8rem;margin-bottom:0.4rem;"><div style="display:flex;justify-content:space-between;"><span style="color:var(--bc-text);font-weight:600;">{_au.get("player","")}</span><span style="color:#22c55e;">⚡ {_au.get("edge_gain","")}</span></div><div style="font-size:1.0rem;color:var(--bc-muted);">{_au.get("current_line","")} → {_au.get("better_line","")} on {_au.get("source","")}</div></div>')
            st.markdown("".join(_au2_html), unsafe_allow_html=True)
        else:
            st.markdown('<div style="color:var(--bc-dim);font-size:1.0rem;">✅ All lines optimal — no upgrades today.</div>', unsafe_allow_html=True)

        # ── ARBITRAGE OPPORTUNITIES ────────────────────────
        st.markdown('''<div style="display:flex;align-items:center;gap:0.75rem;margin:1rem 0 0.8rem;"><div style="flex:1;height:1px;background:var(--bc-bg2);"></div><span style="color:var(--bc-dim);font-size:1.0rem;text-transform:uppercase;letter-spacing:0.08em;">Arbitrage Opportunities</span><div style="flex:1;height:1px;background:var(--bc-bg2);"></div></div>''', unsafe_allow_html=True)
        arb_opps = st.session_state.get("arb_opportunities", [])
        if arb_opps:
            _arb_html = []
            for arb in arb_opps[:5]:
                _arb_html.append(f'<div style="background:var(--bc-bg-card);border-left:3px solid #22c55e;border-radius:4px;padding:0.5rem 0.8rem;margin-bottom:0.4rem;"><span style="color:var(--bc-text);font-weight:600;font-size:1.0rem;">{arb.get("Player","")}</span> <span style="color:#b8c6d6;font-size:1.0rem;">{arb.get("Prop","")}</span> <span style="color:#22c55e;font-size:1.0rem;">ROI: {arb.get("ROI","—")}</span></div>')
            st.markdown("".join(_arb_html), unsafe_allow_html=True)
        else:
            st.markdown('<div style="color:var(--bc-muted);font-size:1.05rem;padding:0.3rem 0;">Load board to scan for arbitrage opportunities.</div>', unsafe_allow_html=True)
        _arb_opps = st.session_state.get("arb_opportunities", [])
        if _arb_opps:
            _arb2_html = []
            for _arb in _arb_opps[:5]:
                _profit = float(_arb.get("Arb Pct", 0) or 0)
                _arb2_html.append(f'<div style="background:var(--bc-bg-card);border-left:3px solid #22c55e;border-radius:4px;padding:0.5rem 0.8rem;margin-bottom:0.4rem;"><div style="display:flex;justify-content:space-between;"><span style="color:var(--bc-text);font-weight:600;">{_arb.get("Player","")}</span><span style="color:#22c55e;font-weight:700;">+{_profit:.1f}%</span></div><div style="font-size:1.0rem;color:var(--bc-muted);">{_arb.get("Book1","")} {_arb.get("Line1","")} vs {_arb.get("Book2","")} {_arb.get("Line2","")}</div></div>')
            st.markdown("".join(_arb2_html), unsafe_allow_html=True)
        else:
            st.markdown('<div style="color:var(--bc-dim);font-size:1.0rem;">No arbitrage opportunities found today.</div>', unsafe_allow_html=True)

        # ── SIGNAL ODDS ARBITRAGE (cross-book, real bookmaker legs) ──────
        # Game-level (not per-player) -- separate section since it's a
        # different shape than the player-prop arb blocks above.
        st.markdown('''<div style="display:flex;align-items:center;gap:0.75rem;margin:1rem 0 0.8rem;"><div style="flex:1;height:1px;background:var(--bc-bg2);"></div><span style="color:var(--bc-dim);font-size:1.0rem;text-transform:uppercase;letter-spacing:0.08em;">Signal Odds — Cross-Book Arbitrage</span><div style="flex:1;height:1px;background:var(--bc-bg2);"></div></div>''', unsafe_allow_html=True)
        _so_arb = [a for a in st.session_state.get("signalodds_arbitrage", []) if not a.get("locked")]
        if _so_arb:
            _so_arb_html = []
            for a in sorted(_so_arb, key=lambda x: float(x.get("margin_percent") or 0), reverse=True)[:5]:
                _matchup = f'{a.get("away_team","")} @ {a.get("home_team","")}'
                _legs = a.get("legs") or []
                _legs_str = " vs ".join(
                    f'{l.get("bookmaker","")} {l.get("outcome","")} ({l.get("odds","")})' for l in _legs
                )
                _margin = float(a.get("margin_percent") or 0)
                _so_arb_html.append(f'<div style="background:var(--bc-bg-card);border-left:3px solid #22c55e;border-radius:4px;padding:0.5rem 0.8rem;margin-bottom:0.4rem;"><div style="display:flex;justify-content:space-between;"><span style="color:var(--bc-text);font-weight:600;font-size:1.0rem;">{_matchup}</span><span style="color:#22c55e;font-weight:700;">+{_margin:.2f}%</span></div><div style="font-size:0.95rem;color:var(--bc-muted);">{a.get("market_name","")} — {_legs_str}</div></div>')
            st.markdown("".join(_so_arb_html), unsafe_allow_html=True)
        else:
            st.markdown('<div style="color:var(--bc-dim);font-size:1.0rem;">No Signal Odds arbitrage opportunities found today.</div>', unsafe_allow_html=True)

        # ── KALSHI — PREDICTION MARKET PRICES ─────────────────
        # Real bid/ask from Kalshi's own public order book (yes-price ~=
        # market-implied probability). Top markets per event by volume,
        # not the full stacked-totals distribution -- that's available in
        # the raw data (fetch_kalshi_from_gist) for a future deeper view.
        st.markdown('''<div style="display:flex;align-items:center;gap:0.75rem;margin:1rem 0 0.8rem;"><div style="flex:1;height:1px;background:var(--bc-bg2);"></div><span style="color:var(--bc-dim);font-size:1.0rem;text-transform:uppercase;letter-spacing:0.08em;">Kalshi — Prediction Market Prices</span><div style="flex:1;height:1px;background:var(--bc-bg2);"></div></div>''', unsafe_allow_html=True)
        _kalshi_events = st.session_state.get("kalshi_events_scraped", [])
        if _kalshi_events:
            _kalshi_by_sport = {}
            for _kev in _kalshi_events:
                _kalshi_by_sport.setdefault(_kev.get("sport", "?"), []).append(_kev)
            _kalshi_html = []
            for _ksport in sorted(_kalshi_by_sport.keys()):
                _kevs = _kalshi_by_sport[_ksport]
                def _kev_volume(ev):
                    tot = 0.0
                    for m in ev.get("markets", []):
                        try:
                            tot += float(m.get("volume") or 0)
                        except (TypeError, ValueError):
                            pass
                    return tot
                _top_kevs = sorted(_kevs, key=_kev_volume, reverse=True)[:5]
                _kalshi_html.append(f'<div style="color:var(--bc-muted);font-size:0.9rem;text-transform:uppercase;margin:0.6rem 0 0.3rem;">{_ksport}</div>')
                for _kev in _top_kevs:
                    _kmarkets = _kev.get("markets") or []
                    if not _kmarkets:
                        continue
                    _krows = []
                    for m in sorted(_kmarkets, key=lambda x: float(x.get("volume") or 0), reverse=True)[:3]:
                        try:
                            _bid = float(m.get("yes_bid") or 0)
                            _ask = float(m.get("yes_ask") or 0)
                            _mid = (_bid + _ask) / 2 if (_bid or _ask) else float(m.get("last_price") or 0)
                        except (TypeError, ValueError):
                            _mid = 0
                        # Kalshi's own "title" field is identical across every
                        # team-specific market in an event (e.g. both markets
                        # under "Cleveland vs Tampa Bay Winner?" share that
                        # exact title) -- confirmed against real captured
                        # data. The actual team this specific market resolves
                        # on is only stated in rules_primary ("If Cleveland
                        # wins..."), so pull it from there instead of
                        # re-displaying the shared, team-less title.
                        _k_team_m = re.search(r"If (.+?) wins", m.get("rules_primary", "") or "")
                        _k_label = _k_team_m.group(1) if _k_team_m else m.get("title", "")
                        _krows.append(f'{_k_label}: {_mid*100:.0f}%')
                    _krows_str = " · ".join(_krows)
                    _kalshi_html.append(f'<div style="background:var(--bc-bg-card);border-left:3px solid #6366f1;border-radius:4px;padding:0.5rem 0.8rem;margin-bottom:0.4rem;"><div style="color:var(--bc-text);font-weight:600;font-size:1.0rem;">{_kev.get("title","")}</div><div style="font-size:0.9rem;color:var(--bc-muted);">{_krows_str}</div></div>')
            st.markdown("".join(_kalshi_html), unsafe_allow_html=True)
        else:
            st.markdown('<div style="color:var(--bc-dim);font-size:1.0rem;">No Kalshi market data available.</div>', unsafe_allow_html=True)

        # ── BEST OF ALL SPORTS ─────────────────────────────
        st.markdown('''<div style="display:flex;align-items:center;gap:0.75rem;margin:1rem 0 0.8rem;"><div style="flex:1;height:1px;background:var(--bc-bg2);"></div><span style="color:var(--bc-dim);font-size:1.0rem;text-transform:uppercase;letter-spacing:0.08em;">Best of All Sports</span><div style="flex:1;height:1px;background:var(--bc-bg2);"></div></div>''', unsafe_allow_html=True)
        all_sports_best = [p for p in st.session_state.get("all_sports_best", [])
                           if p.get("Player","") not in ("","Unknown Player")
                           and float(p.get("Line",0) or 0) < 100
                           and float(p.get("Avg",0) or 0) > 0]
        if all_sports_best:
            _asb_html = []
            for ap in all_sports_best[:5]:
                tier_c = TIER_COLORS.get(ap.get("Tier",""), "#6a7a8a")
                _asb_html.append(f'<div style="background:var(--bc-bg-card);border-left:3px solid {tier_c};border-radius:4px;padding:0.5rem 0.8rem;margin-bottom:0.4rem;"><span style="color:{tier_c};font-size:1.15rem;font-weight:700;">{ap.get("Sport","")}</span> <span style="color:var(--bc-text);font-weight:600;font-size:1.0rem;margin-left:0.5rem;">{ap.get("Player","")}</span> <span style="color:#b8c6d6;font-size:1.0rem;">{ap.get("Side","")} {ap.get("Line","")} {ap.get("Prop","")}</span> <span style="color:{tier_c};font-size:1.0rem;margin-left:0.5rem;">{ap.get("EdgePct","—")}</span></div>')
            st.markdown("".join(_asb_html), unsafe_allow_html=True)
        else:
            st.markdown('<div style="color:var(--bc-muted);font-size:1.05rem;padding:0.3rem 0;">Load boards across sports to see the best plays of the day.</div>', unsafe_allow_html=True)

        # ── TRENDING PICKS ─────────────────────────────────
        st.markdown('''<div style="display:flex;align-items:center;gap:0.75rem;margin:1rem 0 0.8rem;"><div style="flex:1;height:1px;background:var(--bc-bg2);"></div><span style="color:var(--bc-dim);font-size:1.0rem;text-transform:uppercase;letter-spacing:0.08em;">Trending Picks (Last 7 Days)</span><div style="flex:1;height:1px;background:var(--bc-bg2);"></div></div>''', unsafe_allow_html=True)
        all_history = st.session_state.get("history", [])
        if all_history:
            cutoff = datetime.now() - timedelta(days=7)
            recent_picks = [h for h in all_history if h.get("timestamp","") >= cutoff.strftime("%Y-%m-%d")]
            if recent_picks:
                # Count frequency and win rate per prop
                prop_stats = {}
                for h in recent_picks:
                    _pl = h.get('player','')
                    try:
                        _li = float(h.get('line',0) or 0)
                    except (ValueError, TypeError):
                        _li = 0.0
                    if not _pl or _pl == "Unknown Player" or _li > 100:
                        continue
                    key = f"{_pl} {h.get('side','')} {_li} {h.get('prop','')}"
                    if key not in prop_stats:
                        prop_stats[key] = {"count": 0, "wins": 0, "tier": h.get("tier",""), "player": h.get("player",""), "prop": h.get("prop",""), "line": h.get("line",""), "side": h.get("side","")}
                    prop_stats[key]["count"] += 1
                    if h.get("outcome") == "WIN":
                        prop_stats[key]["wins"] += 1
                # Sort by frequency
                trending = sorted(prop_stats.values(), key=lambda x: x["count"], reverse=True)[:5]
                trend_html = ""
                for t in trending:
                    hit_rate = t["wins"] / t["count"] if t["count"] > 0 else 0
                    hit_color = "#22c55e" if hit_rate >= 0.6 else "#e8a020" if hit_rate >= 0.4 else "#e04040"
                    tier_c = TIER_COLORS.get(t["tier"], "#6a7a8a")
                    trend_html += f'<div style="background:var(--bc-bg-card);border-left:3px solid {tier_c};border-radius:4px;padding:0.5rem 0.8rem;margin-bottom:0.4rem;display:flex;align-items:center;justify-content:space-between;"><div><span style="color:var(--bc-text);font-weight:600;font-size:1.0rem;">{t["player"]}</span> <span style="color:#b8c6d6;font-size:1.0rem;">{t["side"]} {t["line"]} {t["prop"]}</span></div><div style="text-align:right;"><span style="color:{hit_color};font-weight:600;font-size:1.0rem;">{hit_rate:.0%} ({t["wins"]}/{t["count"]})</span> <span style="color:var(--bc-dim);font-size:1.0rem;margin-left:6px;">{t["count"]}x locked</span></div></div>'
                st.markdown(trend_html, unsafe_allow_html=True)
            else:
                st.markdown('<div style="color:var(--bc-dim);font-size:1.05rem;">No picks in the last 7 days. Start locking picks to see trends.</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div style="color:var(--bc-dim);font-size:1.05rem;">Lock picks to start tracking trends.</div>', unsafe_allow_html=True)

    with col_right:
        st.markdown('<div style="color:var(--bc-dim);font-size:1.0rem;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:0.8rem;font-weight:700;">Sharp Money Alerts</div>', unsafe_allow_html=True)
        sharp_data = st.session_state.get("sharp_alerts", [])
        steam_moves = st.session_state.get("steam_moves", [])
        game_sharp_flags = st.session_state.get("game_sharp_flags", {})
        displayed = 0

        # ── EV Movement alerts (highest priority — real sharp book data) ──
        for alert_str in sharp_data[:5]:
            parts = alert_str.split(" | ")
            title = parts[0] if parts else alert_str
            detail = " | ".join(parts[1:]) if len(parts) > 1 else ""
            is_steam = "STEAM" in alert_str
            is_rlm   = "RLM" in alert_str
            color = "#e04040" if is_steam else ("#e8a020" if is_rlm else "#22c55e")
            label = "STEAM MOVE" if is_steam else ("REVERSE LINE" if is_rlm else "SHARP MOVE")
            st.markdown(
                f'<div style="background:var(--bc-bg-card);border:1px solid {color}44;border-radius:6px;padding:0.7rem;margin-bottom:0.5rem;">'
                f'<div style="color:{color};font-weight:700;font-size:0.85rem;text-transform:uppercase;margin-bottom:0.25rem;">⚡ {label} [EV API]</div>'
                f'<div style="color:#b8c6d6;font-size:1.0rem;line-height:1.4;">{title}</div>'
                + (f'<div style="color:var(--bc-muted);font-size:0.85rem;margin-top:0.2rem;">{detail}</div>' if detail else '')
                + '</div>',
                unsafe_allow_html=True
            )
            displayed += 1

        # Sharp prop alerts from board SharpFlag
        for p in sorted(board, key=lambda x: x.get("Edge",0), reverse=True)[:20]:
            if p.get("SharpFlag") and displayed < 5:
                st.markdown(f'<div style="background:var(--bc-bg-card);border:1px solid var(--bc-border);border-radius:6px;padding:0.7rem;margin-bottom:0.5rem;"><div style="color:#22c55e;font-weight:700;font-size:1.0rem;text-transform:uppercase;margin-bottom:0.25rem;">Line Update</div><div style="color:#b8c6d6;font-size:1.0rem;line-height:1.4;">{p.get("Player","")} {p.get("Prop","")} — {p.get("SharpFlag","")}</div></div>', unsafe_allow_html=True)
                displayed += 1
        # Steam moves
        for sm in steam_moves[:3]:
            if displayed < 7:
                st.markdown(f'<div style="background:var(--bc-bg-card);border:1px solid var(--bc-border);border-radius:6px;padding:0.7rem;margin-bottom:0.5rem;"><div style="color:#e04040;font-weight:700;font-size:1.0rem;text-transform:uppercase;margin-bottom:0.25rem;">Steam Move</div><div style="color:#b8c6d6;font-size:1.0rem;line-height:1.4;">{sm.get("matchup","")} {sm.get("market","")} {sm.get("signal","")}</div></div>', unsafe_allow_html=True)
                displayed += 1
        # Game sharp flags
        for matchup, flag in list(game_sharp_flags.items())[:3]:
            if displayed < 8:
                label = "Line Move" if flag.get("sharp") else "Public vs Sharp"
                color = "#e8a020" if flag.get("sharp") else "#378add"
                direction = flag.get("direction","")
                st.markdown(f'<div style="background:var(--bc-bg-card);border:1px solid var(--bc-border);border-radius:6px;padding:0.7rem;margin-bottom:0.5rem;"><div style="color:{color};font-weight:700;font-size:1.0rem;text-transform:uppercase;margin-bottom:0.25rem;">{label}</div><div style="color:#b8c6d6;font-size:1.0rem;line-height:1.4;">{matchup} — {direction}</div></div>', unsafe_allow_html=True)
                displayed += 1
        # Injury alerts in sidebar
        for ip in injury_props[:3]:
            if displayed < 10:
                st.markdown(f'<div style="background:var(--bc-bg-card);border:1px solid var(--bc-border);border-radius:6px;padding:0.7rem;margin-bottom:0.5rem;"><div style="color:#e8a020;font-weight:700;font-size:1.0rem;text-transform:uppercase;margin-bottom:0.25rem;">Injury Alert</div><div style="color:#b8c6d6;font-size:1.0rem;line-height:1.4;">{ip.get("Player","")} — {ip.get("Injury","Questionable")}</div></div>', unsafe_allow_html=True)
                displayed += 1
        if displayed == 0:
            _jwt_configured = bool(_get_ev_jwt())
            _no_alert_msg = "No alerts — load board to scan for sharp activity." if _jwt_configured else "No alerts — add EV_JWT to Streamlit secrets to enable sharp movement data."
            st.markdown(f'<div style="color:var(--bc-dim);font-size:1.0rem;padding:0.5rem;">{_no_alert_msg}</div>', unsafe_allow_html=True)


# ----- TAB 1: EV OPTIMIZER (DFF-style) -----
with tabs[4]:
    _board  = st.session_state.get("board_data", []) or []
    _sport  = st.session_state.get("last_sport", SPORTS[0]) or "NBA"
    _kalshi = st.session_state.get("kalshi_markets", [])
    _poly   = st.session_state.get("polymarket_markets", [])
    _covers = st.session_state.get("covers_consensus", [])

    st.markdown(f'<div class="bc-section-header">📊 EV Optimizer <span style="opacity:0.6;font-weight:400;">— {_sport}</span></div>', unsafe_allow_html=True)

    if not _board:
        st.markdown(empty_state_html("📊", "No board loaded yet",
                                      "Pick a sport and load the board to populate the EV Optimizer."),
                    unsafe_allow_html=True)
    else:
        # ── Filter bar (sticky while scrolling the board below) ──
        with st.container(key="ev_sticky_filters"):
            _fc1, _fc2, _fc3, _fc4, _fc5, _fc6 = st.columns([3,2,2,2,2,1.3])
            with _fc1:
                _search = st.text_input("🔍 Search player", "", key="ev_search", placeholder="e.g. LeBron, Strider...")
            with _fc2:
                _tier_f = st.multiselect("Tier", ["SOVEREIGN","ELITE","APPROVED","LEAN"],
                                          default=["SOVEREIGN","ELITE","APPROVED"], key="ev_tier")
            with _fc3:
                _all_props = sorted(set(p.get("Prop","") for p in _board if p.get("Prop","")))
                _prop_f = st.multiselect("Prop type", _all_props, key="ev_prop")
            with _fc4:
                _min_edge = st.number_input("Min edge %", min_value=0.0, max_value=20.0,
                                             value=0.0, step=0.5, key="ev_min_edge")
            with _fc5:
                _sort_col = st.selectbox("Sort by", ["BQ Score","Edge %","L5 Hit %","Line","Reliability"], key="ev_sort")
            with _fc6:
                # Display-only density toggle -- same data, tighter padding
                # and smaller font, not a separate feature mode. Whales can
                # fit more rows on screen; new bettors can ignore it.
                _density = st.selectbox("Density", ["Standard", "Dense"], key="ev_density")
            _view_mode = st.radio("View", ["Table", "Cards"], index=0, horizontal=True, key="ev_view_mode")

        st.html(
            '<div class="heatmap-legend" title="Background intensity on the Edge % column scales with edge size, '
            'from 0% up to 15%+ -- purely visual, doesn\'t change the underlying number.">'
            '<span class="heatmap-legend-title">Edge Confidence</span>'
            '<span class="heatmap-legend-row"><span class="heatmap-legend-swatch"></span>'
            '<span>Low → High</span></span>'
            '</div>'
        )

        _unab_only = st.checkbox(
            "⚡ Unabated disagreement only (≥5pt gap between GEM and Unabated's real devigged price)",
            value=False, key="ev_unabated_flag_only",
        )

        # ── Build rows ──────────────────────────────────────────
        _rows = []
        for _p in _board:
            if _p.get("Tier","") not in (_tier_f or ["SOVEREIGN","ELITE","APPROVED","LEAN"]):
                continue
            _edge_pct = round(float(_p.get("Edge",0) or 0) * 100, 1)
            if _edge_pct < _min_edge:
                continue
            _player = _p.get("Player","")
            if _search and normalize_name(_search) not in normalize_name(_player):
                continue
            if _prop_f and _p.get("Prop","") not in _prop_f:
                continue
            if _unab_only and not _p.get("UnabatedFlag"):
                continue

            # L5 / L10 / Season hit rates
            _l5  = _p.get("L5","")
            _l10 = _p.get("L10","")
            _szn = _p.get("Season","")

            # Book odds
            _pinn = _p.get("PinnacleOdds","")
            _dk   = _p.get("DKOdds","")
            _fd   = _p.get("FDOdds","")

            # Market intelligence
            _model_prob  = round(float(_p.get("Prob",0.5) or 0.5) * 100, 1)
            _mkt_signal  = ""
            _kalshi_prob = ""
            _poly_prob   = ""

            _pname_lower = normalize_name(_player)
            _pname_tokens = set(_pname_lower.split())
            _kalshi_matches = []
            for _km in _kalshi:
                _kt = set(normalize_name(_km.get("event","")).split())
                if len(_pname_tokens) >= 2 and _pname_tokens.issubset(_kt):
                    _kalshi_matches.append(_km)
            if _kalshi_matches:
                _kalshi_prob = f"{_kalshi_matches[0]['implied_prob']:.0%}"
            _poly_matches = []
            for _pm in _poly:
                _qt = set(normalize_name(_pm.get("question","")).split())
                if len(_pname_tokens) >= 2 and _pname_tokens.issubset(_qt):
                    _poly_matches.append(_pm)
            if _poly_matches:
                _poly_prob = f"{_poly_matches[0]['implied_prob']:.0%}"

            _market_vals = [float(_km["implied_prob"]) for _km in _kalshi_matches]
            _market_vals += [float(_pm["implied_prob"]) for _pm in _poly_matches]
            if _market_vals:
                _mkt_avg = sum(_market_vals) / len(_market_vals)
                _div = _model_prob/100 - _mkt_avg
                if _div >= 0.08:
                    _mkt_signal = "📈 MODEL+"
                elif _div <= -0.08:
                    _mkt_signal = "📉 MKT+"
                else:
                    _mkt_signal = "✅ AGREE"

            # Public betting from Covers
            _pub_pct = ""
            if isinstance(_covers, dict):
                for _cdm, _cd_val in _covers.items():
                    _cdm_l = _cdm.lower()
                    if any(t in _cdm_l for t in [_p.get("Team","").lower()[:4]] if t):
                        _away_pct = _cd_val.get("away_pct", 50)
                        _home_pct = _cd_val.get("home_pct", 50)
                        _pub_pct = f"{max(_away_pct, _home_pct)}%"
                        break

            # Reliability from FantasyLabs
            _fl_data = st.session_state.get("fantasylabs_lineups",{})
            _fl      = _fl_data.get(_pname_lower, {})
            _rel     = ""
            if _fl:
                _rel_score = sum([
                    1 if _fl.get("in_lineup") else 0,
                    1 if _fl.get("active") else 0,
                    1 if _fl.get("injury_status","").lower() in ("active","","healthy") else 0,
                    1 if _fl.get("lineup_order",0) > 0 and _fl.get("lineup_order",0) <= 4 else 0,
                ])
                _rel = f"{_rel_score}/4"

            # ── Bet Quality Score (A+ to D) ─────────────────────
            # Incorporates: edge, alignment, agreement, volatility, CLV
            _conflict   = _p.get("ConflictStatus","")
            _mkt_agree  = int(_p.get("MarketAgreement", 50) or 50)
            _risk_lvl   = _p.get("RiskLevel","")
            _clv_data   = load_json_data(CLV_PATH, [])
            _clv_beat   = 0.5  # default
            if _clv_data:
                _player_clv = [c for c in _clv_data
                               if normalize_name(c.get("player","")) == normalize_name(_player)]
                if len(_player_clv) >= 3:
                    _clv_beat = sum(1 for c in _player_clv
                                    if c.get("clv",0) > 0) / len(_player_clv)

            # Score 0-100 across 5 factors
            _bq = 0
            # Edge (40 pts)
            _bq += min(40, _edge_pct * 4)
            # Alignment (20 pts)
            if _conflict == "ALIGNED":      _bq += 20
            elif _conflict == "MIXED":      _bq += 10
            elif _conflict == "CONFLICTED": _bq += 0
            else:                           _bq += 12  # unknown = neutral
            # Market agreement (20 pts)
            _bq += int(_mkt_agree * 0.20)
            # Volatility (10 pts)
            if _risk_lvl == "LOW":          _bq += 10
            elif _risk_lvl == "MEDIUM":     _bq += 7
            elif _risk_lvl == "HIGH":       _bq += 3
            elif _risk_lvl == "EXTREME":    _bq += 0
            else:                           _bq += 5  # unknown
            # CLV history (10 pts)
            _bq += int(_clv_beat * 10)

            _bq = max(0, min(100, int(_bq)))

            # Grade mapping
            if _bq >= 85 and _conflict == "ALIGNED":
                _grade, _grade_color = "A+", "#22c55e"
            elif _bq >= 75:
                _grade, _grade_color = "A",  "#22c55e"
            elif _bq >= 65:
                _grade, _grade_color = "B+", "#4ade80"
            elif _bq >= 55:
                _grade, _grade_color = "B",  "#e8a020"
            elif _bq >= 40:
                _grade, _grade_color = "C",  "#e8a020"
            elif _conflict == "CONFLICTED":
                _grade, _grade_color = "C",  "#e04040"
            else:
                _grade, _grade_color = "D",  "#6a7a8a"

            # Row background — based on quality score not just edge
            if _bq >= 85:
                _row_bg = "rgba(34,197,94,0.12)"
            elif _bq >= 70:
                _row_bg = "rgba(34,197,94,0.06)"
            elif _bq >= 55:
                _row_bg = "rgba(232,160,32,0.06)"
            elif _conflict == "CONFLICTED":
                _row_bg = "rgba(224,64,64,0.04)"
            else:
                _row_bg = "transparent"

            _rows.append({
                "_player":     _player,
                "_team":       _p.get("Team",""),
                "_prop":       _p.get("Prop",""),
                "_line":       _p.get("Line",""),
                "_side":       _p.get("Side","OVER"),
                "_tier":       _p.get("Tier",""),
                "_edge_pct":   _edge_pct,
                "_grade":      _grade,
                "_grade_color":_grade_color,
                "_row_bg":     _row_bg,
                "_model_prob": _model_prob,
                "_kalshi":     _kalshi_prob,
                "_poly":       _poly_prob,
                "_mkt_signal": _mkt_signal,
                "_unabated": (
                    ("📈 MODEL+" if _p.get("UnabatedDirection") == "model_higher" else "📉 MKT+")
                    if _p.get("UnabatedFlag") else ("✅ AGREE" if _p.get("UnabatedFairProb") is not None else "")
                ),
                "_pub_pct":    _pub_pct,
                "_pinn":       str(_pinn) if _pinn else "—",
                "_dk":         str(_dk)   if _dk   else "—",
                "_fd":         str(_fd)   if _fd   else "—",
                "_l5":         str(_l5)   if _l5   else "—",
                "_l10":        str(_l10)  if _l10  else "—",
                "_szn":        str(_szn)  if _szn  else "—",
                "_rel":        _rel or "—",
                "_source":     _p.get("Source",""),
                "_risk":       _p.get("RiskLevel",""),
                "_p":          _p,   # full prop dict for edge type badge and other display
                "_mmq":        _p.get("MarketMoveQuality",0),
                "_mins_stab":  _p.get("MinutesStability",""),
                "_bq_score":   _bq,
                "_conflict":   _conflict,
                "_ev_sharp":   _p.get("EVSharpEV"),
                "_ev_books":   _p.get("EVSharpBooks", 0),
                "_ev_link":    _p.get("EVSharpLink", ""),
                "_better":     _p.get("BetterLineNote", ""),
            })

        # Sort
        _sort_map = {
            "BQ Score":    ("_bq_score",   True),
            "Edge %":      ("_edge_pct",   True),
            "L5 Hit %":    ("_l5",         True),
            "Line":        ("_line",        False),
            "Reliability": ("_rel",         True),
        }
        _sk, _sr = _sort_map.get(_sort_col, ("_edge_pct", True))
        try:
            _rows.sort(key=lambda x: float(str(x.get(_sk,"0")).replace("%","").replace("—","0") or 0), reverse=_sr)
        except (ValueError, TypeError, ZeroDivisionError):
            _rows.sort(key=lambda x: str(x.get(_sk,"")), reverse=_sr)

        # Group by tier (SOVEREIGN -> ELITE -> APPROVED -> LEAN) while
        # preserving the chosen sort order within each tier -- Python's
        # sort() is stable, so sorting again by tier rank alone keeps the
        # existing order intact inside each group. Pure visual grouping,
        # doesn't change which props appear -- lock buttons below still
        # re-match by player/line against _board, not by position, so
        # this re-sort is safe.
        _tier_rank = {"SOVEREIGN": 0, "ELITE": 1, "APPROVED": 2, "LEAN": 3}
        _rows.sort(key=lambda x: _tier_rank.get(x.get("_tier", ""), 9))

        # ── Sticky Summary Bar ─────────────────────────────────────────
        _n_sov   = sum(1 for r in _rows if r.get("_tier") == "SOVEREIGN")
        _n_elite = sum(1 for r in _rows if r.get("_tier") == "ELITE")
        _n_appr  = sum(1 for r in _rows if r.get("_tier") == "APPROVED")
        _total_action = sum(
            (r.get("_p", {}).get("KellyAdvisedPct", 0) or 0) * _bankroll_now
            for r in _rows if r.get("_tier") in ("SOVEREIGN", "ELITE", "APPROVED")
        )
        st.markdown(
            f'<div class="bc-summary-bar">'
            f'<span style="color:var(--bc-dim);font-size:11px;letter-spacing:1px;text-transform:uppercase;">BOARD</span>'
            f'<span class="bc-summary-pill bc-sov-pill">⚡ {_n_sov} SOVEREIGN</span>'
            f'<span class="bc-summary-pill bc-elite-pill">▲ {_n_elite} ELITE</span>'
            f'<span class="bc-summary-pill bc-appr-pill">● {_n_appr} APPROVED</span>'
            f'<span style="flex:1"></span>'
            f'<span class="bc-summary-pill bc-action-pill">💰 ${_total_action:.2f} total action</span>'
            f'<span style="color:#2a3a4a;font-size:10px;">{len(_rows)} props loaded</span>'
            f'</div>',
            unsafe_allow_html=True
        )

        # ── Spotlight: today's top-ranked pick(s), real data only.
        # _rows is already tier+sort ordered above. Only ever shows
        # Sovereign/Elite tier picks -- no false standout on a weak day.
        def _sp_rationale(row):
            """Real rationale from actual per-signal magnitudes already
            computed on the prop (SignalBase/Defense/Location/Usage) --
            NOT EdgeTypeReason, which is read elsewhere in this file but
            confirmed (checked before building this) to never actually be
            set anywhere in the codebase, so it's always empty. Picks
            whichever real signal has the largest magnitude and names it,
            plus the real model-vs-market gap -- no invented commentary.
            Each named term carries a title= tooltip with its actual real
            value -- "Reliability" uses the real _rel field (kept the
            honest name rather than calling it "Variance Suppression",
            since there's no genuine per-prop variance metric available
            to back that specific label without inventing one)."""
            _p_sig = row.get("_p", {})
            _sig_vals = {
                "Matchup Delta": abs(float(_p_sig.get("SignalDefense", 0) or 0)),
                "Usage Trend": abs(float(_p_sig.get("SignalUsage", 0) or 0)),
                "Home/Away Split": abs(float(_p_sig.get("SignalLocation", 0) or 0)),
                "Base Model Strength": abs(float(_p_sig.get("SignalBase", 0) or 0)),
            }
            _top_sig = max(_sig_vals, key=_sig_vals.get) if any(_sig_vals.values()) else None
            _parts = []
            if _top_sig and _sig_vals[_top_sig] > 0:
                _parts.append(
                    f'Driven primarily by <span title="Raw signal value: {_sig_vals[_top_sig]:.3f}" '
                    f'style="border-bottom:1px dotted var(--bc-dim);cursor:help;">{_top_sig}</span>'
                )
            _rel_val = row.get("_rel", "")
            if _rel_val and _rel_val != "—":
                _parts.append(
                    f'<span title="Signal agreement: {_rel_val} sources aligned" '
                    f'style="border-bottom:1px dotted var(--bc-dim);cursor:help;">Reliability {_rel_val}</span>'
                )
            try:
                _mp = float(str(row.get("_model_prob", "")).replace("%", ""))
                _edge_val = row.get("_edge_pct", 0)
                _parts.append(
                    f'<span title="Edge (model vs market-implied price): {_edge_val}%" '
                    f'style="border-bottom:1px dotted var(--bc-dim);cursor:help;">Market Mispricing</span> ({_mp:.0f}% model)'
                )
            except (ValueError, TypeError):
                pass
            return " · ".join(_parts) if _parts else "Edge from combined signal strength"

        def _sp_card_html(row, label, reveal=False):
            _tc = TIER_COLORS.get(row["_tier"], "#6a7a8a")
            _edge_str = f"+{row['_edge_pct']}%" if row["_edge_pct"] > 0 else f"{row['_edge_pct']}%"
            _reveal_cls = " spotlight-reveal" if reveal else ""
            return (
                f'<div class="command-card{_reveal_cls}" style="text-align:left;padding:16px 20px;margin-bottom:10px;'
                f'border-left:4px solid {_tc};background:linear-gradient(135deg,var(--bc-bg-card) 0%,{_tc}14 140%);">'
                f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                f'<div style="flex:1;">'
                f'<div class="command-label" style="color:{_tc};">{label}</div>'
                f'<div style="font-size:1.15rem;font-weight:800;color:var(--bc-text);margin-top:6px;">'
                f'{row["_player"]} <span style="font-weight:400;color:var(--bc-muted);">— {row["_side"]} {row["_line"]} {row["_prop"]}</span></div>'
                f'<div style="font-size:0.8rem;color:var(--bc-dim);margin-top:8px;">{row["_team"]} · {_sp_rationale(row)}</div>'
                f'</div>'
                f'<div style="width:1px;align-self:stretch;background:rgba(255,255,255,0.07);margin:0 18px;"></div>'
                f'<div style="text-align:right;">'
                f'<div class="command-label" style="font-size:0.62rem;">Model Confidence</div>'
                f'<div class="odds-mono" style="font-size:1.05rem;font-weight:700;color:var(--bc-text);margin:2px 0 6px;">{row["_model_prob"]}%</div>'
                f'<div class="odds-mono" style="font-size:1.6rem;font-weight:800;color:{row["_grade_color"]};">{_edge_str}</div>'
                f'<div style="font-size:0.7rem;color:{_tc};font-weight:700;text-transform:uppercase;">{row["_tier"]} · Grade {row["_grade"]}</div>'
                f'</div>'
                f'</div>'
                f'</div>'
            )

        # ── Board Strength indicator -- real tier composition of today's
        # (filtered) board, not decorative. Explains why Spotlight may or
        # may not appear right below it.
        _n_sov_bs = sum(1 for r in _rows if r.get("_tier") == "SOVEREIGN")
        _n_elite_bs = sum(1 for r in _rows if r.get("_tier") == "ELITE")
        _n_appr_bs = sum(1 for r in _rows if r.get("_tier") == "APPROVED")
        if _n_sov_bs or _n_elite_bs:
            _bs_label, _bs_color = "Strong board", "#22c55e"
        elif _n_appr_bs:
            _bs_label, _bs_color = "Moderate board", "#e8a020"
        else:
            _bs_label, _bs_color = "Weak board", "#6a7a8a"
        st.markdown(
            f'<div style="display:inline-flex;align-items:center;gap:6px;margin-bottom:10px;'
            f'font-size:0.75rem;color:{_bs_color};font-weight:600;" '
            f'title="Strong = Sovereign/Elite present · Moderate = Approved only · Weak = nothing above Approved">'
            f'● {_bs_label}</div>',
            unsafe_allow_html=True
        )

        if _rows and _rows[0].get("_tier") in ("SOVEREIGN", "ELITE"):
            _n_sov_today = sum(1 for r in _rows if r.get("_tier") == "SOVEREIGN")
            _n_elite_today = sum(1 for r in _rows if r.get("_tier") == "ELITE")
            # Multi-spotlight gate: >=3 Elite, or >=1 Sovereign + >=2 Elite.
            _multi_ok = _n_elite_today >= 3 or (_n_sov_today >= 1 and _n_elite_today >= 2)
            _sp_candidates = [_rows[0]]
            if _multi_ok:
                for _r2 in _rows[1:3]:
                    if _r2.get("_tier") in ("SOVEREIGN", "ELITE"):
                        _sp_candidates.append(_r2)

            # Cinematic reveal: fade-in + slight scale, but ONLY on the
            # render where the #1 pick's identity is genuinely different
            # from the last one seen this session -- not on every rerun,
            # which would replay the animation on every filter tweak.
            _sp_top_id_check = f"{_rows[0]['_player']}|{_rows[0]['_prop']}|{_rows[0]['_line']}"
            _sp_is_new_reveal = (
                st.session_state.get("_sp_last_seen_id") is not None
                and st.session_state.get("_sp_last_seen_id") != _sp_top_id_check
            )

            _sp_labels = (["🎯 Spotlight — Top Edge Right Now"] if len(_sp_candidates) == 1
                          else [f"🎯 Spotlight #{i+1}" for i in range(len(_sp_candidates))])
            st.markdown(
                "".join(
                    _sp_card_html(r, l, reveal=(i == 0 and _sp_is_new_reveal))
                    for i, (r, l) in enumerate(zip(_sp_candidates, _sp_labels))
                ),
                unsafe_allow_html=True
            )
        elif _rows:
            st.caption("🎯 No Sovereign or Elite picks today. Board does not meet Spotlight criteria.")

        if _rows:
            # ── Spotlight alert: only fires when today's #1 pick is a
            # genuinely NEW spotlight vs the last one seen this session,
            # or jumped up to Sovereign from something lower. Session-only
            # (not persisted across browser sessions) -- a real cross-
            # session version would need its own Gist round-trip on every
            # single board load just to check, which isn't worth the cost
            # for a same-session convenience notice.
            _sp_top = _rows[0]
            _sp_id = f"{_sp_top['_player']}|{_sp_top['_prop']}|{_sp_top['_line']}"
            _sp_prev_id = st.session_state.get("_sp_last_seen_id")
            _sp_prev_tier = st.session_state.get("_sp_last_seen_tier")
            if _sp_prev_id is not None and _sp_id != _sp_prev_id:
                if _sp_top["_tier"] == "SOVEREIGN":
                    st.info(f"🔔 New Sovereign-tier spotlight: **{_sp_top['_player']}** — {_sp_top['_side']} {_sp_top['_line']} {_sp_top['_prop']}")
                elif _sp_top["_tier"] == "ELITE" and _sp_prev_tier != "SOVEREIGN":
                    st.info(f"🔔 New Elite-tier spotlight: **{_sp_top['_player']}** — {_sp_top['_side']} {_sp_top['_line']} {_sp_top['_prop']}")
            st.session_state["_sp_last_seen_id"] = _sp_id
            st.session_state["_sp_last_seen_tier"] = _sp_top["_tier"]

            # ── Spotlight history: log today's top pick once (deduped by
            # date+player+prop), then show real win-rate/ROI IF enough
            # past spotlight picks have since resolved -- no fake numbers
            # on day one, an honest "not enough history yet" instead.
            try:
                _sp_today_key = date.today().strftime("%Y-%m-%d")
                _sp_log = load_from_gist("spotlight_log", None) or []
                _sp_entry_id = f"{_sp_today_key}|{_sp_top['_player']}|{_sp_top['_prop']}|{_sp_top['_line']}"
                if not any(e.get("id") == _sp_entry_id for e in _sp_log):
                    _sp_log.append({
                        "id": _sp_entry_id, "date": _sp_today_key,
                        "player": _sp_top["_player"], "prop": _sp_top["_prop"],
                        "line": _sp_top["_line"], "side": _sp_top["_side"],
                        "tier": _sp_top["_tier"], "sport": _sport,
                    })
                    _sp_log = _sp_log[-200:]  # cap growth, most-recent-first isn't needed for matching
                    save_to_gist("spotlight_log", _sp_log)

                _sp_resolved_matches = []
                _sp_history_all = st.session_state.get("history", [])
                _sp_hist_idx = {}
                for _h in _sp_history_all:
                    if _h.get("outcome") in ("WIN", "LOSS"):
                        _sp_hist_idx.setdefault((normalize_name(_h.get("player", "")), _h.get("prop", "")), []).append(_h)
                for _entry in _sp_log:
                    _sp_key = (normalize_name(_entry["player"]), _entry["prop"])
                    for _h in _sp_hist_idx.get(_sp_key, []):
                        if _h.get("timestamp", "")[:10] >= _entry["date"]:
                            _sp_resolved_matches.append(_h)
                            break

                if len(_sp_resolved_matches) >= 5:
                    _sp_wins = sum(1 for h in _sp_resolved_matches if h["outcome"] == "WIN")
                    _sp_last10 = _sp_resolved_matches[-10:]
                    _sp_wr = _sp_wins / len(_sp_resolved_matches) * 100
                    _sp_wagered = sum(float(h.get("wager", 0) or 0) for h in _sp_resolved_matches)
                    _sp_net = sum(
                        (float(h.get("wager", 0) or 0) * float(h.get("payout_mult", 1.0) or 1.0) - float(h.get("wager", 0) or 0))
                        if h["outcome"] == "WIN" else -float(h.get("wager", 0) or 0)
                        for h in _sp_resolved_matches
                    )
                    _sp_roi = (_sp_net / _sp_wagered * 100) if _sp_wagered else 0
                    with st.expander(f"📜 Spotlight History — {len(_sp_resolved_matches)} resolved picks"):
                        st.markdown(
                            f'Win rate: <span style="color:{"#22c55e" if _sp_wr>=52.4 else "#e04040"};font-weight:700;">{_sp_wr:.0f}%</span> '
                            f'({_sp_wins}/{len(_sp_resolved_matches)}) · '
                            f'Last 10: {"".join("✅" if h["outcome"]=="WIN" else "❌" for h in _sp_last10)} · '
                            f'Rolling ROI: <span style="color:{"#22c55e" if _sp_roi>=0 else "#e04040"};font-weight:700;">{_sp_roi:+.1f}%</span>',
                            unsafe_allow_html=True,
                        )
                else:
                    st.caption(f"📜 Spotlight History: only {len(_sp_resolved_matches)} resolved spotlight pick(s) so far — needs 5+ before showing a real win rate.")
            except Exception:
                _logger.debug("Spotlight history tracking failed silently")
        st.caption(f"Showing {len(_rows)} props | Sorted by {_sort_col}")

        # ── Render table ────────────────────────────────────────
        # Header
        _tier_colors = TIER_COLORS

        _header = (
            '<div style="display:grid;grid-template-columns:'
            '12px 170px 58px 56px 95px 55px 60px 58px 62px 130px 48px 48px 48px 52px 72px;'
            'gap:6px;padding:8px 10px;background:var(--bc-bg-card);border-radius:6px 6px 0 0;'
            'font-size:12px;font-weight:700;color:var(--bc-dim);text-transform:uppercase;'
            'letter-spacing:0.04em;position:sticky;top:0;z-index:10;white-space:nowrap;">'
            '<span></span>'
            '<span>Player</span>'
            '<span>Tier</span>'
            '<span>Type</span>'
            '<span>Prop</span>'
            '<span style="text-align:center">Line</span>'
            '<span style="text-align:center">Grade</span>'
            '<span style="text-align:center">Edge</span>'
            '<span style="text-align:center">Model</span>'
            '<span style="text-align:center">Consensus</span>'
            '<span style="text-align:center">L5</span>'
            '<span style="text-align:center">L10</span>'
            '<span style="text-align:center">Szn</span>'
            '<span style="text-align:center">EV+</span>'
            '<span style="text-align:center">● Rely</span>'
            '</div>'
        )
        if _view_mode != "Cards":
            st.markdown(_header, unsafe_allow_html=True)

        if _view_mode == "Cards":
            _tier_badge_colors = {"SOVEREIGN": "#f5c518", "ELITE": "#1e90ff", "APPROVED": "#3ac47d", "LEAN": "#8ab4d4"}
            _cards_per_row = 3
            try:
                _og_edges_all = fetch_theoddsgap_edges_from_gist()
            except Exception:
                _og_edges_all = []
            def _og_edge_match(player_name):
                target = normalize_name(player_name)
                if not target:
                    return None
                return next((e for e in _og_edges_all if normalize_name(e.get("player","")) == target), None)
            for _ci in range(0, len(_rows), _cards_per_row):
                _card_cols = st.columns(_cards_per_row)
                for _cj, _rc in enumerate(_rows[_ci:_ci + _cards_per_row]):
                    with _card_cols[_cj]:
                        _tbc = _tier_badge_colors.get(_rc.get("_tier", ""), "#6a7a8a")
                        _og_match = _og_edge_match(_rc.get("_player", ""))
                        _og_edge_html = ""
                        if _og_match:
                            _og_gap = (_og_match.get("market_line", 0) or 0) - (_og_match.get("app_line", 0) or 0)
                            _og_gob = "🎯 " if _og_match.get("kind") == "goblin" else ""
                            _og_edge_html = (
                                f'<div style="color:var(--bc-dim);font-size:10.5px;margin-top:6px;border-top:1px solid var(--bc-bg2);padding-top:6px;">'
                                f'{_og_gob}Market Edge ({_og_match.get("app","")}): {_og_match.get("app_line","")} vs mkt {_og_match.get("market_line","")} '
                                f'(gap {_og_gap:+.1f}) · {_og_match.get("win_pct","?")}% win</div>'
                            )
                        st.markdown(
                            f'<div style="background:var(--bc-bg-card);border:1px solid {_tbc}44;'
                            f'border-radius:10px;padding:12px 14px;margin-bottom:12px;min-height:190px;">'
                            f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                            f'<span style="font-weight:700;font-size:14px;color:var(--bc-text);">{_rc.get("_player","")}</span>'
                            f'<span style="background:{_tbc};color:#0a1628;font-weight:700;font-size:11px;'
                            f'padding:2px 8px;border-radius:10px;">{_rc.get("_grade","")}</span>'
                            f'</div>'
                            f'<div style="color:var(--bc-dim);font-size:12px;margin-top:2px;">{_rc.get("_team","")}</div>'
                            f'<div style="font-size:15px;font-weight:600;color:var(--bc-text);margin-top:8px;">'
                            f'{_rc.get("_side","")} {_rc.get("_line","")} {_rc.get("_prop","")}</div>'
                            f'<div style="display:flex;gap:14px;margin-top:8px;">'
                            f'<div><div style="font-size:10px;color:var(--bc-dim);">EDGE</div>'
                            f'<div style="font-size:15px;font-weight:700;color:{_rc.get("_grade_color","var(--bc-text)")};">{_rc.get("_edge_pct","")}%</div></div>'
                            f'<div><div style="font-size:10px;color:var(--bc-dim);">MODEL</div>'
                            f'<div style="font-size:15px;font-weight:700;color:var(--bc-text);">{_rc.get("_model_prob","")}%</div></div>'
                            f'<div><div style="font-size:10px;color:var(--bc-dim);">BEST</div>'
                            f'<div style="font-size:13px;font-weight:600;color:var(--bc-text);">'
                            f'{_rc.get("_pinn") if _rc.get("_pinn") not in ("—","") else (_rc.get("_dk") if _rc.get("_dk") not in ("—","") else _rc.get("_fd",""))}</div></div>'
                            f'</div>'
                            f'<div style="color:var(--bc-dim);font-size:11px;margin-top:8px;">'
                            f'L5 {_rc.get("_l5","—")} · L10 {_rc.get("_l10","—")} · Szn {_rc.get("_szn","—")}</div>'
                            + _og_edge_html +
                            f'</div>',
                            unsafe_allow_html=True
                        )

        # Density toggle -- same data, tighter spacing/smaller font in
        # Dense mode. Not a feature mode, purely a display density setting.
        if st.session_state.get("ev_density") == "Dense":
            _row_pad, _row_font, _row_minh = "3px 10px", "12px", "24px"
        else:
            _row_pad, _row_font, _row_minh = "6px 10px", "14px", "32px"

        # Rows
        _html_rows = []
        _lock_buttons = []  # collect lock actions outside HTML
        _prev_tier_group = None
        try:
            _og_edges_table = fetch_theoddsgap_edges_from_gist()
        except Exception:
            _og_edges_table = []
        def _og_table_match(player_name):
            target = normalize_name(player_name)
            if not target:
                return None
            return next((e for e in _og_edges_table if normalize_name(e.get("player","")) == target), None)
        for _r in (_rows if _view_mode != "Cards" else []):
            if _r.get("_tier") != _prev_tier_group:
                _prev_tier_group = _r.get("_tier")
                _grp_color = _tier_colors.get(_prev_tier_group, "#6a7a8a")
                _html_rows.append(
                    f'<div style="padding:6px 10px 3px;margin-top:4px;font-size:11px;'
                    f'font-weight:700;letter-spacing:0.5px;text-transform:uppercase;'
                    f'color:{_grp_color};border-top:1px solid rgba(255,255,255,0.06);">'
                    f'{_prev_tier_group}</div>'
                )
            _tc    = _tier_colors.get(_r["_tier"],"#6a7a8a")
            _gc    = _r["_grade_color"]
            _bg    = _r["_row_bg"]
            _e_str = f"+{_r['_edge_pct']}%" if _r["_edge_pct"] > 0 else f"{_r['_edge_pct']}%"
            # Edge heatmap: background intensity scales with edge magnitude
            # (0% -> transparent, 15%+ -> full intensity) so a scanning eye
            # catches the strongest edges by color weight, not just the
            # number itself. Green for positive edge (the only case that
            # reaches display after the min-edge filter above), capped at
            # 15% so one outlier prop doesn't wash out the rest of the scale.
            _heat_alpha = min(1.0, max(0.0, _r["_edge_pct"] / 15.0)) * 0.35
            _heat_bg = f"rgba(34,197,94,{_heat_alpha:.2f})" if _r["_edge_pct"] > 0 else "transparent"
            # Tier badge + left accent bar
            _tc_hex = TIER_COLORS.get(_r["_tier"], "#6a7a8a").lstrip("#")
            _tc_rgb = tuple(int(_tc_hex[i:i+2], 16) for i in (0, 2, 4)) if len(_tc_hex) == 6 else (106, 122, 138)
            _tier_bg   = f"rgba({_tc_rgb[0]},{_tc_rgb[1]},{_tc_rgb[2]},0.14)"
            _tier_str  = _r["_tier"][:3]
            _conf_color = "#22c55e" if _r.get("_conflict")=="ALIGNED" else "#e04040" if _r.get("_conflict")=="CONFLICTED" else "#e8a020"
            _rely_color = "#22c55e" if _r["_rel"] in ("4/4","3/4") else "var(--bc-dim)"
            _gs = "17px" if _r["_grade"] in ("A+","A") else "15px"
            # Edge type badge
            _et      = _r.get("_p", {}).get("EdgeType", "")
            _et_col  = _r.get("_p", {}).get("EdgeTypeColor", "#6a7a8a")
            _et_lbl  = {"A": "ARB", "B": "α", "C": "~"}.get(_et, "?")
            _et_html = (f'<span title="{_r.get("_p",{}).get("EdgeTypeLabel","")}: '
                        f'{_r.get("_p",{}).get("EdgeTypeReason","")}" '
                        f'style="background:{_et_col}22;color:{_et_col};font-size:9px;'
                        f'font-weight:700;padding:2px 4px;border-radius:3px;">{_et_lbl}</span>'
                        ) if _et else ""
            # Build consensus bar: colored dots for each source
            _p_dict = _r.get("_p", {})
            _cons_sources = [
                ("G",  "#378add" if _p_dict.get("EVSharpEV") else "var(--bc-border)"),   # EVSharps/Outlier
                ("Cl", "#378add" if _p_dict.get("CLVCapture") else "var(--bc-border)"),  # CLV
                ("P",  "#378add" if _r.get("_kalshi") else "var(--bc-border)"),           # Kalshi/Poly
                ("S",  "#22c55e" if _p_dict.get("EVSharpMove") else "var(--bc-border)"), # Sharp steam
                ("G",  "#22c55e" if _r.get("_model_prob", 0) and safe_float(str(_r.get("_model_prob",0)).replace("%",""), 0) >= 60 else "var(--bc-border)"),  # Grade
                ("B",  "#e8a020" if _p_dict.get("BetterLineNote") else "var(--bc-border)"),  # Better line
            ]
            # Unabated dot handled separately (not in the loop below) because
            # it's tri-state (flagged / agreed / no data) where the other
            # dots are boolean present/absent — "no data" needs to look
            # visually different from "checked, no disagreement found",
            # otherwise a gray dot reads as "confirmed" when it may just mean
            # Unabated never matched this row (see _UNABATED_BOOK_KEY above).
            _unab_fair = _p_dict.get("UnabatedFairProb")
            if _unab_fair is None:
                _unab_dot = ('<span style="display:inline-block;width:13px;height:13px;'
                             'border-radius:50%;border:1.5px solid var(--bc-border);'
                             'background:transparent;margin-right:2px;" '
                             'title="U: no Unabated data for this row"></span>')
            else:
                _unab_col = ("#e04040" if _p_dict.get("UnabatedFlag") and _p_dict.get("UnabatedDirection")=="market_higher"
                             else "#22c55e" if _p_dict.get("UnabatedFlag") else "var(--bc-border)")
                _unab_title = "U: market thinks easier than GEM" if _unab_col == "#e04040" else \
                              "U: GEM thinks easier than market" if _unab_col == "#22c55e" else \
                              "U: checked, no disagreement"
                _unab_dot = (f'<span style="display:inline-block;width:13px;height:13px;border-radius:50%;'
                             f'background:{_unab_col};font-size:8px;font-weight:700;color:#ffffff;'
                             f'text-align:center;line-height:13px;margin-right:2px;" title="{_unab_title}">U</span>')
            _evs_fair = _p_dict.get("EVSharpsFairProb")
            if _evs_fair is None:
                _evs_dot = ('<span style="display:inline-block;width:13px;height:13px;'
                             'border-radius:50%;border:1.5px solid var(--bc-border);'
                             'background:transparent;margin-right:2px;" '
                             'title="E: no EVSharps data for this row (MLB HR props only)"></span>')
            else:
                _evs_col = ("#e04040" if _p_dict.get("EVSharpsFlag") and _p_dict.get("EVSharpsDirection")=="market_higher"
                             else "#22c55e" if _p_dict.get("EVSharpsFlag") else "var(--bc-border)")
                _evs_title = "E: market thinks easier than GEM" if _evs_col == "#e04040" else \
                              "E: GEM thinks easier than market" if _evs_col == "#22c55e" else \
                              "E: checked, no disagreement"
                _evs_dot = (f'<span style="display:inline-block;width:13px;height:13px;border-radius:50%;'
                             f'background:{_evs_col};font-size:8px;font-weight:700;color:#ffffff;'
                             f'text-align:center;line-height:13px;margin-right:2px;" title="{_evs_title}">E</span>')
            _og_match_row = _og_table_match(_r.get("_player", ""))
            if _og_match_row is None:
                _og_dot = ('<span style="display:inline-block;width:13px;height:13px;'
                           'border-radius:50%;border:1.5px solid var(--bc-border);'
                           'background:transparent;margin-right:2px;" '
                           'title="O: no theoddsgap data for this player"></span>')
            else:
                _og_gap_row = (_og_match_row.get("market_line", 0) or 0) - (_og_match_row.get("app_line", 0) or 0)
                _og_col = "#22c55e" if _og_gap_row > 0 else ("#e04040" if _og_gap_row < 0 else "var(--bc-border)")
                _og_title = (f"O: {_og_match_row.get('app','')} {_og_match_row.get('app_line','')} vs mkt "
                             f"{_og_match_row.get('market_line','')} (gap {_og_gap_row:+.1f}) · {_og_match_row.get('win_pct','?')}% win")
                _og_dot = (f'<span style="display:inline-block;width:13px;height:13px;border-radius:50%;'
                           f'background:{_og_col};font-size:8px;font-weight:700;color:#ffffff;'
                           f'text-align:center;line-height:13px;margin-right:2px;" title="{_og_title}">O</span>')
            _cons_bar = "".join([
                f'<span style="display:inline-block;width:13px;height:13px;border-radius:50%;'
                f'background:{col};font-size:8px;font-weight:700;color:#ffffff;'
                f'text-align:center;line-height:13px;margin-right:2px;" title="{lbl}">{lbl[0]}</span>'
                for lbl, col in _cons_sources
            ]) + _unab_dot + _evs_dot + _og_dot
            # Filled bar count for % display
            _filled = sum(1 for _, c in _cons_sources if c != "var(--bc-border)")
            _cons_pct = int(_filled / len(_cons_sources) * 100)
            _cons_cell = (
                f'<div style="display:flex;flex-direction:row;align-items:center;gap:5px;white-space:nowrap;">'
                f'{_cons_bar}'
                f'<span style="font-size:11px;color:#4a6a8a;">{_cons_pct}%</span>'
                f'</div>'
            )

            _tier_css = {
                "SOVEREIGN": "row-sovereign",
                "ELITE":     "row-elite",
                "APPROVED":  "row-approved",
                "LEAN":      "row-lean",
            }.get(_r["_tier"], "row-lean")

            _row = (
                f'<div class="{_tier_css}" style="display:grid;grid-template-columns:'
                f'12px 170px 58px 56px 95px 55px 60px 58px 62px 130px 48px 48px 48px 52px 72px;'
                f'gap:6px;padding:{_row_pad};background:{_bg};'
                f'border-bottom:1px solid rgba(26,58,92,0.5);font-size:{_row_font};align-items:center;'
                f'min-height:{_row_minh};cursor:default;transition:background 0.15s;">'
                f'<span style="width:3px;height:24px;background:{_tc};display:block;margin:auto;border-radius:2px;"></span>'
                f'<span style="font-weight:600;color:var(--bc-text);">{_r["_player"][:22]}</span>'
                f'<span style="background:{_tier_bg};color:{_tc};font-size:11px;font-weight:700;'
                f'padding:3px 6px;border-radius:3px;text-transform:uppercase;">{_tier_str}</span>'
                f'{_et_html}'
                f'<span style="text-align:center;color:var(--bc-muted);font-size:13px;">{_r["_prop"][:12]} {_r["_side"]}</span>'
                f'<span class="odds-mono" style="text-align:center;font-size:14px;">{_r["_line"]}</span>'
                f'<span style="text-align:center;font-size:{_gs};font-weight:800;color:{_gc};">{_r["_grade"]}</span>'
                f'<span class="odds-mono" style="text-align:center;font-size:14px;color:{_gc};background:{_heat_bg};border-radius:4px;padding:2px 4px;">{_e_str}</span>'
                f'<span class="odds-mono" style="text-align:center;font-size:14px;color:var(--bc-muted);">{_r["_model_prob"]}%</span>'
                f'{_cons_cell}'
                f'<span style="text-align:center;color:var(--bc-muted);font-size:13px;">{_r["_l5"]}</span>'
                f'<span style="text-align:center;color:var(--bc-muted);font-size:13px;">{_r["_l10"]}</span>'
                f'<span style="text-align:center;color:var(--bc-muted);font-size:13px;">{_r["_szn"]}</span>'
                + (
                    f'<span style="text-align:center;font-size:13px;font-weight:700;color:#00d4aa;">'
                    f'{float(_r["_ev_sharp"]):+.1%}</span>'
                    if _r.get("_ev_sharp") is not None else
                    f'<span style="text-align:center;color:var(--bc-dim);font-size:13px;">—</span>'
                ) +
                f'<span style="text-align:center;white-space:nowrap;">'
                f'<span style="color:{_conf_color};font-size:12px;">●</span> '
                f'<span style="color:{_rely_color};font-size:13px;">{_r["_rel"]}</span>'
                f'</span></div>'
            )
            _html_rows.append(_row)
        # Render in chunks to avoid hitting Streamlit limits
        _chunk = 50
        for _i in range(0, len(_html_rows), _chunk):
            st.markdown(
                '<div style="border-radius:0 0 6px 6px;overflow:hidden;">'
                + "".join(_html_rows[_i:_i+_chunk])
                + '</div>',
                unsafe_allow_html=True
            )

        # Individual lock buttons — rendered outside HTML for interactivity
        if _rows:
            st.markdown("**Quick Lock:**")
            _lk_cols = st.columns(min(5, len(_rows)))
            for _lki, _lr in enumerate(_rows[:10]):
                _lk_col = _lk_cols[_lki % len(_lk_cols)]
                with _lk_col:
                    _lk_label = f"🔒 {_lr['_player'][:12]} {_lr['_grade']}"
                    if st.button(_lk_label, key=f"ev_lock_{_lki}", use_container_width=True,
                                  help=f"{_lr['_prop']} {_lr['_side']} {_lr['_line']} | {'+' if _lr['_edge_pct']>0 else ''}{_lr['_edge_pct']}%"):
                        # Find the prop in board and lock it
                        _lk_prop = next((p for p in _board
                                         if normalize_name(p.get("Player",""))==normalize_name(_lr["_player"])
                                         and str(p.get("Line",""))==str(_lr["_line"])), None)
                        if _lk_prop:
                            _already = any(
                                normalize_name(l.get("player",""))==normalize_name(_lr["_player"]) and
                                str(l.get("line",""))==str(_lr["_line"])
                                for l in st.session_state.get("locks", [])
                            )
                            if not _already:
                                st.session_state["locks"].append({
                                    "player":    _lk_prop.get("Player",""),
                                    "prop":      _lk_prop.get("Prop",""),
                                    "line":      _lk_prop.get("Line",0),
                                    "side":      _lk_prop.get("Side","OVER"),
                                    "tier":      _lk_prop.get("Tier",""),
                                    "edge":      _lk_prop.get("Edge",0),
                                    "sport":     _sport,
                                    "source":    "EV Optimizer",
                                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                    "prob":      _lk_prop.get("Prob",0.5),
                                    "team":      _lk_prop.get("Team",""),
                                    "signal_values": _board_prop_signal_values(_lk_prop),
                                    "clv_capture": _capture_clv_placement(_lk_prop.get("Player",""), _lk_prop.get("Prop",""), _lk_prop.get("Prob",0.5)),
                                })
                                _show_team_exposure_warning(_lk_prop.get("Team",""), _sport)
                                # Capture Pinnacle CLV at lock-time — this was
                                # previously dead code (record_pinnacle_line
                                # existed but was never called from anywhere),
                                # which is why the Pinnacle CLV Tracker stayed
                                # stuck on "need 5 more" no matter how many
                                # bets were resolved.
                                try:
                                    record_pinnacle_line(st.session_state["locks"][-1], _board)
                                except Exception:
                                    pass
                                save_json_data(LOCKS_PATH, st.session_state.locks)
                                save_to_gist("locks", st.session_state.locks)  # persists across restarts
                                st.success(f"Locked {_lr['_player']} {_lr['_prop']}")
                                st.rerun()
                            else:
                                st.info("Already locked")

        # ── Lock any prop (covers the full board, not just the first 10
        # rows that get quick-lock buttons above). A dedicated button per
        # row for every row on a 50-100 row board isn't practical, so this
        # is a searchable dropdown + one lock button instead — every prop
        # shown in the table is reachable here regardless of table size.
        if len(_rows) > 10:
            st.markdown("**Lock any prop from this board:**")
            _all_row_labels = [
                f"{r['_player']} — {r['_side']} {r['_line']} {r['_prop']} ({r['_tier']}, +{r['_edge_pct']}%)"
                for r in _rows
            ]
            _lk_pick_col1, _lk_pick_col2 = st.columns([4,1])
            with _lk_pick_col1:
                _lk_pick = st.selectbox("Search props", ["— select —"] + _all_row_labels,
                                         key="fullboard_lock_search", label_visibility="collapsed")
            with _lk_pick_col2:
                if st.button("🔒 Lock", key="fullboard_lock_search_btn", use_container_width=True) and _lk_pick != "— select —":
                    _lk_idx = _all_row_labels.index(_lk_pick)
                    _lr2 = _rows[_lk_idx]
                    _lk_prop2 = next((p for p in _board
                                      if normalize_name(p.get("Player",""))==normalize_name(_lr2["_player"])
                                      and str(p.get("Line",""))==str(_lr2["_line"])), None)
                    if _lk_prop2:
                        _already2 = any(
                            normalize_name(l.get("player",""))==normalize_name(_lr2["_player"]) and
                            str(l.get("line",""))==str(_lr2["_line"])
                            for l in st.session_state.get("locks", [])
                        )
                        if not _already2:
                            st.session_state["locks"].append({
                                "player":    _lk_prop2.get("Player",""),
                                "prop":      _lk_prop2.get("Prop",""),
                                "line":      _lk_prop2.get("Line",0),
                                "side":      _lk_prop2.get("Side","OVER"),
                                "tier":      _lk_prop2.get("Tier",""),
                                "edge":      _lk_prop2.get("Edge",0),
                                "sport":     _sport,
                                "source":    "EV Optimizer",
                                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                "prob":      _lk_prop2.get("Prob",0.5),
                                "team":      _lk_prop2.get("Team",""),
                                "signal_values": _board_prop_signal_values(_lk_prop2),
                                "clv_capture": _capture_clv_placement(_lk_prop2.get("Player",""), _lk_prop2.get("Prop",""), _lk_prop2.get("Prob",0.5)),
                            })
                            _show_team_exposure_warning(_lk_prop2.get("Team",""), _sport)
                            try:
                                record_pinnacle_line(st.session_state["locks"][-1], _board)
                            except Exception:
                                pass
                            save_json_data(LOCKS_PATH, st.session_state.locks)
                            save_to_gist("locks", st.session_state.locks)
                            st.success(f"Locked {_lr2['_player']} {_lr2['_prop']}")
                            st.rerun()
                        else:
                            st.info("Already locked")

        if not _rows:
            st.info("No props match current filters.")

        # ── Portfolio Builder ─────────────────────────────────
        st.markdown("---")
        st.markdown("#### 🎯 Portfolio Builder")
        st.caption("Select the cleanest N bets controlling for concentration and correlation.")
        _pb1, _pb2, _pb3, _pb4, _pb5 = st.columns(5)
        with _pb1:
            _n_bets = st.selectbox("Bets", [3,5,10,15,20], index=1, key="pb_n")
        with _pb2:
            _max_player = st.selectbox("Max/player", [1,2,3], index=0, key="pb_maxp")
        with _pb3:
            _max_game = st.selectbox("Max/game", [1,2,3], index=1, key="pb_maxg")
        with _pb4:
            _max_vol = st.selectbox("Max volatile", [0,1,2], index=1, key="pb_maxv")
        with _pb5:
            _min_bq = st.number_input("Min BQ", 0, 100, 50, 5, key="pb_minbq")
        
        if st.button(f"🏗️ Build {_n_bets}-Bet Portfolio", key="pb_build", type="primary"):
            _pb_selected, _pb_metrics = build_optimal_portfolio(
                _board, n_bets=_n_bets, sport=_sport,
                max_per_player=_max_player, max_per_game=_max_game,
                max_volatile=_max_vol, min_bq=_min_bq,
            )
            if _pb_selected:
                st.session_state["portfolio_selection"] = _pb_selected
                st.session_state["portfolio_metrics"]   = _pb_metrics
            else:
                st.warning("No props meet the criteria. Try lowering Min BQ.")
        
        _pb_sel = st.session_state.get("portfolio_selection", [])
        _pb_met = st.session_state.get("portfolio_metrics", {})
        if _pb_sel:
            # Health metrics
            _hc1, _hc2, _hc3, _hc4, _hc5 = st.columns(5)
            _hc1.metric("Avg BQ", f"{_pb_met.get('avg_bq',0):.0f}")
            _hc2.metric("Avg Edge", f"{_pb_met.get('avg_edge',0):.1f}%")
            _hc3.metric("Aligned", _pb_met.get("n_aligned",0))
            _hc4.metric("Games", _pb_met.get("unique_games",0))
            _hc5.metric("Health", _pb_met.get("health_label",""))
            
            # Correlation warnings
            _corr_warns = check_correlation_risk(_pb_sel)
            for _cw in _corr_warns:
                _cw_color = {"HIGH":"#e04040","MEDIUM":"#e8a020","LOW":"#6a7a8a"}.get(_cw["severity"],"#6a7a8a")
                st.markdown(
                    f'<div style="background:var(--bc-bg-card);border-left:3px solid {_cw_color};'
                    f'border-radius:4px;padding:4px 8px;margin-bottom:3px;font-size:11px;">'
                    f'<span style="color:{_cw_color};">{_cw["message"]}</span></div>',
                    unsafe_allow_html=True
                )
            
            # Selected bets table
            st.markdown("**Selected Portfolio:**")
            for _i, _pp in enumerate(_pb_sel, 1):
                _pp_edge = round(float(_pp.get("Edge",0) or 0)*100, 1)
                _pp_bq   = int(_pp.get("BetQualityScore",0) or 0)
                _pp_grade= "A+" if _pp_bq>=85 else "A" if _pp_bq>=75 else "B+" if _pp_bq>=65 else "B" if _pp_bq>=55 else "C"
                _pp_col  = "#22c55e" if _pp_bq>=75 else "#e8a020" if _pp_bq>=55 else "#6a7a8a"
                st.markdown(
                    f'<div style="display:flex;justify-content:space-between;padding:5px 8px;'
                    f'background:var(--bc-bg);border-radius:4px;margin-bottom:3px;">'
                    f'<span style="color:var(--bc-text);font-weight:600;">{_i}. {_pp.get("Player","")} '
                    f'— {_pp.get("Prop","")} {_pp.get("Side","")} {_pp.get("Line","")}</span>'
                    f'<span style="color:{_pp_col};font-weight:700;">{_pp_grade} | '
                    f'BQ:{_pp_bq} | +{_pp_edge}%</span></div>',
                    unsafe_allow_html=True
                )
            
            # Lock all portfolio bets
            if st.button("🔒 Lock All Portfolio Bets", key="pb_lock_all"):
                for _lp in _pb_sel:
                    _already = any(
                        normalize_name(l.get("player",""))==normalize_name(_lp.get("Player","")) and
                        str(l.get("line",""))==str(_lp.get("Line",""))
                        for l in st.session_state.get("locks", [])
                    )
                    if not _already:
                        st.session_state["locks"].append({
                            "player": _lp.get("Player",""), "prop": _lp.get("Prop",""),
                            "line": _lp.get("Line",0), "side": _lp.get("Side","OVER"),
                            "tier": _lp.get("Tier",""), "edge": _lp.get("Edge",0),
                            "sport": _sport, "source": "Portfolio Builder",
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "prob": _lp.get("Prob",0.5),
                            "team": _lp.get("Team",""),
                            "signal_values": _board_prop_signal_values(_lp),
                            "clv_capture": _capture_clv_placement(_lp.get("Player",""), _lp.get("Prop",""), _lp.get("Prob",0.5)),
                        })
                        try:
                            record_pinnacle_line(st.session_state["locks"][-1], _board)
                        except Exception:
                            pass
                save_json_data(LOCKS_PATH, st.session_state.locks)
                save_to_gist("locks", st.session_state.locks)  # persists across restarts
                st.success(f"Locked {len(_pb_sel)} portfolio bets")
                # One summary per team, not one warning per lock -- a
                # multi-bet lock-all action would otherwise stack up to
                # len(_pb_sel) near-identical warnings.
                for _pb_team in sorted(set(_lp.get("Team","") for _lp in _pb_sel if _lp.get("Team"))):
                    _pb_sport = next((_lp.get("Sport", _sport) for _lp in _pb_sel if _lp.get("Team")==_pb_team), _sport)
                    _show_team_exposure_warning(_pb_team, _pb_sport)
                st.rerun()

        # ── Quick action bar ─────────────────────────────────────
        st.markdown("---")
        _qa1, _qa2, _qa3 = st.columns(3)
        with _qa1:
            if st.button("🔒 Lock all SOVEREIGN/ELITE", key="ev_lock_all"):
                for _p in _board:
                    if _p.get("Tier") in ("SOVEREIGN","ELITE"):
                        _already = any(
                            normalize_name(l.get("player",""))==normalize_name(_p.get("Player","")) and
                            str(l.get("line",""))==str(_p.get("Line",""))
                            for l in st.session_state.get("locks", [])
                        )
                        if not _already:
                            st.session_state["locks"].append({
                                "player": _p.get("Player",""), "prop": _p.get("Prop",""),
                                "line": _p.get("Line",0), "side": _p.get("Side","OVER"),
                                "tier": _p.get("Tier",""), "edge": _p.get("Edge",0),
                                "sport": _sport, "source": "EV Optimizer",
                                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                "prob": _p.get("Prob",0.5),
                                "team": _p.get("Team",""),
                                "signal_values": _board_prop_signal_values(_p),
                                "clv_capture": _capture_clv_placement(_p.get("Player",""), _p.get("Prop",""), _p.get("Prob",0.5)),
                            })
                            try:
                                record_pinnacle_line(st.session_state["locks"][-1], _board)
                            except Exception:
                                pass
                save_json_data(LOCKS_PATH, st.session_state.locks)
                save_to_gist("locks", st.session_state.locks)  # persists across restarts
                st.success(f"Locked {len([p for p in _board if p.get('Tier') in ('SOVEREIGN','ELITE')])} plays")
                _bulk_teams = sorted(set(p.get("Team","") for p in _board if p.get("Tier") in ("SOVEREIGN","ELITE") and p.get("Team")))
                for _bulk_team in _bulk_teams:
                    _show_team_exposure_warning(_bulk_team, _sport)
                st.rerun()
        with _qa2:
            if st.button("📥 Export CSV", key="ev_export"):
                import pandas as _pd
                _export = [{
                    "Player": r["_player"], "Team": r["_team"],
                    "Prop": r["_prop"], "Line": r["_line"],
                    "Side": r["_side"], "Grade": r["_grade"],
                    "Edge%": r["_edge_pct"], "Model%": r["_model_prob"],
                    "L5": r["_l5"], "L10": r["_l10"], "Season": r["_szn"],
                    "Pinnacle": r["_pinn"], "DK": r["_dk"], "FD": r["_fd"],
                    "Signal": r["_mkt_signal"], "Unabated": r["_unabated"], "Reliability": r["_rel"],
                } for r in _rows]
                _csv = _pd.DataFrame(_export).to_csv(index=False)
                st.download_button("Download", _csv, "betcouncil_ev.csv", "text/csv", key="ev_dl")
        with _qa3:
            st.metric("Total Props", len(_rows),
                      delta=f"{len([r for r in _rows if r['_edge_pct'] >= 5])} above 5%")
# ----- TAB 2: GAME LINES -----
with tabs[3]:
    # Use game_analysis (has FavoriteTeam/FavoriteML/TotalEdge/recommendations)
    # Fall back to raw games if game_analysis not loaded yet
    _game_analysis_full = st.session_state.get("game_analysis", [])
    _raw_games = st.session_state.games or []
    _sport2 = st.session_state.get("last_sport", SPORTS[0]) or "NBA"
    # Only use game_analysis if it matches current sport — prevents stale cross-sport data
    _ga_sport = _game_analysis_full[0].get("Sport", _game_analysis_full[0].get("sport","")) if _game_analysis_full else ""
    _games = _game_analysis_full if (_game_analysis_full and _ga_sport == _sport2) else _raw_games
    st.markdown(f'<div class="bc-section-header">🏟️ Game Lines <span style="opacity:0.6;font-weight:400;">— {_sport2}</span></div>', unsafe_allow_html=True)

    # ── ODDS_API_KEY status warning ────────────────────────────────────────
    if _ODDS_API_KEY_STATUS == "missing":
        st.warning(
            "⚠️ **ODDS_API_KEY not configured** — Game lines source from SBR and "
            "BetOnline fallbacks only. Props and alt lines are unavailable. "
            "Add `ODDS_API_KEY` in Secrets to enable full odds coverage."
        )
    elif _ODDS_API_KEY_STATUS == "invalid":
        st.warning(
            "⚠️ **ODDS_API_KEY is invalid or expired** (HTTP 401/403 from api.the-odds-api.com). "
            "Game lines fall back to SBR/BetOnline. Update `ODDS_API_KEY` in Secrets."
        )

    # ── Sport-Specific Optimal Timing Window ─────────────────────────────
    try:
        from sport_timing_windows import optimal_window, opener_window
        _tw = optimal_window(_sport2)
        _ow = opener_window(_sport2)
    except Exception as _tw_err:
        _tw, _ow = {}, {}
        print(f"[WARN] sport_timing_windows: {_tw_err}")

    if _tw:
        st.info(f"⏰ **Optimal check-back window for {_sport2}:** {_tw['window_label']} — {_tw['reason']}")
    if _ow:
        st.caption(f"📖 **Opener strategy (soft line, lower limits):** {_ow['window_label']} — {_ow['reason']}")

    if _sport2.upper() == "MLB":
        try:
            from mlb_starter_bullpen_split import team_starter_bullpen_split_by_name
            _sb_signals = []
            _sb_teams_checked = set()
            for _g in (_games or [])[:15]:
                for _team in (_g.get("home"), _g.get("away")):
                    if not _team or _team in _sb_teams_checked:
                        continue
                    _sb_teams_checked.add(_team)
                    _split = team_starter_bullpen_split_by_name(_team)
                    if _split and _split.get("signal") != "NEUTRAL":
                        _sb_signals.append(_split)
        except Exception as _sb_err:
            _sb_signals = []
            print(f"[WARN] mlb_starter_bullpen_split: {_sb_err}")

        if _sb_signals:
            with st.expander(f"⚾ Starter vs Bullpen — {len(_sb_signals)} teams flagged", expanded=False):
                _sb_colors = {"FADE_FULL_GAME": "#e04040", "BET_FULL_GAME": "#22c55e", "SLIGHT_LEAN": "#e8a020"}
                for _s in _sb_signals[:15]:
                    _clr = _sb_colors.get(_s["signal"], "#6a7a8a")
                    st.markdown(
                        f'<div style="border-left:4px solid {_clr};background:var(--bc-bg);border-radius:4px;'
                        f'padding:0.5rem 0.9rem;margin-bottom:0.4rem;font-size:0.9rem;">'
                        f'<b>{_s["team"]}</b> — Starter ERA {_s["starter_era"]} / Bullpen ERA {_s["bullpen_era"]} '
                        f'(gap {_s["gap"]:+.2f}) — {_s["note"]}</div>',
                        unsafe_allow_html=True,
                    )

        try:
            from monthly_park_factors import compute_monthly_park_factors
            import datetime as _dt
            _pf_month = _dt.date.today().month
            _pf_data = compute_monthly_park_factors()
            _pf_rows = []
            for _g in (_games or [])[:15]:
                _home_t = _g.get("home")
                if not _home_t:
                    continue
                for _venue, _months in _pf_data.items():
                    if _home_t.lower() in _venue.lower() or _venue.lower() in _home_t.lower():
                        _factor = _months.get(_pf_month)
                        if _factor is not None:
                            _pf_rows.append({"team": _home_t, "venue": _venue, "factor": _factor})
                        break
        except Exception as _pf_err:
            _pf_rows = []
            print(f"[WARN] monthly_park_factors: {_pf_err}")

        if _pf_rows:
            with st.expander(f"🏟️ Monthly Park Factors — computed from real {_dt.date.today().year} game data", expanded=False):
                for _p in _pf_rows:
                    _lean = "hitter-friendly" if _p["factor"] > 1.03 else "pitcher-friendly" if _p["factor"] < 0.97 else "neutral"
                    st.markdown(
                        f'<div style="border-left:4px solid #a855f7;background:var(--bc-bg);border-radius:4px;'
                        f'padding:0.5rem 0.9rem;margin-bottom:0.4rem;font-size:0.9rem;">'
                        f'<b>{_p["venue"]}</b> ({_p["team"]}) — factor {_p["factor"]} this month, {_lean}</div>',
                        unsafe_allow_html=True,
                    )

    if _sport2.upper() == "TENNIS":
        try:
            from tennis_uts_scraper import fetch_player_surface_performance
            _tennis_rows = []
            _players_checked = set()
            for _g in (_games or [])[:10]:  # cap: sequential + rate-limited requests
                for _player in (_g.get("home"), _g.get("away")):
                    if not _player or _player in _players_checked:
                        continue
                    _players_checked.add(_player)
                    _perf = fetch_player_surface_performance(_player)
                    if _perf:
                        _tennis_rows.append({"player": _player, "surfaces": _perf})
        except Exception as _ten_err:
            _tennis_rows = []
            print(f"[WARN] tennis_uts_scraper: {_ten_err}")

        if _tennis_rows:
            with st.expander(f"🎾 Surface Breakdown — {len(_tennis_rows)} players (real UTS data)", expanded=False):
                for _t in _tennis_rows:
                    _parts = [f"{s}: {d['win_pct']}% ({d['wins']}-{d['losses']})" for s, d in _t["surfaces"].items()]
                    st.markdown(
                        f'<div style="border-left:4px solid #a855f7;background:var(--bc-bg);border-radius:4px;'
                        f'padding:0.5rem 0.9rem;margin-bottom:0.4rem;font-size:0.9rem;">'
                        f'<b>{_t["player"]}</b> — {" | ".join(_parts)}</div>',
                        unsafe_allow_html=True,
                    )

    if _sport2.upper() == "UFC":
        try:
            from unified_sharp_score import build_ufc_board
            _ufc_data = build_ufc_board()
        except Exception as _ufc_err:
            _ufc_data = {}
            print(f"[WARN] build_ufc_board: {_ufc_err}")

        if _ufc_data:
            with st.expander(f"🥊 Finish Rates by Weight Class — {len(_ufc_data)} classes (real data)", expanded=False):
                for _wc, _stats in sorted(_ufc_data.items(), key=lambda kv: kv[1]["finish_pct"], reverse=True):
                    st.markdown(
                        f'<div style="border-left:4px solid #e04040;background:var(--bc-bg);border-radius:4px;'
                        f'padding:0.5rem 0.9rem;margin-bottom:0.4rem;font-size:0.9rem;">'
                        f'<b>{_wc}</b> — {_stats["finish_pct"]}% finish ({_stats["ko_pct"]}% KO, {_stats["sub_pct"]}% sub) '
                        f'| {_stats["decision_pct"]}% decision (n={_stats["n_fights"]})</div>',
                        unsafe_allow_html=True,
                    )

    # ── Soccer Draw-Bias + NBA B2B Subtype (real data sources) ──────────
    if _sport2.upper() == "SOCCER":
        try:
            from fetchers import fetch_h2h_game_lines
            from soccer_draw_bias import parse_h2h_draw_odds
            _h2h_games, _, _, _ = fetch_h2h_game_lines("Soccer")
            _draw_signals = []
            for _g in _h2h_games:
                _dv = parse_h2h_draw_odds(_g)
                if _dv and _dv.get("undervalued"):
                    _draw_signals.append({"matchup": _g.get("Matchup"), **_dv})
        except Exception as _db_err:
            _draw_signals = []
            print(f"[WARN] soccer_draw_bias: {_db_err}")

        if _draw_signals:
            with st.expander(f"⚽ Draw Value — {len(_draw_signals)} undervalued draws", expanded=False):
                for _d in _draw_signals[:10]:
                    st.markdown(
                        f'<div style="border-left:4px solid #a855f7;background:var(--bc-bg);border-radius:4px;'
                        f'padding:0.5rem 0.9rem;margin-bottom:0.4rem;font-size:0.9rem;">'
                        f'<b>{_d["matchup"]}</b> — {_d["note"]}</div>',
                        unsafe_allow_html=True,
                    )

    if _sport2.upper() == "NBA":
        try:
            from nba_b2b_classifier import classify_b2b, fetch_team_recent_games
            from nba_rest_asymmetry import classify_rest_asymmetry
            _b2b_signals = []
            _rest_signals = []
            _teams_checked = set()
            _team_games_cache = {}
            for _g in (_games or [])[:15]:  # cap: avoid excessive ESPN calls per rerun
                _home_t, _away_t = _g.get("home"), _g.get("away")
                for _team in (_home_t, _away_t):
                    if not _team or _team in _teams_checked:
                        continue
                    _teams_checked.add(_team)
                    _recent = fetch_team_recent_games(_team, "NBA")
                    _team_games_cache[_team] = _recent
                    _cls = classify_b2b(_recent)
                    if _cls:
                        _b2b_signals.append({"team": _team, **_cls})
                if _home_t and _away_t and _home_t in _team_games_cache and _away_t in _team_games_cache:
                    _ra = classify_rest_asymmetry(_team_games_cache[_home_t], _team_games_cache[_away_t])
                    if _ra and _ra.get("favored_side"):
                        _rest_signals.append({"matchup": f"{_away_t} @ {_home_t}", **_ra})
        except Exception as _b2b_err:
            _b2b_signals, _rest_signals = [], []
            print(f"[WARN] nba_b2b_classifier/rest_asymmetry: {_b2b_err}")

        if _b2b_signals:
            with st.expander(f"🏀 B2B Subtypes — {len(_b2b_signals)} teams flagged", expanded=False):
                for _b in _b2b_signals[:15]:
                    st.markdown(
                        f'<div style="border-left:4px solid #e8a020;background:var(--bc-bg);border-radius:4px;'
                        f'padding:0.5rem 0.9rem;margin-bottom:0.4rem;font-size:0.9rem;">'
                        f'<b>{_b["team"]}</b> — {_b["note"]} (adj: {_b["point_adjustment"]:+.1f} pts)</div>',
                        unsafe_allow_html=True,
                    )

        if _rest_signals:
            with st.expander(f"😴 Rest Asymmetry — {len(_rest_signals)} matchups flagged", expanded=False):
                for _r in _rest_signals[:15]:
                    _fh_str = f" | +{_r['first_half_bonus']:.1f} pts 1H bonus" if _r.get("first_half_bonus") else ""
                    st.markdown(
                        f'<div style="border-left:4px solid #378add;background:var(--bc-bg);border-radius:4px;'
                        f'padding:0.5rem 0.9rem;margin-bottom:0.4rem;font-size:0.9rem;">'
                        f'<b>{_r["matchup"]}</b> — {_r["note"]} (adj: {_r["point_adjustment"]:+.1f} pts{_fh_str}, '
                        f'home rest {_r["home_rest_days"]}d / away rest {_r["away_rest_days"]}d)</div>',
                        unsafe_allow_html=True,
                    )

        try:
            from nba_pace_mismatch import score_pace_mismatch, load_pace_data
            _pace_data = load_pace_data()
            _pace_signals = []
            if _pace_data:
                for _g in (_games or [])[:15]:
                    _home_t, _away_t = _g.get("home"), _g.get("away")
                    if not _home_t or not _away_t:
                        continue
                    _favored = "HOME" if _g.get("home_favorite") else ("AWAY" if _g.get("away_favorite") else None)
                    _pm = score_pace_mismatch(_home_t, _away_t, favored_side=_favored, pace_data=_pace_data)
                    if _pm.get("is_mismatch"):
                        _pm["home_team"] = _home_t
                        _pace_signals.append({"matchup": f"{_away_t} @ {_home_t}", **_pm})
        except Exception as _pace_err:
            _pace_signals = []
            print(f"[WARN] nba_pace_mismatch: {_pace_err}")

        if _pace_signals:
            with st.expander(f"⚡ Pace Mismatches — {len(_pace_signals)} flagged", expanded=False):
                for _p in _pace_signals[:15]:
                    _lean_str = f" → <b>{_p['total_lean']}</b>" if _p.get("total_lean") else ""
                    _fast_pace = _p["home_pace"] if _p["fast_team"] == _p.get("home_team") else _p["away_pace"]
                    st.markdown(
                        f'<div style="border-left:4px solid #22c55e;background:var(--bc-bg);border-radius:4px;'
                        f'padding:0.5rem 0.9rem;margin-bottom:0.4rem;font-size:0.9rem;">'
                        f'<b>{_p["matchup"]}</b> — {_p["fast_team"]} ({_fast_pace}) '
                        f'vs {_p["slow_team"]}{_lean_str}</div>',
                        unsafe_allow_html=True,
                    )

    # ── Originator-Follower Lag + Information Asymmetry ──────────────────
    # Both record a timestamped snapshot every board load (building real
    # history automatically) and only surface once enough history exists.
    try:
        from market_microstructure import (
            record_odds_snapshot, compute_originator_scores,
            record_public_betting_snapshot, detect_info_asymmetry,
        )
        record_odds_snapshot(_sport2)
        record_public_betting_snapshot(_sport2)
        _orig_scores = compute_originator_scores(_sport2)
        _asym_signals = detect_info_asymmetry(_sport2)
    except Exception as _mm_err:
        _orig_scores, _asym_signals = {}, []
        print(f"[WARN] market_microstructure: {_mm_err}")

    if _orig_scores:
        with st.expander(f"⏱️ Originator-Follower Scores — {len(_orig_scores)} books tracked", expanded=False):
            st.caption(
                "⚠️ Coarse signal: snapshots are taken every 15 minutes, so if multiple books "
                "moved within the same window, whichever happens to be recorded first gets credited "
                "as the 'originator' — not a true sub-minute leader/follower read. Directionally "
                "suggestive over many samples, not something to trust on any single game."
            )
            for _book, _score in sorted(_orig_scores.items(), key=lambda kv: kv[1], reverse=True):
                st.markdown(f"**{_book}**: {_score*100:.0f}% of moves led")

    if _asym_signals:
        with st.expander(f"⚡ Information Asymmetry — {len(_asym_signals)} volume spikes flagged", expanded=False):
            for _a in _asym_signals[:10]:
                st.markdown(
                    f'<div style="border-left:4px solid #e8a020;background:var(--bc-bg);border-radius:4px;'
                    f'padding:0.5rem 0.9rem;margin-bottom:0.4rem;font-size:0.9rem;">'
                    f'<b>{_a["game"]}</b> — {_a["side"]}: money% jumped {_a["money_delta_pts"]:+.1f}pts '
                    f'(tickets only {_a["tickets_delta_pts"]:+.1f}pts) over {_a["minutes_between_snapshots"]}min '
                    f'→ now {_a["current_money_pct"]}% money / {_a["current_tickets_pct"]}% tickets'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    # ── TeamRankings Situational Signals (KillerSports replacement, unlimited) ──
    try:
        from teamrankings_situational import fetch_situational_signals
        _tr_signals = fetch_situational_signals(_sport2)
    except Exception as _tr_err:
        _tr_signals = []
        print(f"[WARN] teamrankings_situational: {_tr_err}")

    if _tr_signals:
        with st.expander(f"📐 Situational Trends — {len(_tr_signals)} significant (90%+ confidence)", expanded=False):
            for _t in _tr_signals[:15]:
                st.markdown(
                    f'<div style="border-left:4px solid #378add;background:var(--bc-bg);border-radius:4px;'
                    f'padding:0.5rem 0.9rem;margin-bottom:0.4rem;font-size:0.9rem;">'
                    f'<b>{_t["team"]}</b> — {_t["record"]} ({_t["win_rate"]*100:.1f}%) in '
                    f'{_t["trend_type"].replace("_"," ")} / {_t["filter"].replace("_"," ")} '
                    f'| z={_t["z_score"]} ({_t["confidence"]}) → <b>{_t["signal"]}</b>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    # ── Arbitrage Detector (real cross-book, guaranteed-profit signals) ──
    try:
        from arbitrage_detector import find_arbitrage
        _arbs = find_arbitrage(_sport2)
    except Exception as _arb_err:
        _arbs = []
        print(f"[WARN] arbitrage_detector: {_arb_err}")

    if _arbs:
        with st.expander(f"💰 Arbitrage Opportunities — {len(_arbs)} found", expanded=False):
            for _a in _arbs[:10]:
                st.markdown(
                    f'<div style="border-left:4px solid #22c55e;background:var(--bc-bg);border-radius:4px;'
                    f'padding:0.6rem 0.9rem;margin-bottom:0.5rem;">'
                    f'<b>{_a["game"]}</b> — {_a["market"]} | Profit: {_a["profit_pct"]:.2f}%<br>'
                    f'{_a["side_a"]["side"]} {_a["side_a"]["odds"]} @ {_a["side_a"]["book"]} '
                    f'&nbsp;|&nbsp; {_a["side_b"]["side"]} {_a["side_b"]["odds"]} @ {_a["side_b"]["book"]}'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    # ── Unified Sharp Score board (Scanbet CLV/steam + Action Network RLM) ──
    try:
        from unified_sharp_score import build_unified_sharp_board as _build_usb
        _usb = _build_usb(_sport2)
    except Exception as _usb_err:
        _usb = []
        print(f"[WARN] unified_sharp_score (Game Lines tab): {_usb_err}")

    if _usb:
        _usb_tier_colors = {"STRONG": "#e04040", "MODERATE": "#e8a020", "WEAK": "#6a7a8a"}
        with st.expander(f"🎯 Unified Sharp Signals — {len(_usb)} games flagged", expanded=False):
            for _u in _usb[:10]:
                _tclr = _usb_tier_colors.get(_u["tier"], "#6a7a8a")
                _lines = []
                for _c in _u["clv_signals"][:3]:
                    if _c.get("type") == "KEY_NUMBER":
                        _lines.append(f"🎯 KEY NUMBER | {_c['market']} {_c['opener_value']}→{_c['current_value']} | {_c['note']}")
                        continue
                    _bayes_str = f" | Bayes: {_c['bayesian_posterior']*100:.1f}%" if _c.get("bayesian_posterior") is not None else ""
                    _lines.append(f"📡 CLV {_c['drop_pct']:+.1f}% | {_c['selection']} ({_c['n_snapshots']} snaps){_bayes_str}")
                for _s in _u["steam_signals"][:2]:
                    _lines.append(f"🌊 STEAM | {_s['selection']} moving fast ({_s['n_snapshots']} snaps)")
                for _r in _u["rlm_signals"][:2]:
                    _lines.append(f"🔴 RLM | {_r['public_pct']}% public {_r['public_side']}, sharp $ on {_r['sharp_side']}")
                _body = "<br>".join(_lines) if _lines else "No signal breakdown available"
                _dir_line = f"<br>→ Consensus: sharp money on <b>{_u['consensus_direction']}</b>" if _u.get("consensus_direction") else ""
                _cause = _u.get("movement_cause", {})
                _cause_line = f"<br>🔎 Cause: <b>{_cause.get('cause','UNCLEAR')}</b> ({_cause.get('confidence',0)*100:.0f}% conf)" if _cause else ""
                _timing = _u.get("timing", {})
                _timing_line = f"<br>⏳ {_timing.get('action','')}: {_timing.get('reason','')} | Kelly ×{_u.get('kelly_multiplier',1.0)}" if _timing else ""
                st.markdown(
                    f'<div style="border-left:4px solid {_tclr};background:var(--bc-bg);border-radius:4px;'
                    f'padding:0.6rem 0.9rem;margin-bottom:0.5rem;">'
                    f'<b>{_u["game_label"]}</b> — Score: {_u["total_score"]:.1f} ({_u["tier"]})<br>'
                    f'{_body}{_dir_line}{_cause_line}{_timing_line}</div>',
                    unsafe_allow_html=True,
                )

    # ── Module Status Panel — single summary of everything above ────────
    try:
        from diagnostics_panel import render_diagnostics
        _diag_candidates = [
            "_usb", "_arbs", "_tr_signals", "_b2b_signals", "_rest_signals",
            "_pace_signals", "_sb_signals", "_pf_rows", "_draw_signals",
            "_ufc_data", "_tennis_rows",
        ]
        _local_scope = locals()
        _diag_vars = {name: _local_scope[name] for name in _diag_candidates if name in _local_scope}
        render_diagnostics(_sport2, _diag_vars)
    except Exception as _diag_err:
        print(f"[WARN] diagnostics_panel: {_diag_err}")

    # Slip grouping controls
    _slip_ctrl1, _slip_ctrl2, _slip_ctrl3 = st.columns([2,2,3])
    with _slip_ctrl1:
        if st.button("🎯 Start New Slip", key="start_new_slip", use_container_width=True):
            st.session_state["current_slip_id"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            st.success(f"New slip started — lock your picks")
    with _slip_ctrl2:
        if st.button("✅ End Slip", key="end_slip", use_container_width=True):
            st.session_state["current_slip_id"] = None
            st.success("Slip closed — next lock starts a new slip")
    with _slip_ctrl3:
        _cur_slip = st.session_state.get("current_slip_id")
        if _cur_slip:
            _slip_locks_count = sum(1 for l in st.session_state.get("locks", []) if l.get("timestamp","") == _cur_slip)
            st.markdown(f'<div style="background:var(--bc-bg);border:1px solid #22c55e44;border-radius:6px;padding:0.4rem 0.8rem;font-size:0.9rem;color:#22c55e;">📎 Active slip: {_slip_locks_count} picks locked</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div style="background:var(--bc-bg);border:1px solid var(--bc-border);border-radius:6px;padding:0.4rem 0.8rem;font-size:0.9rem;color:var(--bc-dim);">No active slip — tap Start New Slip to group picks</div>', unsafe_allow_html=True)

    if _games:
        _game_sports = list(set(g.get("Sport",_sport2) for g in _games))
        _gl_filt_col1, _gl_filt_col2 = st.columns([3, 1])
        with _gl_filt_col1:
            _gsf = st.multiselect("Filter by Sport", _game_sports, default=_game_sports, key="gl_sport")
        with _gl_filt_col2:
            _gl_sort = st.selectbox("Sort by", ["Time", "Best Edge", "Movement"], key="gl_sort")
        _fgames = [g for g in _games if g.get("Sport",_sport2) in (_gsf or _game_sports)]

        # Real sort keys -- best edge is the largest-magnitude edge across
        # the 3 real per-market fields already on each game (spread/total/
        # moneyline), not a fabricated composite score.
        def _gl_best_edge(g):
            return max(abs(float(g.get("SpreadEdge", 0) or 0)), abs(float(g.get("TotalEdge", 0) or 0)), abs(float(g.get("MLEdge", 0) or 0)))
        if _gl_sort == "Best Edge":
            _fgames = sorted(_fgames, key=_gl_best_edge, reverse=True)
        elif _gl_sort == "Movement":
            # Real movement signal from the same function already used per-
            # game below (get_line_movement_summary) -- games with a real
            # detected movement direction sort first, not a fabricated
            # magnitude proxy from unrelated edge fields.
            def _gl_has_movement(g):
                _m = _g_matchup = g.get("matchup", g.get("Matchup", "—"))
                _lm = get_line_movement_summary(_m, g.get("Sport", _sport2), g)
                return 1 if (_lm or {}).get("direction") else 0
            _fgames = sorted(_fgames, key=_gl_has_movement, reverse=True)
        _tc2 = TIER_COLORS

        # ── Game Lines hero card: single best-edge pick across today's
        # slate, real data only. Same visual language already proven on
        # Full Board's Spotlight card (accent bar, tier color) and
        # Summary's Hit Rate gauge (conic-gradient circle) -- reusing
        # both rather than inventing new CSS. Only shows a market that
        # actually has a real pick (SpreadPick/TotalPick/MLPick present),
        # not just a nonzero edge number with no real recommendation text.
        _gl_hero = None
        _gl_hero_edge = 0.0
        for _hg in _fgames:
            for _mkt, _pick_key, _tier_key, _edge_key in (
                ("SPREAD", "SpreadPick", "SpreadTier", "SpreadEdge"),
                ("TOTAL", "TotalPick", "TotalTier", "TotalEdge"),
                ("ML", "MLPick", "MLTier", "MLEdge"),
            ):
                _pick_txt = _hg.get(_pick_key)
                if not _pick_txt:
                    continue
                _e = abs(float(_hg.get(_edge_key, 0) or 0))
                if _e > _gl_hero_edge:
                    _gl_hero_edge = _e
                    _gl_hero = {
                        "matchup": _hg.get("matchup", _hg.get("Matchup", "—")),
                        "market": _mkt, "pick_text": _pick_txt,
                        "tier": _hg.get(_tier_key, "—"), "edge": _e,
                        "time": _hg.get("Time", _hg.get("time", "")),
                    }

        if _gl_hero and _gl_hero["tier"] in ("SOVEREIGN", "ELITE"):
            _gl_hero_tc = TIER_COLORS.get(_gl_hero["tier"], "#6a7a8a")
            # No real per-game win-probability field exists (unlike player
            # props, which have a genuine _model_prob) -- the ring shows the
            # real edge % directly rather than inventing a confidence score.
            # Scaled against a 15% ceiling (consistent with the same edge
            # ceiling already used for the Full Board heatmap intensity)
            # purely for the ring's fill amount, not the displayed number.
            _gl_edge_pct = _gl_hero["edge"] * 100
            _gl_ring_deg = min(1.0, _gl_edge_pct / 15.0) * 360
            _gl_time_suffix = f' · {_gl_hero["time"]}' if _gl_hero.get("time") else ""
            st.markdown(
                f'<div class="command-card" style="text-align:left;padding:18px 22px;margin-bottom:14px;'
                f'border-left:4px solid {_gl_hero_tc};display:flex;justify-content:space-between;align-items:center;'
                f'background:linear-gradient(135deg,var(--bc-bg-card) 0%,{_gl_hero_tc}14 140%);">'
                f'<div>'
                f'<div class="command-label" style="color:{_gl_hero_tc};">THE CALL — {_sport2}</div>'
                f'<div style="font-size:1.4rem;font-weight:800;color:var(--bc-text);margin-top:4px;">{_gl_hero["pick_text"]}</div>'
                f'<div style="font-size:0.85rem;color:var(--bc-dim);margin-top:4px;">{_gl_hero["matchup"]} · {_gl_hero["market"]}{_gl_time_suffix}</div>'
                f'<div style="font-size:0.7rem;color:{_gl_hero_tc};font-weight:700;text-transform:uppercase;margin-top:6px;">{_gl_hero["tier"]}</div>'
                f'</div>'
                f'<div style="width:72px;height:72px;border-radius:50%;background:conic-gradient({_gl_hero_tc} {_gl_ring_deg:.0f}deg, rgba(255,255,255,0.08) 0deg);display:flex;align-items:center;justify-content:center;flex-shrink:0;">'
                f'<div style="width:58px;height:58px;border-radius:50%;background:var(--bc-bg-card);display:flex;flex-direction:column;align-items:center;justify-content:center;">'
                f'<div style="font-weight:800;font-size:1.1rem;color:#ffffff;">{_gl_edge_pct:.1f}%</div>'
                f'<div style="font-size:0.5rem;color:var(--bc-dim);text-transform:uppercase;">edge</div>'
                f'</div></div>'
                f'</div>',
                unsafe_allow_html=True
            )

        # Real multi-point line-movement history for the momentum sparkline
        # below -- each board load already writes a new timestamped snapshot
        # via store_game_board_snapshot(), so today's snapshots give genuine
        # intraday points, not just the single open-vs-current comparison
        # get_line_movement_summary() uses. Loaded once here, not per-game.
        _gl_today_key = date.today().strftime("%Y-%m-%d")
        _gl_snaps_raw = load_from_gist("game_board_snapshots", None) or {}
        _gl_today_snaps = sorted(
            (v for k, v in _gl_snaps_raw.items() if v.get("date") == _gl_today_key),
            key=lambda v: v.get("timestamp", ""),
        )

        _gl_per_sport_fetch_cache = {}
        for _gi, _g in enumerate(_fgames):
            _matchup = _g.get("matchup", _g.get("Matchup","—"))
            _gsport = _g.get("Sport",_sport2)
            if _gsport not in _gl_per_sport_fetch_cache:
                _gl_per_sport_fetch_cache[_gsport] = {
                    "betql": fetch_betql_from_gist(_gsport),
                    "pickswise": fetch_pickswise_picks_from_gist(_gsport),
                    "wgt": fetch_wiseguyteam_from_gist(_gsport),
                    "betslib": fetch_betslib_predictions(_gsport),
                    "signalodds_arb": fetch_signalodds_arbitrage_from_gist(),
                }
            _line_movement = get_line_movement_summary(_matchup, _gsport, _g)
            _gtime = _g.get("Time","—")
            _injury = _g.get("Injury","")
            _alt_line = _g.get("AltLine","")
            _alt_edge = float(_g.get("AltEdge",0) or 0)
            _alt_tier = _g.get("AltTier","LEAN")
            _picks = [
                {"label":"SPREAD",
                 "pick":(_g.get("SpreadPick") or
                         ("No Market" if _g.get("Spread","N/A") in ("N/A","",None)
                          else (
                              # Show which team covers: home team covers negative spread
                              (_g.get("home","") + " " + str(_g.get("Spread",""))) if (
                                  _g.get("home") and
                                  str(_g.get("Spread","")).lstrip("+-").replace(".","").isdigit() and
                                  float(str(_g.get("Spread","0")).replace("+","")) < 0
                              ) else (
                                  (_g.get("away","") + " " + str(_g.get("Spread",""))) if (
                                      _g.get("away") and
                                      str(_g.get("Spread","")).lstrip("+-").replace(".","").isdigit()
                                  ) else _g.get("Spread","—")
                              )
                          ))),
                 "note": ("" if _g.get("SpreadPick") else
                          ("" if _g.get("Spread","N/A") in ("N/A","",None)
                           else ("" if any(r.get("type")=="SPREAD" for r in _g.get("recommendations",[]))
                                else "No Edge"))),
                 "line":(_g.get("SpreadLineHome") if _g.get("SpreadLineHome") is not None else _g.get("Spread","—")),"edge":float(_g.get("SpreadEdge",0) or 0),"tier":_g.get("SpreadTier","—") if _g.get("SpreadPick") or float(_g.get("SpreadEdge",0) or 0) != 0 else "—"},
                {"label":"TOTAL",
                 "pick":(_g.get("TotalPick") or
                         ("No Market" if _g.get("Total","N/A") in ("N/A","",None)
                          else (
                              # Show OVER/UNDER direction from recommendations or edge sign
                              next((r.get("pick","") for r in _g.get("recommendations",[])
                                    if r.get("type")=="TOTAL"), None) or
                              (("OVER " if float(_g.get("TotalEdge",0) or 0) > 0 else
                               "UNDER " if float(_g.get("TotalEdge",0) or 0) < 0 else "O/U ")
                              + str(_g.get("Total","")))
                          ))),
                 "note": ("" if _g.get("TotalPick") else
                          ("" if _g.get("Total","N/A") in ("N/A","",None)
                           else ("" if any(r.get("type")=="TOTAL" for r in _g.get("recommendations",[]))
                                else "No Edge"))),
                 "line":_g.get("Total",_g.get("OverUnder","—")),"edge":float(_g.get("TotalEdge",0) or 0),"tier":_g.get("TotalTier","—") if _g.get("TotalPick") or float(_g.get("TotalEdge",0) or 0) != 0 else "—"},
                {"label":"ML",
                 "pick":(_g.get("MLPick") or
                         ("No Market" if _g.get("HomeML","N/A") in ("N/A","",None)
                          else (
                              # Show favorite team + ML odds. Bug fix (2026-07):
                              # this used to be `(FavoriteTeam+" "+FavoriteML).strip() or <rebuild>`,
                              # but if FavoriteTeam was empty while FavoriteML had a
                              # real value, the stripped result was still a non-empty
                              # (team-less) string like "-131" — truthy in Python, so
                              # the `or` never fell through to the team-name rebuild
                              # below. Explicitly require FavoriteTeam to be present.
                              (_g.get("FavoriteTeam","") + " " + _g.get("FavoriteML","")).strip()
                              if _g.get("FavoriteTeam") else
                              # Rebuild from home/away + ML odds
                              # home/away may be full names (from game_analysis) or abbrevs (from raw games)
                              ((_g.get("home","") + " " + str(_g.get("HomeML","")))
                               if (str(_g.get("HomeML","0")).replace("+","").lstrip("-").isdigit() and
                                   str(_g.get("AwayML","0")).replace("+","").lstrip("-").isdigit() and
                                   float(str(_g.get("HomeML","0")).replace("+","")) <= float(str(_g.get("AwayML","0")).replace("+","")))
                               else (_g.get("away","") + " " + str(_g.get("AwayML",""))))
                          ))),
                 "note": ("" if _g.get("MLPick") else
                          ("" if _g.get("HomeML","N/A") in ("N/A","",None)
                           else ("" if any(r.get("type")=="MONEYLINE" for r in _g.get("recommendations",[]))
                                else "No Edge"))),
                 "line":_g.get("HomeML",_g.get("ML","—")),"edge":float(_g.get("MLEdge",0) or 0),"tier":_g.get("MLTier","—") if _g.get("MLPick") or float(_g.get("MLEdge",0) or 0) != 0 else "—"},
                {"label": "ALT LINE",
                 "pick": _alt_line or (
                     # MLB/NHL: show Run Line (-1.5) with home team label
                     ((_g.get("home","") + " -1.5") if _gsport in ("MLB","NHL") and _g.get("home") else "—")
                 ),
                 # Clean home-relative number (see AltLineValue, fixed
                 # 2026-07-13) -- NOT _alt_line, which is a full descriptive
                 # string like "Pittsburgh Pirates -1.5 (-110)" and would
                 # crash float() in the resolver exactly like the SPREAD
                 # line bug did.
                 "line": (_g.get("AltLineValue") if _g.get("AltLineValue") is not None else (
                     _g.get("RunLineHome") or _g.get("OddsAPI Spread", 0) or 0
                 )),
                 "edge": _alt_edge, "tier": _alt_tier},
            ]
            # DEBUG: show ML data availability (remove after diagnosis)
            if st.session_state.get("show_ml_debug", False):
                st.caption(f"🔧 {_g.get('matchup','?')}: HomeML={_g.get('HomeML','MISSING')} AwayML={_g.get('AwayML','MISSING')} MLPick={_g.get('MLPick','MISSING')} MLEdge={_g.get('MLEdge','MISSING')} | keys with ML: {[k for k in _g.keys() if 'ml' in k.lower() or 'ML' in k]}")
            # Game card header
            _gl_agree = next((r.get("market_agreement") for r in _g.get("recommendations", []) if r.get("market_agreement")), None)
            _gl_agree_note = next((r.get("market_agreement_note") for r in _g.get("recommendations", []) if r.get("market_agreement_note")), "")
            _gl_n_books = max([r.get("n_books", 0) for r in _g.get("recommendations", [])] or [0])
            _gl_badge_color = {"STRONG_AGREE": "#22c55e", "MODERATE_AGREE": "#e8a020", "DISAGREE": "#e04040"}.get(_gl_agree, "#4a5a6a")
            _gl_badge_label = {"STRONG_AGREE": "✓ Market Agrees", "MODERATE_AGREE": "⚠ Mixed Signals", "DISAGREE": "🔥 Sharp/Public Split"}.get(_gl_agree, "")
            _gl_badge_html = (
                f'<span title="{_gl_agree_note}" style="font-size:11px;font-weight:600;padding:2px 8px;border-radius:10px;background:{_gl_badge_color}22;color:{_gl_badge_color};border:0.5px solid {_gl_badge_color}44;margin-left:auto;">{_gl_badge_label} ({_gl_n_books} books)</span>'
                if _gl_agree_note else ''
            )
            # Public betting % badge from SBR data
            _gl_pub_h = next((r.get("public_pct_home") for r in _g.get("recommendations", []) if r.get("public_pct_home") is not None), None)
            _gl_pub_a = next((r.get("public_pct_away") for r in _g.get("recommendations", []) if r.get("public_pct_away") is not None), None)
            _gl_svp   = next((r.get("sharp_vs_public") for r in _g.get("recommendations", []) if r.get("sharp_vs_public")), None)
            _gl_pin   = next((r.get("pinnacle_sharp") for r in _g.get("recommendations", []) if r.get("pinnacle_sharp")), None)
            _gl_vsin  = next((r.get("vsin_sharp") for r in _g.get("recommendations", []) if r.get("vsin_sharp")), None)
            _gl_pub_html = ""
            if _gl_pub_h is not None:
                _pub_color = "#e04040" if _gl_svp == "FADE_PUBLIC" else ("#e8a020" if _gl_svp == "WITH_PUBLIC" else "#4a7a9b")
                _pub_icon  = "🎯" if _gl_svp == "FADE_PUBLIC" else ("⚡" if _gl_svp == "WITH_PUBLIC" else "👥")
                _home_name = _g.get("matchup","").split(" @ ")[-1] if " @ " in _g.get("matchup","") else "Home"
                _gl_pub_html = f'<span style="font-size:11px;font-weight:600;padding:2px 8px;border-radius:10px;background:{_pub_color}22;color:{_pub_color};border:0.5px solid {_pub_color}44;margin-left:6px;" title="Public money: {_gl_pub_h}% on {_home_name}">{_pub_icon} {_gl_pub_h}%/{_gl_pub_a}% public</span>'
            # MC blend badge — shows when Monte Carlo simulation contributed to the edge
            _gl_mc_blend = any(r.get("mc_blend") for r in _g.get("recommendations", []))
            _gl_mc_html = (
                '<span style="font-size:11px;font-weight:600;padding:2px 8px;border-radius:10px;'
                'background:#7c3aed22;color:#a78bfa;border:0.5px solid #7c3aed44;margin-left:6px;" '
                'title="Monte Carlo simulation blended into edge calculation">🎲 MC</span>'
            ) if _gl_mc_blend else ""
            _gl_pin_html = ""
            if _gl_pin and _gl_pin.get("note"):
                _pin_ok   = _gl_pin.get("confirms", False)
                _pin_fade = not _pin_ok and _gl_pin.get("prob", 0.5) < 0.46
                _pin_color = "#22c55e" if _pin_ok else ("#e04040" if _pin_fade else "#7f77dd")
                _pin_icon  = "📌✓" if _pin_ok else ("📌✗" if _pin_fade else "📌~")
                _gl_pin_html = (
                    f'<span title="{_gl_pin.get("note","")}" style="font-size:11px;font-weight:600;'
                    f'padding:2px 8px;border-radius:10px;background:{_pin_color}22;color:{_pin_color};'
                    f'border:0.5px solid {_pin_color}44;margin-left:6px;">{_pin_icon} Pinnacle</span>'
                )
            _gl_vsin_html = ""
            if _gl_vsin and _gl_vsin.get("note"):
                _vsin_ok   = _gl_vsin.get("confirms", False)
                _vsin_fade = not _vsin_ok and _gl_vsin.get("prob", 0.5) < 0.46
                _vsin_color = "#22c55e" if _vsin_ok else ("#e04040" if _vsin_fade else "#e8a020")
                _vsin_icon  = "🎰✓" if _vsin_ok else ("🎰✗" if _vsin_fade else "🎰~")
                _gl_vsin_html = (
                    f'<span title="{_gl_vsin.get("note","")}" style="font-size:11px;font-weight:600;'
                    f'padding:2px 8px;border-radius:10px;background:{_vsin_color}22;color:{_vsin_color};'
                    f'border:0.5px solid {_vsin_color}44;margin-left:6px;">{_vsin_icon} Nevada</span>'
                )
            _gl_row_best = max(_picks, key=lambda p: abs(p["edge"]))
            _gl_row_tc = _tc2.get(_gl_row_best["tier"], "#6a7a8a")
            _gl_row_edge_pct = _gl_row_best["edge"] * 100
            _gl_row_ring_deg = min(1.0, abs(_gl_row_edge_pct) / 15.0) * 360
            _gl_row_ring_html = (
                f'<div style="width:40px;height:40px;border-radius:50%;'
                f'background:conic-gradient({_gl_row_tc} {_gl_row_ring_deg:.0f}deg, rgba(255,255,255,0.08) 0deg);'
                f'display:flex;align-items:center;justify-content:center;flex-shrink:0;margin-left:auto;">'
                f'<div style="width:32px;height:32px;border-radius:50%;background:var(--bc-bg-card);'
                f'display:flex;flex-direction:column;align-items:center;justify-content:center;">'
                f'<div style="font-weight:800;font-size:0.68rem;color:#ffffff;">{_gl_row_edge_pct:.1f}%</div>'
                f'<div style="font-size:0.4rem;color:var(--bc-dim);text-transform:uppercase;">edge</div>'
                f'</div></div>'
            )
            # ── Verdict badge: how many independent external sources agree
            # with OUR OWN model's picks across ALL markets (spread/total/
            # ML), not just the single best-edge one. Combines the rich
            # internal edge/tier analysis above with all 5 relevant
            # external sources (BetQL/Pickswise/WiseGuyTeam/SignalOdds
            # predictions/SignalOdds arbitrage).
            _gl_verdict_html = ""
            _gl_age_html = ""
            try:
                _gl_betql_wrapper = _read_gist_file(f"betcouncil_betql_{_gsport}.json", cache_minutes=5)
                _gl_age_min = _gist_data_age_minutes(_gl_betql_wrapper)
                if _gl_age_min is not None:
                    _gl_age_str = f"{int(_gl_age_min)}m ago" if _gl_age_min < 60 else f"{_gl_age_min/60:.1f}h ago"
                    _gl_age_color = "#22c55e" if _gl_age_min < 30 else ("#e8a020" if _gl_age_min < 90 else "#e04040")
                    _gl_age_html = (
                        f'<span title="How fresh the underlying multi-book data is" '
                        f'style="font-size:10px;color:{_gl_age_color};margin-left:6px;">'
                        f'🕐 {_gl_age_str}</span>'
                    )
            except Exception:
                _gl_age_html = ""
            try:
                def _gl_norm_team(s):
                    s = re.sub(r"[+-]?\d+\.?\d*", "", str(s or ""))
                    return re.sub(r"[^a-z0-9]", "", s.lower())
                def _gl_teams_match(a, b):
                    na, nb = _gl_norm_team(a), _gl_norm_team(b)
                    return bool(na and nb and (na in nb or nb in na))

                # Every market of ours with a real pick (tier != "—"),
                # not just the single highest-edge one.
                _our_market_picks = [
                    p for p in _picks
                    if p.get("tier") not in (None, "—") and p.get("pick") not in (None, "", "—", "No Market", "No Edge")
                ]

                # Fetch each external source once per sport (cached above, not per game)
                _gl_sport_cache = _gl_per_sport_fetch_cache[_gsport]
                _ext_betql = next((g2 for g2 in _gl_sport_cache["betql"]
                                    if _gl_teams_match(g2.get("home_team",""), _g.get("home","")) and
                                       _gl_teams_match(g2.get("away_team",""), _g.get("away",""))), None)
                _ext_pickswise = next((g2 for g2 in _gl_sport_cache["pickswise"]
                                        if _gl_teams_match(g2.get("home_team",""), _g.get("home","")) and
                                           _gl_teams_match(g2.get("away_team",""), _g.get("away",""))), None)
                _ext_wgt = next((g2 for g2 in _gl_sport_cache["wgt"]
                                  if _gl_teams_match(g2.get("home_team",""), _g.get("home","")) and
                                     _gl_teams_match(g2.get("away_team",""), _g.get("away",""))), None)
                _ext_so_preds = [p2 for p2 in _gl_sport_cache["betslib"]
                                  if _gl_teams_match(p2.get("home",""), _g.get("home","")) and
                                     _gl_teams_match(p2.get("away",""), _g.get("away",""))]
                _ext_so_arb = [a2 for a2 in _gl_sport_cache["signalodds_arb"]
                               if not a2.get("locked") and
                                  _gl_teams_match(a2.get("home_team",""), _g.get("home","")) and
                                  _gl_teams_match(a2.get("away_team",""), _g.get("away",""))]

                _agree, _disagree, _checked = 0, 0, 0
                for _mp in _our_market_picks:
                    _our_pick_text = str(_mp.get("pick", ""))
                    _our_side_team = next(
                        (t for t in (_g.get("home", ""), _g.get("away", "")) if t and t in _our_pick_text),
                        None
                    )
                    _our_is_over = "OVER" in _our_pick_text.upper()
                    _our_is_under = "UNDER" in _our_pick_text.upper()

                    if _ext_betql and _our_side_team:
                        _ml2 = next((c for c in _ext_betql.get("community", []) if c.get("bet_type") == "moneyline"), None)
                        if _ml2:
                            _lean_home = _ml2.get("home_count", 0) > _ml2.get("away_count", 0)
                            _lean_team = _ext_betql.get("home_team") if _lean_home else _ext_betql.get("away_team")
                            _checked += 1
                            if _gl_teams_match(_lean_team, _our_side_team):
                                _agree += 1
                            else:
                                _disagree += 1

                    if _ext_pickswise and _ext_pickswise.get("pick_side") and _our_side_team:
                        _checked += 1
                        if _gl_teams_match(_ext_pickswise["pick_side"], _our_pick_text) or _gl_teams_match(_ext_pickswise["pick_side"], _our_side_team):
                            _agree += 1
                        else:
                            _disagree += 1

                    if _ext_wgt and _ext_wgt.get("has_sharp") and _our_side_team:
                        _flags = _ext_wgt.get("sharp_flags", [])
                        if "ml_side2" in _flags:
                            _checked += 1
                            if _gl_teams_match(_ext_wgt.get("home_team",""), _our_side_team):
                                _agree += 1
                            else:
                                _disagree += 1
                        elif "ml_side1" in _flags:
                            _checked += 1
                            if _gl_teams_match(_ext_wgt.get("away_team",""), _our_side_team):
                                _agree += 1
                            else:
                                _disagree += 1

                    for _sop in _ext_so_preds:
                        _sop_pick = _sop.get("pick", "")
                        if _sop_pick and _sop_pick in (_sop.get("home",""), _sop.get("away","")) and _our_side_team:
                            _checked += 1
                            if _gl_teams_match(_sop_pick, _our_side_team):
                                _agree += 1
                            else:
                                _disagree += 1
                            break

                    # Arbitrage doesn't imply a directional lean the way a
                    # pick does -- both sides of an arb are simultaneously
                    # "correct" by construction, so presence alone isn't
                    # agree/disagree signal. Not counted in the tally.

                if _checked > 0:
                    _v_color = "#22c55e" if _agree > _disagree else ("#e04040" if _disagree > _agree else "#e8a020")
                    _v_icon = "✅" if _agree > _disagree else ("❌" if _disagree > _agree else "➖")
                    _gl_verdict_html = (
                        f'<span title="External sources checked across all our graded markets for this game" '
                        f'style="font-size:11px;font-weight:600;padding:2px 8px;border-radius:10px;'
                        f'background:{_v_color}22;color:{_v_color};border:0.5px solid {_v_color}44;margin-left:6px;">'
                        f'{_v_icon} {_agree}/{_checked} sources agree</span>'
                    )
                    try:
                        _verdict_dir = "agree" if _agree > _disagree else ("disagree" if _disagree > _agree else "split")
                        _gl_game_date = str(_g.get("GameTime", "") or _g.get("game_time", ""))[:10] or date.today().strftime("%Y-%m-%d")
                        log_verdict_prediction(
                            _matchup, _g.get("home", ""), _g.get("away", ""), _gsport,
                            _gl_row_best.get("type", _gl_row_best.get("label", "")),
                            _gl_row_best.get("pick", ""), _gl_row_best.get("line", 0),
                            _gl_game_date, _verdict_dir, _agree, _checked
                        )
                    except Exception:
                        pass
            except Exception:
                _gl_verdict_html = ""
            _gl_logos_html = ""
            try:
                def _gl_logo_match(a, b):
                    na = re.sub(r"[^a-z0-9]", "", str(a or "").lower())
                    nb = re.sub(r"[^a-z0-9]", "", str(b or "").lower())
                    return bool(na and nb and (na in nb or nb in na))
                _gl_logo_map = fetch_espn_team_logos(_gsport)
                _gl_away_logo = next((url for name, url in _gl_logo_map.items() if _gl_logo_match(name, _g.get("away", ""))), "")
                _gl_home_logo = next((url for name, url in _gl_logo_map.items() if _gl_logo_match(name, _g.get("home", ""))), "")
                if _gl_away_logo:
                    _gl_logos_html += f'<img src="{_gl_away_logo}" style="width:24px;height:24px;object-fit:contain;" />'
                if _gl_home_logo:
                    _gl_logos_html += f'<span style="color:var(--bc-dim);margin:0 2px;">@</span><img src="{_gl_home_logo}" style="width:24px;height:24px;object-fit:contain;" />'
            except Exception:
                _gl_logos_html = ""
            st.markdown(
                f'<div style="background:var(--bc-bg-card);border-radius:6px 6px 0 0;border:0.5px solid #1e2d3d;border-bottom:none;padding:8px 14px;display:flex;align-items:center;gap:10px;margin-top:12px;">'
                f'<span style="font-size:19px;font-weight:700;letter-spacing:0.8px;color:var(--bc-blue);">{_gsport}</span>'
                + _gl_logos_html +
                f'<span style="font-size:18px;font-weight:700;color:var(--bc-text);">{_matchup}</span>'
                f'<span style="font-size:17px;color:var(--bc-dim);">{_gtime}</span>'
                + _gl_pub_html + _gl_mc_html + _gl_pin_html + _gl_vsin_html + _gl_badge_html + _gl_verdict_html + _gl_age_html + _gl_row_ring_html +
                f'</div>',
                unsafe_allow_html=True
            )
            try:
                def _og_match(a, b):
                    na = re.sub(r"[^a-z0-9]", "", str(a or "").lower())
                    nb = re.sub(r"[^a-z0-9]", "", str(b or "").lower())
                    return bool(na and nb and (na in nb or nb in na))
                _og_game = next((g2 for g2 in fetch_theoddsgap_lines_from_gist(_gsport)
                                  if _og_match(g2.get("home",""), _g.get("home","")) and
                                     _og_match(g2.get("away",""), _g.get("away",""))), None)
                if _og_game:
                    _og_parts = []
                    _og_ml = _og_game.get("ml")
                    if _og_ml:
                        _og_parts.append(f"ML: {_og_ml.get('away_best',{}).get('label','')} {_og_ml.get('away_best',{}).get('odds','')} / {_og_ml.get('home_best',{}).get('label','')} {_og_ml.get('home_best',{}).get('odds','')} ({_og_ml.get('n_books','?')} books)")
                    _og_sp = _og_game.get("spread")
                    if _og_sp:
                        _og_parts.append(f"Spread {_og_sp.get('line','')}: {_og_sp.get('home_best',{}).get('label','')} {_og_sp.get('home_best',{}).get('odds','')}")
                    _og_tot = _og_game.get("total")
                    if _og_tot:
                        _og_parts.append(f"O/U {_og_tot.get('line','')}: {_og_tot.get('over_best',{}).get('label','')} {_og_tot.get('over_best',{}).get('odds','')} / {_og_tot.get('under_best',{}).get('label','')} {_og_tot.get('under_best',{}).get('odds','')}")
                    if _og_parts:
                        st.caption("🔭 theoddsgap (19 books incl. Kalshi/Polymarket/ProphetX): " + " · ".join(_og_parts))
            except Exception:
                pass
            if _gsport == "MLB":
                try:
                    _ump_lineups = st.session_state.get("mlb_lineups", {})
                    _ump_key = next((k for k in _ump_lineups if _og_teams_match(_ump_lineups[k].get("home_team",""), _g.get("home","")) and _og_teams_match(_ump_lineups[k].get("away_team",""), _g.get("away",""))), None) if _ump_lineups else None
                    _ump_name = _ump_lineups.get(_ump_key, {}).get("hp_umpire", "") if _ump_key else ""
                    if not _ump_name:
                        _ump_name = next((v.get("hp_umpire","") for v in _ump_lineups.values() if _og_teams_match(v.get("home_team",""), _g.get("home","")) and _og_teams_match(v.get("away_team",""), _g.get("away",""))), "")
                    if _ump_name:
                        _ump_totals = _ump_totals_cache.get(_ump_name.strip().lower(), {})
                        _ump_avg = _ump_totals.get("avg_total_runs")
                        if _ump_avg is not None:
                            _ump_over = _ump_totals.get("over_rate_vs_85", 0)
                            _ump_n = _ump_totals.get("game_count", 0)
                            _ump_color = "#e04040" if (_ump_avg > 9.2 or _ump_over > 0.58) else ("#1e90ff" if (_ump_avg < 8.0 or _ump_over < 0.44) else "#6a7a8a")
                            st.markdown(f'<div style="font-size:0.8rem;color:{_ump_color};">⚾ HP Ump: {_ump_name} — {_ump_avg} R/G · {_ump_over:.0%} Over (n={_ump_n}, {datetime.now().year})</div>', unsafe_allow_html=True)
                except Exception:
                    pass
            if _gsport == "NFL":
                try:
                    _ll_state = fetch_leaguelogs_nfl_state()
                    if _ll_state.get("week") is not None:
                        _ll_phase = {"pre": "Preseason", "regular": "Regular Season", "post": "Postseason"}.get(_ll_state.get("seasonType"), "")
                        st.caption(f"🏈 NFL · Week {_ll_state['week']} · {_ll_phase}")
                except Exception:
                    pass
            if _gsport == "MLB":
                try:
                    _rlv_home_ml = float(str(_g.get("HomeML", "")).replace("+", "")) if str(_g.get("HomeML", "")).lstrip("+-").replace(".", "").isdigit() else None
                    _rlv_away_ml = float(str(_g.get("AwayML", "")).replace("+", "")) if str(_g.get("AwayML", "")).lstrip("+-").replace(".", "").isdigit() else None
                    _rlv_fav_ml, _rlv_fav_team = (None, None)
                    if _rlv_home_ml is not None and _rlv_away_ml is not None:
                        if _rlv_home_ml < 0 and _rlv_home_ml < _rlv_away_ml:
                            _rlv_fav_ml, _rlv_fav_team = _rlv_home_ml, _g.get("home", "")
                        elif _rlv_away_ml < 0 and _rlv_away_ml < _rlv_home_ml:
                            _rlv_fav_ml, _rlv_fav_team = _rlv_away_ml, _g.get("away", "")
                    if _rlv_fav_ml is not None and -155 <= _rlv_fav_ml <= -130:
                        st.caption(f"💰 Run Line value check: {_rlv_fav_team} ML {_rlv_fav_ml:+.0f} — favorite in ECU's run-line-value zone (check -1.5 RL price vs ML)")
                except Exception:
                    pass
                try:
                    _drt_scoring = fetch_team_recent_scoring()
                    for _drt_team in (_g.get("home", ""), _g.get("away", "")):
                        _drt_key = next((k for k in _drt_scoring if _og_teams_match(k, _drt_team)), None)
                        if not _drt_key:
                            continue
                        _drt_l4 = _drt_scoring[_drt_key][-4:]
                        if len(_drt_l4) == 4:
                            _drt_avg = sum(_drt_l4) / 4
                            if _drt_avg < 3.0:
                                st.markdown(f'<div style="font-size:0.8rem;color:#e04040;">🥶 {_drt_team}: {sum(_drt_l4)} runs in L4 ({_drt_avg:.1f} R/G) — drought fade candidate</div>', unsafe_allow_html=True)
                except Exception:
                    pass
            # 3-column picks
            _pc1, _pc2, _pc3, _pc4 = st.columns(4)
            for _idx, (_pc, _pk) in enumerate(zip([_pc1,_pc2,_pc3,_pc4], _picks)):
                with _pc:
                    _pc_color = _tc2.get(_pk["tier"],"#6a7a8a")
                    _is_pos = _pk["edge"] > 0
                    _edge_color = _pc_color if _is_pos else "#e04040"
                    _has_edge = abs(_pk["edge"]) >= 0.02
                    _lm = _line_movement if isinstance(_line_movement, dict) else {}
                    _lm_dir = _lm.get("direction", "")
                    _lm_arrow = (
                        '<span class="line-up">↑</span>' if _lm_dir == "up" else
                        '<span class="line-down">↓</span>' if _lm_dir == "down" else
                        '<span class="line-flat">–</span>'
                    ) if _lm else ""
                    # Momentum sparkline: real TOTAL-line value from this
                    # matchup across today's actual saved snapshots (not
                    # fabricated intermediate points). Needs 2+ distinct
                    # snapshots to draw anything.
                    _mom_svg = ""
                    _mom_vals = []
                    for _snap in _gl_today_snaps:
                        if _snap.get("sport") != _gsport:
                            continue
                        for _pk2 in _snap.get("picks", []):
                            if _pk2.get("matchup") == _matchup and _pk2.get("market") == "TOTAL":
                                _mom_vals.append(_pk2.get("line", 0))
                                break
                    if len(_mom_vals) >= 2 and len(set(_mom_vals)) >= 2:
                        _mv_min, _mv_max = min(_mom_vals), max(_mom_vals)
                        _mv_range = (_mv_max - _mv_min) or 1
                        _mv_w, _mv_h = 50, 16
                        _mv_pts = " ".join(
                            f"{i/(len(_mom_vals)-1)*_mv_w:.1f},{_mv_h - (v-_mv_min)/_mv_range*_mv_h:.1f}"
                            for i, v in enumerate(_mom_vals)
                        )
                        _mv_color = "#22c55e" if _mom_vals[-1] >= _mom_vals[0] else "#e04040"
                        _mom_svg = (f'<svg width="{_mv_w}" height="{_mv_h}" style="vertical-align:middle;margin-left:4px;">'
                                    f'<polyline points="{_mv_pts}" fill="none" stroke="{_mv_color}" stroke-width="1.5"/></svg>')
                    _gl_card_class = "gl-market-card has-edge" if _has_edge else "gl-market-card"
                    st.markdown(
                        f'<div class="{_gl_card_class}" style="border-left:3px solid {_pc_color};border:0.5px solid #1e2d3d;border-left:3px solid {_pc_color};padding:16px 18px;background:var(--bc-bg);">'
                        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">'
                        f'<span style="font-size:13px;font-weight:700;letter-spacing:1px;color:#6a8aab;text-transform:uppercase;">{_pk["label"]}</span>'
                        f'<span style="font-size:12px;font-weight:700;padding:3px 8px;border-radius:4px;background:{_pc_color}22;color:{_pc_color};border:0.5px solid {_pc_color}44;">{_pk["tier"]}</span>'
                        f'</div>'
                        f'<div style="display:flex;align-items:baseline;gap:8px;margin-bottom:6px;flex-wrap:wrap;">'
                        f'<span style="font-family:\'JetBrains Mono\',\'Fira Code\',\'Courier New\',monospace;font-size:19px;font-weight:700;color:#ffffff;">{_pk["pick"]}</span>'
                        f'<span style="font-family:\'JetBrains Mono\',\'Fira Code\',\'Courier New\',monospace;font-size:13px;color:#6a8aab;">{_pk["line"]}</span>'
                        f'{_lm_arrow}{_mom_svg}'
                        f'</div>'
                        + (f'<div style="font-size:12px;color:#e8a020;margin-bottom:3px;">{_pk.get("note","")}</div>' if _pk.get("note") else "")
                        + f'<span style="font-family:\'JetBrains Mono\',\'Fira Code\',\'Courier New\',monospace;font-size:15px;font-weight:700;color:{_edge_color};">{"+"+str(round(_pk["edge"]*100,1)) if _is_pos else str(round(_pk["edge"]*100,1))}% edge</span>'
                        f'</div>',
                        unsafe_allow_html=True
                    )
            if _injury:
                st.markdown(f'<div style="padding:5px 14px;font-size:14px;color:var(--bc-dim);border:0.5px solid #1e2d3d;border-top:none;border-radius:0 0 6px 6px;background:var(--bc-bg-card);">ℹ️ {_injury}</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div style="border:0.5px solid #1e2d3d;border-top:none;border-radius:0 0 6px 6px;height:4px;background:#08111a;"></div>', unsafe_allow_html=True)

            # Opening line vs current (ESPN capture, once/day) — real CLV context,
            # replaces the old dead "oddsportal" write that nothing ever read.
            _ol = st.session_state.get("opening_lines_lookup", {}).get(_matchup, {})
            if _ol and (_ol.get("opening_home_ml") is not None or _ol.get("opening_away_ml") is not None):
                _cur_total = (_g.get("total") or {}).get("points")
                _cur_spread = (_g.get("home_spread") or {}).get("points")
                _move_total_html = line_movement_html(_ol.get("opening_total"), _cur_total) if _cur_total is not None else ""
                _move_spread_html = line_movement_html(_ol.get("opening_spread"), _cur_spread) if _cur_spread is not None else ""
                st.caption(
                    f"📌 Opening: {_g.get('away','Away')} {_ol.get('opening_away_ml','—')} / "
                    f"{_g.get('home','Home')} {_ol.get('opening_home_ml','—')}"
                    + (f" · O/U {_ol['opening_total']}" if _ol.get("opening_total") is not None else "")
                )
                _move_parts = []
                if _move_total_html:
                    _move_parts.append(f"Total {_move_total_html}")
                if _move_spread_html:
                    _move_parts.append(f"Spread {_move_spread_html}")
                if _move_parts:
                    st.markdown(f'<div style="margin-top:-8px;margin-bottom:4px;">{" · ".join(_move_parts)}</div>', unsafe_allow_html=True)

            # Dimers model edge/win probability (via Stats Insider backend) —
            # independent second-source comparison, display only.
            try:
                _dimers_match = get_dimers_match(_matchup, _gsport)
            except Exception:
                _dimers_match = {}
            if _dimers_match:
                _dm_h_edge = _dimers_match.get("home_edge")
                _dm_a_edge = _dimers_match.get("away_edge")
                if isinstance(_dm_h_edge, (int, float)) and isinstance(_dm_a_edge, (int, float)):
                    _dm_side, _dm_edge, _dm_win = (
                        (_g.get("home", "Home"), _dm_h_edge, _dimers_match.get("home_win_pct"))
                        if _dm_h_edge > _dm_a_edge else
                        (_g.get("away", "Away"), _dm_a_edge, _dimers_match.get("away_win_pct"))
                    )
                    _dm_text = f"📊 Dimers: {_dm_side} edge {_dm_edge:+.1f}%"
                    if isinstance(_dm_win, (int, float)):
                        _dm_text += f" · win prob {_dm_win:.0%}"
                    st.caption(_dm_text)

            # MyBookie (public SSR HTML) — real-book line comparison, display only.
            try:
                _mb_match = get_mybookie_match(_matchup, _gsport)
            except Exception:
                _mb_match = {}
            if _mb_match and _mb_match.get("ml_odds"):
                _mb_text = f"📗 MyBookie: {_mb_match.get('ml_team','')} ML {_mb_match.get('ml_odds','')}"
                if _mb_match.get("total_points"):
                    _mb_text += f" · O/U {_mb_match['total_points']} ({_mb_match.get('total_odds','')})"
                st.caption(_mb_text)

            # VegasInsider (public trends + consensus, MLB only) — display only.
            try:
                _vi_match = get_vegasinsider_match(_matchup, _gsport)
            except Exception:
                _vi_match = {}
            if _vi_match:
                if _vi_match.get("trends"):
                    _vi_parts = [f'{t.get("team","")} {t.get("ml_pct","")} ML' for t in _vi_match["trends"][:2]]
                    st.caption(f"🌐 VegasInsider public %: {' vs '.join(_vi_parts)}")
                if _vi_match.get("open_ml") and _vi_match.get("consensus_ml"):
                    st.caption(f"🌐 VegasInsider line move: opened {_vi_match['open_ml']} → now {_vi_match['consensus_ml']}")

            # Sports Insights (public ticket %) — display only.
            try:
                _si_match = get_sportsinsights_match(_matchup, _gsport)
            except Exception:
                _si_match = {}
            if _si_match and _si_match.get("home_pct_ml") is not None:
                st.caption(
                    f"🎟️ Sports Insights: {_si_match.get('home_abv','')} {_si_match['home_pct_ml']}% ML tickets, "
                    f"{_si_match.get('home_pct_spread','?')}% spread, {_si_match.get('home_pct_ou','?')}% O/U "
                    f"({_si_match.get('total_bets','?')} bets)"
                )

            # ScoresAndOdds (11-book multi-book odds comparison) — display only.
            try:
                _sao_match = get_scoresandodds_match(_matchup, _gsport)
            except Exception:
                _sao_match = {}
            if _sao_match:
                _sao_ml = _sao_match.get("moneyline", {})
                _sao_sp = _sao_match.get("spread", {})
                _sao_to = _sao_match.get("total", {})
                _sao_text = f"📚 ScoresAndOdds ({len(_sao_ml.get('comparison', {}))} books): "
                if _sao_ml.get("home") is not None:
                    _sao_text += f"ML {_sao_match.get('home_team','')} {_sao_ml['home']}/{_sao_match.get('away_team','')} {_sao_ml.get('away','')}"
                if _sao_sp.get("value"):
                    _sao_text += f" · Spread {_sao_sp['value']}"
                if _sao_to.get("value"):
                    _sao_text += f" · O/U {_sao_to['value']}"
                st.caption(_sao_text)

            # Pickswise (expert picks + consensus odds) — display only.
            try:
                _pw_match = get_pickswise_match(_matchup, _gsport)
            except Exception:
                _pw_match = {}
            if _pw_match:
                if _pw_match.get("pick_side"):
                    _pw_stars = "★" * int(_pw_match.get("pick_rating") or 0)
                    _pw_text = f"✍️ Pickswise pick: {_pw_match['pick_side']} — {_pw_match.get('pick_bet','')} {_pw_stars}"
                    if _pw_match.get("pick_author"):
                        _pw_text += f" (by {_pw_match['pick_author']})"
                    st.caption(_pw_text)
                elif _pw_match.get("odds"):
                    st.caption(f"✍️ Pickswise: no pick published yet for this game ({len(_pw_match['odds'])} consensus odds lines available)")

            # Action Network (multi-book odds + starting pitcher stats) — display only.
            try:
                _an_match = get_actionnetwork_match(_matchup, _gsport)
            except Exception:
                _an_match = {}
            if _an_match and _an_match.get("odds"):
                _an_book = _an_match["odds"][0]
                _an_text = (
                    f"🔷 Action Network ({len(_an_match['odds'])} books): "
                    f"ML {_an_match.get('away_team','')} {_an_book.get('ml_away','')} / "
                    f"{_an_match.get('home_team','')} {_an_book.get('ml_home','')}"
                )
                if _an_book.get("total"):
                    _an_text += f" · O/U {_an_book['total']}"
                st.caption(_an_text)
                _an_sp = _an_match.get("starting_pitchers", {})
                for _side, _label in [("away", _an_match.get("away_team","Away")), ("home", _an_match.get("home_team","Home"))]:
                    _sp = _an_sp.get(_side)
                    if _sp and _sp.get("pitching"):
                        _era = _sp["pitching"].get("era")
                        _whip = _sp["pitching"].get("whip")
                        if _era:
                            st.caption(f"⚾ {_label} SP: ERA {_era}, WHIP {_whip}")

            # BetQL (multi-book lines + season/ATS records + community) — display only.
            try:
                _bq_match = get_betql_match(_matchup, _gsport)
            except Exception:
                _bq_match = {}
            if _bq_match:
                _bq_hr, _bq_ar = _bq_match.get("home_record", {}), _bq_match.get("away_record", {})
                if _bq_hr.get("atswins") is not None or _bq_ar.get("atswins") is not None:
                    st.caption(
                        f"📈 BetQL ATS: {_bq_match.get('away_team','')} {_bq_ar.get('atswins','?')}-{_bq_ar.get('atslosses','?')} · "
                        f"{_bq_match.get('home_team','')} {_bq_hr.get('atswins','?')}-{_bq_hr.get('atslosses','?')} "
                        f"({len(_bq_match.get('lines',[]))} books)"
                    )
                _bq_comm = _bq_match.get("community", [])
                _bq_ml = next((c for c in _bq_comm if c.get("bet_type") == "moneyline"), None)
                if _bq_ml and (_bq_ml.get("home_count") or _bq_ml.get("away_count")):
                    _bq_tot = _bq_ml.get("home_count", 0) + _bq_ml.get("away_count", 0)
                    if _bq_tot:
                        st.caption(
                            f"👥 BetQL community: {_bq_match.get('away_team','')} "
                            f"{_bq_ml.get('away_count',0)/_bq_tot:.0%} · "
                            f"{_bq_match.get('home_team','')} {_bq_ml.get('home_count',0)/_bq_tot:.0%} "
                            f"({_bq_tot} picks)"
                        )
                _bq_lines = _bq_match.get("lines", [])
                if len(_bq_lines) >= 2:
                    _bq_best_home_ml = max((l.get("home_ml") for l in _bq_lines if l.get("home_ml") is not None), default=None)
                    _bq_best_away_ml = max((l.get("away_ml") for l in _bq_lines if l.get("away_ml") is not None), default=None)
                    if _bq_best_home_ml is not None and _bq_best_away_ml is not None:
                        _bq_best_home_book = next((l.get("book") for l in _bq_lines if l.get("home_ml") == _bq_best_home_ml), "")
                        _bq_best_away_book = next((l.get("book") for l in _bq_lines if l.get("away_ml") == _bq_best_away_ml), "")
                        st.caption(
                            f"💵 BetQL best ML: {_bq_match.get('away_team','')} {_bq_best_away_ml:+d} ({_bq_best_away_book}) · "
                            f"{_bq_match.get('home_team','')} {_bq_best_home_ml:+d} ({_bq_best_home_book})"
                        )

            # Lock buttons for each bet type
            _lk_cols = st.columns(4)
            for _lk_idx, (_lk_col, _pk) in enumerate(zip(_lk_cols, _picks)):
                with _lk_col:
                    _glk_key = f"glk_{_gi}_{_pk['label']}"
                    _already_glk = any(
                        l.get("player","") == _matchup and l.get("prop","") == _pk["label"]
                        for l in st.session_state.get("locks", [])
                    )
                    if _already_glk:
                        st.markdown('<div style="text-align:center;color:#22c55e;font-size:15px;padding:4px;">✅ Locked</div>', unsafe_allow_html=True)
                    elif st.button(f"🔒 {_pk['label']}", key=_glk_key, use_container_width=True):
                        _new_game_lock = {
                            "player": _matchup,
                            "prop": _pk["label"],
                            "line": str(_pk["line"]),
                            "side": _pk["pick"],
                            "tier": _pk["tier"],
                            "edge": _pk["edge"],
                            "sport": _gsport,
                            "source": "Bovada/MyBookie",
                            "bet_type": "game",
                            "timestamp": st.session_state.get("current_slip_id") or datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "prob": 0.5 + _pk["edge"] / 2,
                            "wager": 0,
                            "clv_capture": _capture_clv_placement_game(_matchup, _pk["label"], _pk["pick"], _pk["line"]),
                        }
                        st.session_state["locks"].append(_new_game_lock)
                        try:
                            record_pinnacle_game_line(_new_game_lock, st.session_state.get("pinnacle_game_lines", []))
                        except Exception:
                            pass
                        save_json_data(LOCKS_PATH, st.session_state.locks)
                        if not save_to_gist("locks", st.session_state.locks):  # persists across restarts
                            st.warning("Locked locally, but the sync didn't go through — try again in a moment if it doesn't stick.")
                        st.rerun()

        # Keep line movement and public betting data below
        st.markdown("---")
        movement_data = st.session_state.get("game_line_movement", {})
        if movement_data:
            st.markdown("### ⚡ Line Movement & Multi-Book Comparison")
            for matchup, movements in movement_data.items():
                if not movements: continue
                with st.expander(matchup):
                    if len(movements) >= 2:
                        first, last = movements[-1], movements[0]
                        spread_moved = first.get("spread","") != last.get("spread","")
                        total_moved = first.get("over_under","") != last.get("over_under","")
                        st.markdown(f"**Spread:** {first.get('spread','—')} → {last.get('spread','—')} {'🔴 MOVED' if spread_moved else '✅ stable'}")
                        st.markdown(f"**Total:** {first.get('over_under','—')} → {last.get('over_under','—')} {'🔴 MOVED' if total_moved else '✅ stable'}")
                        # Show all providers
                        if len(movements) > 1:
                            st.caption("Books:")
                            for m in movements:
                                provider = m.get("provider","")
                                if provider:
                                    st.caption(f"  {provider}: Spread {m.get('spread','—')} | Total {m.get('over_under','—')} | ML {m.get('home_ml','—')}/{m.get('away_ml','—')}")
                    elif movements:
                        m = movements[0]
                        st.markdown(f"**Current:** Spread {m.get('spread','—')} | Total {m.get('over_under','—')} | ML {m.get('home_ml','—')}/{m.get('away_ml','—')}")
                        st.caption(f"Source: {m.get('provider','ESPN')}")
                        st.caption("⚠️ Only one snapshot available — load board again later to see movement direction.")

                    # Bovada comparison
                    _bov = get_bovada_game_line(matchup)
                    if _bov:
                        st.markdown("**Bovada:**")
                        _bc1, _bc2, _bc3 = st.columns(3)
                        _bc1.metric("ML", f"{_bov.get('away_ml','—')} / {_bov.get('home_ml','—')}")
                        _bc2.metric("Spread", f"{_bov.get('spread','—')} ({_bov.get('spread_odds','—')})")
                        _bc3.metric("Total", f"{_bov.get('total','—')} ({_bov.get('over_odds','—')} / {_bov.get('under_odds','—')})")

                    # ── Market move explanation ──────────────────────
                    # Pull from game_analysis if available
                    _ga_match = next((g for g in st.session_state.get("game_analysis",[])
                                      if g.get("matchup","").lower() == matchup.lower()), None)
                    if _ga_match:
                        _mmq  = int(_ga_match.get("MarketMoveQuality", 0) or 0) if hasattr(_ga_match, "get") else 0
                        _mmn  = _ga_match.get("MarketMoveNote","") if hasattr(_ga_match, "get") else ""
                        _pub  = _ga_match.get("public_data",{}) or {}
                        _rlm  = _ga_match.get("rlm_signals",[]) or []
                        if _mmn:
                            _mmq_color = "#22c55e" if _mmq >= 1 else "#e04040" if _mmq <= -1 else "#6a7a8a"
                            st.markdown(
                                f'<div style="background:var(--bc-bg-card);border-left:3px solid {_mmq_color};'
                                f'border-radius:4px;padding:5px 10px;margin-top:6px;">'
                                f'<span style="color:{_mmq_color};font-weight:600;">Movement Signal:</span> '
                                f'<span style="color:var(--bc-muted);font-size:12px;">{_mmn}</span></div>',
                                unsafe_allow_html=True
                            )
                        if _rlm:
                            for _rlm_item in _rlm[:1]:
                                st.markdown(
                                    f'<div style="background:var(--bc-bg-card);border-left:3px solid #22c55e;'
                                    f'border-radius:4px;padding:5px 10px;margin-top:4px;">'
                                    f'<span style="color:#22c55e;font-weight:600;">↔️ RLM Detected:</span> '
                                    f'<span style="color:var(--bc-muted);font-size:12px;">'
                                    f'{_rlm_item.get("public_pct",0)}% tickets on {_rlm_item.get("public_side","")} | '
                                    f'{_rlm_item.get("money_pct",0)}% money on {_rlm_item.get("sharp_side","")} ��� '
                                    f'sharp action moving against public</span></div>',
                                    unsafe_allow_html=True
                                )
                        # Public betting breakdown
                        _sharp_sigs = _pub.get("sharp_signals",[]) if isinstance(_pub,dict) else []
                        for _ss in _sharp_sigs[:2]:
                            if _ss:
                                st.caption(f"⚡ {_ss[:80]}")
        else:
            st.caption("Line movement loads with the board. If empty, ESPN odds data wasn't available for this game.")

        # ── Public vs Money Row ─────────────────────────────────
        # Sources: Action Network (public tickets % vs money %), Covers
        # (public pick %), Kalshi + Polymarket (prediction-market implied
        # probability), Pinnacle + VSIN (sharp-book signal, already computed
        # earlier for the header badges — surfaced here too now instead of
        # only in the compact pill).
        _pub_data = _g.get("public_data", {})
        _cov_data = st.session_state.get("covers_consensus", [])
        _home_nm, _away_nm = _g.get("home", ""), _g.get("away", "")

        # Match WiseGuyTeam sharp-report data to this game -- a second,
        # independent public-tickets-vs-money source alongside Action
        # Network, fed into the exact same _ml_public/_ml_sharp etc lists
        # below so it flows through the existing consensus verdict rather
        # than creating a separate, redundant display.
        _wgt_game = None
        try:
            _wgt_combined = load_from_gist("evbets_combined", None) or {}
            _wgt_data = (_wgt_combined.get("wiseguyteam") or {}).get(_gsport.upper(), {})
            for _wg in _wgt_data.get("games", []):
                _wg_home, _wg_away = _wg.get("home_team", ""), _wg.get("away_team", "")
                if _wg_home and _wg_away and _home_nm and _away_nm and (
                    _wg_home.lower() in _home_nm.lower() or _home_nm.lower() in _wg_home.lower()
                ) and (
                    _wg_away.lower() in _away_nm.lower() or _away_nm.lower() in _wg_away.lower()
                ):
                    _wgt_game = _wg
                    break
        except Exception:
            _wgt_game = None

        # Sleeper live score + confirmed starting lineup -- MLB only,
        # BallDontLie live scores -- replaces Sleeper's role here with
        # broader, officially-documented coverage (MLB/NFL/WNBA confirmed
        # real access; NHL returns a genuine 401 despite showing FREE on
        # the account dashboard, not yet resolved). Confirmed via real
        # official docs that lineups specifically need a paid tier, so
        # this shows live score only, not lineups (unlike the old Sleeper
        # slot, which claimed "confirmed lineup" it usually couldn't back
        # up with real data anyway).
        _bdl_game = None
        if _gsport.upper() in ("MLB", "NFL", "WNBA"):
            try:
                _bdl_data = load_from_gist(f"bdl_scores_{_gsport.upper()}", None) or {}
                for _bdl_g in _bdl_data.get("games", []):
                    _bdl_home_nm = _bdl_g.get("home_team_name", "")
                    _bdl_away_nm = _bdl_g.get("away_team_name", "")
                    if _bdl_home_nm and _bdl_away_nm and _home_nm and _away_nm and (
                        _bdl_home_nm.lower() in _home_nm.lower() or _home_nm.lower() in _bdl_home_nm.lower()
                    ) and (
                        _bdl_away_nm.lower() in _away_nm.lower() or _away_nm.lower() in _bdl_away_nm.lower()
                    ):
                        _bdl_game = _bdl_g
                        break
            except Exception:
                _bdl_game = None

        # OddsShark/Covers totals consensus -- genuinely new data (the
        # existing Covers integration only covers sides/ML, not totals/O-U).
        # Deliberately NOT wired into the sides/ML consensus lists below,
        # since that data is the exact same real Covers number the
        # existing Covers integration already provides -- adding it there
        # too would double-count one real consensus figure as if two
        # independent sources agreed on it.
        _osk_game = None
        try:
            _osk_combined = load_from_gist("oddsshark_consensus_combined", {}) or {}
            _osk_data = _osk_combined.get(_gsport.upper(), {})
            for _osk_g in _osk_data.get("games", []):
                _osk_home, _osk_away = _osk_g.get("home_team", ""), _osk_g.get("away_team", "")
                if _osk_home and _osk_away and _home_nm and _away_nm and (
                    _osk_home.lower() in _home_nm.lower() or _home_nm.lower() in _osk_home.lower()
                ) and (
                    _osk_away.lower() in _away_nm.lower() or _away_nm.lower() in _osk_away.lower()
                ):
                    _osk_game = _osk_g
                    break
        except Exception:
            _osk_game = None

        # AreYouWatchingThis multi-book moneyline feed -- real per-book
        # prices (DraftKings/FanDuel/MGM/Kalshi/Novig/Polymarket/etc, not
        # just consensus %), was captured but never shown anywhere. Finds
        # the best real moneyline price across all listed books for each
        # side of this specific game.
        _ayw_best = None
        try:
            _ayw_data = load_from_gist(f"areyouwatchingthis_{_gsport.upper()}", None) or {}
            for _ayw_g in _ayw_data.get("games", []):
                _ayw_t1 = f"{_ayw_g.get('team1_city','')} {_ayw_g.get('team1_name','')}".strip()
                _ayw_t2 = f"{_ayw_g.get('team2_city','')} {_ayw_g.get('team2_name','')}".strip()
                if _ayw_t1 and _ayw_t2 and _home_nm and _away_nm and (
                    (_ayw_t1.lower() in _home_nm.lower() or _home_nm.lower() in _ayw_t1.lower() or
                     _ayw_g.get("team1_initials","").lower() == _home_nm.lower()[:3]) or
                    (_ayw_t2.lower() in _home_nm.lower() or _home_nm.lower() in _ayw_t2.lower() or
                     _ayw_g.get("team2_initials","").lower() == _home_nm.lower()[:3])
                ):
                    _ayw_providers = [p for p in _ayw_g.get("providers", []) if p.get("provider") != "CONSENSUS"]
                    if _ayw_providers:
                        _best_1 = max(_ayw_providers, key=lambda p: p.get("moneyline_1_american", -9999) or -9999)
                        _best_2 = max(_ayw_providers, key=lambda p: p.get("moneyline_2_american", -9999) or -9999)
                        _ayw_best = {
                            "team1_book": _best_1.get("provider"), "team1_price": _best_1.get("moneyline_1_american"),
                            "team2_book": _best_2.get("provider"), "team2_price": _best_2.get("moneyline_2_american"),
                            "n_books": len(_ayw_providers),
                        }
                    break
        except Exception:
            _ayw_best = None
        if _ayw_best and _ayw_best.get("team1_price") is not None and _ayw_best.get("team2_price") is not None:
            try:
                st.caption(f"💰 Best ML price across {_ayw_best['n_books']} books: "
                           f"{int(_ayw_best['team2_price']):+d} ({_ayw_best['team2_book'].replace('_',' ').title()}) / "
                           f"{int(_ayw_best['team1_price']):+d} ({_ayw_best['team1_book'].replace('_',' ').title()})")
            except (TypeError, ValueError):
                pass

        # Smarkets real betting-exchange prices -- a real, independent
        # money-backed probability (like Kalshi/Polymarket, which already
        # show elsewhere in this section), not a bookmaker's posted line.
        # MLB only, matching current real coverage. event_name is a single
        # "Team A at Team B" string here rather than separate away/home
        # fields, so matched differently than the other sources above.
        _smk_game = None
        if _gsport.upper() == "MLB":
            try:
                _smk_data = load_from_gist("smarkets_game_lines_MLB", None) or {}
                for _smk_g in _smk_data.get("games", []):
                    _smk_evt = _smk_g.get("event_name", "")
                    if _smk_evt and _home_nm and _away_nm and (
                        _home_nm.split()[-1].lower() in _smk_evt.lower() and
                        _away_nm.split()[-1].lower() in _smk_evt.lower()
                    ):
                        _smk_game = _smk_g
                        break
            except Exception:
                _smk_game = None
        if _smk_game:
            _smk_ml_market = next((m for m in _smk_game.get("markets", []) if m.get("market_type") == "WINNER_2_WAY"), None)
            if _smk_ml_market:
                _smk_vol = _smk_ml_market.get("volume_pence")
                st.markdown('<div style="font-size:12px;color:#6a8aab;margin-top:6px;">🔄 Smarkets exchange</div>', unsafe_allow_html=True)
                for _c in _smk_ml_market.get("contracts", []):
                    try:
                        _smk_back = float(_c.get("best_back_price") or 0)
                        _smk_lay = float(_c.get("best_lay_price") or 0)
                    except (TypeError, ValueError):
                        continue
                    if not (_smk_back or _smk_lay):
                        continue
                    _smk_back_pct = max(0.0, min(100.0, _smk_back * 100))
                    _smk_lay_pct = max(0.0, min(100.0, _smk_lay * 100))
                    st.markdown(
                        f'<div style="margin-bottom:6px;">'
                        f'<div style="display:flex;justify-content:space-between;font-size:12px;color:#c9bce8;">'
                        f'<span>{_c.get("name","")}</span>'
                        f'<span>Back {_smk_back*100:.0f}¢ / Lay {_smk_lay*100:.0f}¢</span>'
                        f'</div>'
                        f'<div style="position:relative;height:8px;border-radius:4px;background:#1a2a3a;overflow:hidden;">'
                        f'<div style="position:absolute;left:0;width:{_smk_back_pct}%;height:100%;background:#22c55e88;"></div>'
                        f'<div style="position:absolute;right:0;width:{100-_smk_lay_pct}%;height:100%;background:#e0404088;"></div>'
                        f'</div></div>',
                        unsafe_allow_html=True
                    )
                if _smk_vol:
                    try:
                        st.caption(f"Volume £{float(_smk_vol)/100:,.0f}")
                    except (TypeError, ValueError):
                        pass

        # Novig real exchange prices via The Odds API (novig_odds_refresh.py)
        # -- same category as the Smarkets block above (real money-backed
        # exchange, not a bookmaker's posted line), all sports rather than
        # MLB-only. Captured but never shown anywhere until now.
        _nvg_game = None
        try:
            _nvg_data = load_from_gist("novig_odds", None) or {}
            for _nvg_g in _nvg_data.get("events", []):
                _nvg_home, _nvg_away = _nvg_g.get("home_team", ""), _nvg_g.get("away_team", "")
                if _nvg_home and _nvg_away and _home_nm and _away_nm and (
                    _nvg_home.lower() in _home_nm.lower() or _home_nm.lower() in _nvg_home.lower()
                ) and (
                    _nvg_away.lower() in _away_nm.lower() or _away_nm.lower() in _nvg_away.lower()
                ):
                    _nvg_game = _nvg_g
                    break
        except Exception:
            _nvg_game = None
        if _nvg_game:
            _nvg_h2h = (_nvg_game.get("novig_markets") or {}).get("h2h", [])
            if _nvg_h2h:
                _nvg_parts = []
                for _o in _nvg_h2h:
                    if _o.get("price") is not None:
                        try:
                            _nvg_parts.append(f"{_o.get('name','')} {int(_o['price']):+d}")
                        except (TypeError, ValueError):
                            pass
                if _nvg_parts:
                    st.caption(f"🔄 Novig exchange: {' vs '.join(_nvg_parts)}")

        # SportsInsights public betting % (bets on spread/total/ML per side)
        # -- real fresh data, was being scraped every cycle but silently
        # discarded due to a key mismatch (fetch function expected "data",
        # real payload uses "games"). Fixed same session this was found.
        try:
            _si_games = st.session_state.get("sportsinsights_games", [])
            _si_game = next((g for g in _si_games if _home_nm and _away_nm and (
                str(g.get("home_team","")).lower() in _home_nm.lower() or _home_nm.lower() in str(g.get("home_team","")).lower()
            ) and (
                str(g.get("away_team","")).lower() in _away_nm.lower() or _away_nm.lower() in str(g.get("away_team","")).lower()
            )), None)
        except Exception:
            _si_game = None
        if _si_game:
            _si_parts = []
            for label, key in (("Spread", "home_pct_spread"), ("Total", "home_pct_ou"), ("ML", "home_pct_ml")):
                v = _si_game.get(key)
                if v is not None:
                    _si_parts.append(f"{label} {v}% home")
            if _si_parts:
                st.caption(f"👥 Public bets (SportsInsights): {' · '.join(_si_parts)} ({_si_game.get('total_bets','?'):,} bets)" if isinstance(_si_game.get("total_bets"), (int, float)) else f"👥 Public bets (SportsInsights): {' · '.join(_si_parts)}")

        # VSIN handle%/bets% splits -- real money vs ticket-count split
        # per side (spread/total/ML), the actual tickets-vs-money signal
        # this project didn't have a working source for until now.
        try:
            _vsin_games = st.session_state.get("vsin_splits_games", [])
            _vsin_game = next((g for g in _vsin_games if _home_nm and _away_nm and (
                str(g.get("home_team","")).lower() in _home_nm.lower() or _home_nm.lower() in str(g.get("home_team","")).lower()
            ) and (
                str(g.get("road_team","")).lower() in _away_nm.lower() or _away_nm.lower() in str(g.get("road_team","")).lower()
            )), None)
        except Exception:
            _vsin_game = None
        if _vsin_game:
            _vs_parts = []
            for label, key in (("Spread", "spread"), ("Total", "total"), ("ML", "moneyline")):
                block = _vsin_game.get(key, {})
                home_side = block.get("home") or block.get("over")
                if home_side:
                    _vs_parts.append(f"{label}: {home_side.get('handle_pct','?')}% handle / {home_side.get('bets_pct','?')}% bets (home)")
            if _vs_parts:
                st.caption(f"💰 VSIN handle vs bets: {' · '.join(_vs_parts)}")

        # Closing line (once the game has actually started/closed) --
        # real consumer for fetch_all_closing_lines, which had a real
        # producer (store_closing_lines) but zero display anywhere.
        try:
            _cl_all = fetch_all_closing_lines() or {}
            _cl_today = date.today().strftime("%Y-%m-%d")
            _cl_entry = None
            for _cl_v in _cl_all.values():
                if _cl_v.get("date") != _cl_today:
                    continue
                _cl_m = str(_cl_v.get("matchup", ""))
                if _home_nm and _away_nm and (
                    _home_nm.lower() in _cl_m.lower() or _cl_m.lower() in _home_nm.lower()
                ) and (
                    _away_nm.lower() in _cl_m.lower() or _cl_m.lower() in _away_nm.lower()
                ):
                    _cl_entry = _cl_v
                    break
        except Exception:
            _cl_entry = None
        if _cl_entry:
            _cl_parts = []
            if _cl_entry.get("close_spread") not in (None, "N/A"):
                _cl_parts.append(f"Spread {_cl_entry['close_spread']}")
            if _cl_entry.get("close_total") not in (None, "N/A"):
                _cl_parts.append(f"Total {_cl_entry['close_total']}")
            if _cl_entry.get("close_home_ml") not in (None, "N/A"):
                _cl_parts.append(f"ML {_cl_entry['close_home_ml']}")
            if _cl_parts:
                st.caption(f"🔒 Closing line ({_cl_entry.get('stored_at','')}): {' · '.join(_cl_parts)}")

        # MLB probable pitchers -- team-keyed, includes Savant FIP/xFIP/
        # xwOBA/K%/BB% enrichment already built in. Confirmed unused
        # anywhere in the codebase before this.
        if _gsport == "MLB":
            try:
                _mlb_pitchers = st.session_state.get("mlb_probable_pitchers", {})
                _mp_home = next((v for k, v in _mlb_pitchers.items() if _home_nm and (k.lower() in _home_nm.lower() or _home_nm.lower() in k.lower())), None)
                _mp_away = next((v for k, v in _mlb_pitchers.items() if _away_nm and (k.lower() in _away_nm.lower() or _away_nm.lower() in k.lower())), None)
            except Exception:
                _mp_home = _mp_away = None
            _mp_parts = []
            for _mp in (_mp_away, _mp_home):
                if _mp and _mp.get("pitcher"):
                    _mp_fip = _mp.get("fip_live")
                    _mp_parts.append(f"{_mp['pitcher']}" + (f" (FIP {_mp_fip})" if _mp_fip is not None else ""))
            if _mp_parts:
                st.caption(f"⚾ Probable pitchers: {' vs '.join(_mp_parts)}")

        # Bobby's Bets live scoreboard + weather/park factor -- MLB only,
        # matching this source's real coverage.
        if _gsport == "MLB":
            try:
                _bb_games = st.session_state.get("bobbys_bets_scoreboard", [])
                _bb_game = next((g for g in _bb_games if _home_nm and _away_nm and (
                    str(g.get("home", {}).get("team", "")).lower() in _home_nm.lower() or
                    _home_nm.lower() in str(g.get("home", {}).get("team", "")).lower()
                ) and (
                    str(g.get("away", {}).get("team", "")).lower() in _away_nm.lower() or
                    _away_nm.lower() in str(g.get("away", {}).get("team", "")).lower()
                )), None)
            except Exception:
                _bb_game = None
            if _bb_game and _bb_game.get("status") not in ("Scheduled", None):
                _bb_away_s = _bb_game.get("away", {})
                _bb_home_s = _bb_game.get("home", {})
                st.caption(f"📊 Live (Bobby's Bets): {_bb_away_s.get('abbreviation','?')} {_bb_away_s.get('score','?')} — "
                           f"{_bb_home_s.get('abbreviation','?')} {_bb_home_s.get('score','?')} ({_bb_game.get('status','')})")
            try:
                _bb_home_abbr = _bb_game.get("home", {}).get("abbreviation") if _bb_game else None
                if _bb_home_abbr:
                    _bb_weather = fetch_bobbys_bets_weather(_bb_home_abbr, "mlb")
                    _bb_impact = _bb_weather.get("impact", {})
                    if _bb_impact.get("summary"):
                        st.caption(f"🌤️ {_bb_impact['summary']}")
            except Exception:
                pass

        if _bdl_game:
            _bdl_home_data = _bdl_game.get("home_team_data") or {}
            _bdl_away_data = _bdl_game.get("away_team_data") or {}
            _bdl_status = _bdl_game.get("status", "")
            _bdl_score_txt = None
            if _bdl_away_data.get("runs") is not None and _bdl_home_data.get("runs") is not None:
                _bdl_score_txt = f"{_bdl_away_data.get('runs')}-{_bdl_home_data.get('runs')} ({_bdl_status})"
            elif _bdl_status:
                _bdl_score_txt = _bdl_status
            with st.expander("📊 BallDontLie: live score" + (f" — {_bdl_score_txt}" if _bdl_score_txt else ""), expanded=False):
                _bdl_c1, _bdl_c2 = st.columns(2)
                with _bdl_c1:
                    st.markdown(f"**{_away_nm}**")
                    if _bdl_away_data:
                        st.caption(f"R: {_bdl_away_data.get('runs','?')}  H: {_bdl_away_data.get('hits','?')}  E: {_bdl_away_data.get('errors','?')}")
                with _bdl_c2:
                    st.markdown(f"**{_home_nm}**")
                    if _bdl_home_data:
                        st.caption(f"R: {_bdl_home_data.get('runs','?')}  H: {_bdl_home_data.get('hits','?')}  E: {_bdl_home_data.get('errors','?')}")
                if _bdl_game.get("venue"):
                    st.caption(f"📍 {_bdl_game['venue']}")

        # Match Covers data to this game
        _cov_game = None
        if isinstance(_cov_data, dict):
            for _cd_matchup, _cd_val in _cov_data.items():
                _cd_matchup_l = _cd_matchup.lower()
                if any(t.lower() in _cd_matchup_l for t in [_home_nm, _away_nm] if t):
                    _cd_away, _, _cd_home = _cd_matchup.partition(" @ ")
                    _cd_away_pct = _cd_val.get("away_pct", 50)
                    _cd_home_pct = _cd_val.get("home_pct", 50)
                    if _cd_home_pct >= _cd_away_pct:
                        _cov_game = {"matchup": _cd_matchup, "public_pct": _cd_home_pct, "side": _cd_home, **_cd_val}
                    else:
                        _cov_game = {"matchup": _cd_matchup, "public_pct": _cd_away_pct, "side": _cd_away, **_cd_val}
                    break

        # Match BettingPros expert/public consensus to this game. BettingPros
        # is fetched every board load (bettingpros_data) and its parsing
        # logic already existed inside compute_public_fade_signal — but that
        # function was never called from anywhere, so this data has been
        # sitting fetched-and-parsed-but-unused. Wiring it in here the same
        # way Covers is wired in above.
        _bp_data = st.session_state.get("bettingpros_data", {})
        _bp_game = None
        if _bp_data:
            _bp_items = (_bp_data if isinstance(_bp_data, list)
                         else _bp_data.get("items", _bp_data.get("picks", _bp_data.get("data", []))))
            if isinstance(_bp_items, list):
                _bp_matchup_l = f"{_away_nm} {_home_nm}".lower()
                for _bi in _bp_items:
                    if not isinstance(_bi, dict):
                        continue
                    _bpick = _bi.get("pick", _bi)
                    _bslug = (_bpick.get("slug", "") or _bpick.get("matchup", "") or "").lower()
                    if not _bslug or not any(t.lower() in _bslug for t in [_home_nm, _away_nm] if t):
                        continue
                    _bp_pct  = float(_bpick.get("consensus_pct") or _bpick.get("pct") or 0)
                    _bp_side = _bpick.get("pick_type", "") or _bpick.get("side", "")
                    if _bp_pct and _bp_side:
                        _bp_game = {"public_pct": _bp_pct, "side": _bp_side}
                        break

        # Match Kalshi/Polymarket markets to this game by team-name presence
        # in the market title/event text (same matching pattern as Covers).
        def _match_prediction_market(markets, home, away):
            if not markets or not (home or away):
                return None
            for m in markets:
                text = f"{m.get('title','')} {m.get('event','')}".lower()
                if (home and home.lower() in text) or (away and away.lower() in text):
                    return m
            return None

        _kal_game  = _match_prediction_market(st.session_state.get("kalshi_markets", []), _home_nm, _away_nm)
        _poly_game = _match_prediction_market(st.session_state.get("polymarket_markets", []), _home_nm, _away_nm)

        # Pinnacle/VSIN sharp signals already computed per-game for the
        # header badges — pull the same objects in here.
        #
        # BUG FIX (2026-07): each recommendation TYPE (SPREAD/TOTAL/MONEYLINE)
        # carries its OWN distinct pinnacle_sharp/vsin_sharp value -- but this
        # used to grab just ONE via next(...) (whichever recommendation
        # happened to have a truthy value first, in SPREAD->TOTAL->MONEYLINE
        # append order) and reuse that SAME signal under every market column
        # below. In practice that meant a TOTAL signal ("Pinnacle neutral on
        # OVER: 49.1%") could show up mislabeled under Moneyline AND Spread,
        # while being silently omitted from Total (the market it actually
        # describes) since Total's own display code never checked _pin_sig
        # at all. Pulling one variable per market fixes both the mislabeling
        # and the Total omission in one change.
        def _sig_for(market_type, key):
            return next((r.get(key) for r in _g.get("recommendations", []) if r.get("type") == market_type and r.get(key)), None)
        _pin_sig_ml,  _vsin_sig_ml  = _sig_for("MONEYLINE", "pinnacle_sharp"), _sig_for("MONEYLINE", "vsin_sharp")
        _pin_sig_sp,  _vsin_sig_sp  = _sig_for("SPREAD",    "pinnacle_sharp"), _sig_for("SPREAD",    "vsin_sharp")
        _pin_sig_tot, _vsin_sig_tot = _sig_for("TOTAL",     "pinnacle_sharp"), _sig_for("TOTAL",     "vsin_sharp")
        # Kept for the top verdict summary's Moneyline section below, which
        # already existed before this fix and expects these two names.
        _pin_sig, _vsin_sig = _pin_sig_ml, _vsin_sig_ml

        _steam_sigs_check = _g.get("steam_signals", {})
        _steam_hits = {k: v for k, v in _steam_sigs_check.items() if isinstance(v, dict) and v.get("is_steam")}
        _opener_gaps = {k: v for k, v in _steam_sigs_check.items() if k.endswith("_opener_gap") and abs(v.get("gap", 0)) >= 0.5}
        _has_steam = bool(_steam_hits or _opener_gaps)

        _has_pub = bool(
            (_pub_data and any(_pub_data.get(k) for k in ["ml_pcts", "spread_pcts", "total_pcts"]))
            or _cov_game or _bp_game or _kal_game or _poly_game
            or _pin_sig_ml or _vsin_sig_ml or _pin_sig_sp or _vsin_sig_sp or _pin_sig_tot or _vsin_sig_tot
            or _has_steam
        )

        if _has_pub:
            with st.expander("📊 Public vs Money", expanded=False):
                # ── Consensus / Contradiction summary — SPLIT BY MARKET.
                # Previously this blended Moneyline sources (Action Network)
                # with Covers (also a straight-up team pick, mislabeled
                # under Total) into one combined verdict with no market
                # label — a bettor reading "public-only signal on Tb" had
                # no way to tell if that meant Moneyline, Spread, or Total.
                # Each market now gets its own explicit, labeled verdict.
                def _consensus_verdict(market_label, public_votes, sharp_votes):
                    if not public_votes and not sharp_votes:
                        return
                    pub_sides = {v[1] for v in public_votes}
                    sharp_sides = {v[1] for v in sharp_votes}
                    st.markdown(f"**{market_label}:**")
                    if public_votes and sharp_votes and pub_sides and sharp_sides and not (pub_sides & sharp_sides):
                        st.markdown(f"🔥 Contradiction — public is on **{list(pub_sides)[0]}**, sharp signals point to **{list(sharp_sides)[0]}**.")
                        st.caption(
                            f"Public ({', '.join(v[0] for v in public_votes)}) vs sharp ({', '.join(v[0] for v in sharp_votes)}). "
                            f"Fading the heavy public side has historically been the higher-EV lean here, but check split size first."
                        )
                    elif sharp_votes and len(sharp_sides) > 1:
                        st.markdown(f"⚠️ Sharp sources disagree with each other on {market_label}.")
                        st.caption("; ".join(f"{v[0]} → {v[1]}" for v in sharp_votes) + " — treat as noisy, not sharp-confirmed.")
                    elif public_votes and sharp_votes:
                        st.markdown(f"✅ Public and sharp agree on **{list(pub_sides)[0]}**.")
                        st.caption(f"{', '.join(v[0] for v in public_votes + sharp_votes)} all point the same direction — stronger than either alone.")
                    elif sharp_votes:
                        st.markdown(f"📌 Sharp-only signal on **{list(sharp_sides)[0]}** — no public data to compare yet.")
                        st.caption(f"Source: {', '.join(v[0] for v in sharp_votes)}")
                    elif public_votes:
                        st.markdown(f"👥 Public-only signal on **{list(pub_sides)[0]}** — no sharp confirmation yet, treat with caution.")
                        st.caption(f"Source: {', '.join(v[0] for v in public_votes)}")

                st.markdown("**🔎 What this means for a bettor, by market:**")

                # -- Moneyline: Action Network tickets/money + Covers (Covers
                # is a straight-up team pick, i.e. a Moneyline signal, not a
                # Total signal — was previously shown under "Total/Covers").
                _ml_pcts_top = _pub_data.get("ml_pcts", {}) if _pub_data else {}
                _home_ml_top = _ml_pcts_top.get("home", {})
                _away_ml_top = _ml_pcts_top.get("away", {})
                _ml_public, _ml_sharp = [], []
                if _home_ml_top or _away_ml_top:
                    _ht, _hm = _home_ml_top.get("tickets", 0), _home_ml_top.get("money", 0)
                    _at, _am = _away_ml_top.get("tickets", 0), _away_ml_top.get("money", 0)
                    _an_pub_side = _home_nm if _ht > _at else _away_nm
                    _an_sharp_side = _home_nm if _hm > _am else _away_nm
                    _ml_public.append(("Action Network tickets", _an_pub_side, f"{max(_ht,_at)}% of bets"))
                    if abs(_hm - _ht) >= 10 or abs(_am - _at) >= 10:
                        _ml_sharp.append(("Action Network money", _an_sharp_side, f"{max(_hm,_am)}% of $ vs {max(_ht,_at)}% of bets"))
                if _cov_game:
                    _ml_public.append(("Covers straight-up picks", _cov_game.get("side", ""), f"{_cov_game.get('public_pct',50)}% of contest players picked them to win"))
                if _bp_game:
                    _ml_public.append(("BettingPros consensus", _bp_game.get("side", ""), f"{_bp_game.get('public_pct',0):.0f}% consensus"))
                if _pin_sig and _pin_sig.get("note"):
                    (_ml_sharp if _pin_sig.get("confirms") else _ml_public).append(
                        ("Pinnacle (sharp book)", "model's pick" if _pin_sig.get("confirms") else "opposite of model", _pin_sig["note"])
                    )
                if _vsin_sig and _vsin_sig.get("note"):
                    (_ml_sharp if _vsin_sig.get("confirms") else _ml_public).append(
                        ("VSIN Nevada", "model's pick" if _vsin_sig.get("confirms") else "opposite of model", _vsin_sig["note"])
                    )
                if _wgt_game and _wgt_game.get("ml"):
                    _wgt_ml = _wgt_game["ml"]
                    _wgt_s1, _wgt_s2 = _wgt_ml.get("side1", {}), _wgt_ml.get("side2", {})
                    if _wgt_s1.get("bet_pct") is not None:
                        _wgt_pub_side = _away_nm if _wgt_s1.get("bet_pct", 0) > _wgt_s2.get("bet_pct", 0) else _home_nm
                        _wgt_pub_pct = max(_wgt_s1.get("bet_pct", 0), _wgt_s2.get("bet_pct", 0))
                        _ml_public.append(("WiseGuyTeam tickets", _wgt_pub_side, f"{_wgt_pub_pct}% of bets"))
                    if _wgt_ml.get("sharp_side"):
                        _wgt_sharp_side = _away_nm if _wgt_ml["sharp_side"] == "side1" else _home_nm
                        _wgt_sharp_d = _wgt_s1 if _wgt_ml["sharp_side"] == "side1" else _wgt_s2
                        _ml_sharp.append(("WiseGuyTeam money", _wgt_sharp_side,
                                          f"{_wgt_sharp_d.get('handle_pct','?')}% of $ vs {_wgt_sharp_d.get('bet_pct','?')}% of bets"))
                _consensus_verdict("Moneyline", _ml_public, _ml_sharp)

                # -- Spread: Action Network spread tickets/money + steam on spread
                _sp_pcts_top = _pub_data.get("spread_pcts", {}) if _pub_data else {}
                _sp_public, _sp_sharp = [], []
                for _side, _sd in _sp_pcts_top.items():
                    _t, _m = _sd.get("tickets", 0), _sd.get("money", 0)
                    if _t: _sp_public.append(("Action Network tickets", _side, f"{_t}% of bets"))
                    if abs(_m - _t) >= 10: _sp_sharp.append(("Action Network money", _side, f"{_m}% of $ vs {_t}% of bets"))
                for _sk, _sv in _steam_hits.items():
                    if "spread" in _sk:
                        _sp_sharp.append(("Steam move", f"{_sv.get('direction','')}", f"{_sv.get('magnitude',0)} pt move in {_sv.get('elapsed_seconds',0)}s"))
                if _pin_sig_sp and _pin_sig_sp.get("note"):
                    (_sp_sharp if _pin_sig_sp.get("confirms") else _sp_public).append(
                        ("Pinnacle (sharp book)", "model's pick" if _pin_sig_sp.get("confirms") else "opposite of model", _pin_sig_sp["note"])
                    )
                if _vsin_sig_sp and _vsin_sig_sp.get("note"):
                    (_sp_sharp if _vsin_sig_sp.get("confirms") else _sp_public).append(
                        ("VSIN Nevada", "model's pick" if _vsin_sig_sp.get("confirms") else "opposite of model", _vsin_sig_sp["note"])
                    )
                if _wgt_game and _wgt_game.get("spread"):
                    _wgt_sp = _wgt_game["spread"]
                    _wgt_sp1, _wgt_sp2 = _wgt_sp.get("side1", {}), _wgt_sp.get("side2", {})
                    if _wgt_sp1.get("bet_pct") is not None:
                        _wgt_sp_pub_side = _away_nm if _wgt_sp1.get("bet_pct", 0) > _wgt_sp2.get("bet_pct", 0) else _home_nm
                        _sp_public.append(("WiseGuyTeam tickets", _wgt_sp_pub_side, f"{max(_wgt_sp1.get('bet_pct',0), _wgt_sp2.get('bet_pct',0))}% of bets"))
                    if _wgt_sp.get("sharp_side"):
                        _wgt_sp_sharp_side = _away_nm if _wgt_sp["sharp_side"] == "side1" else _home_nm
                        _wgt_sp_sharp_d = _wgt_sp1 if _wgt_sp["sharp_side"] == "side1" else _wgt_sp2
                        _sp_sharp.append(("WiseGuyTeam money", _wgt_sp_sharp_side,
                                          f"{_wgt_sp_sharp_d.get('handle_pct','?')}% of $ vs {_wgt_sp_sharp_d.get('bet_pct','?')}% of bets"))
                _consensus_verdict("Spread", _sp_public, _sp_sharp)

                # -- Total: Action Network total tickets/money + steam on total
                # (Kalshi/Polymarket totals excluded from this verdict — too
                # thin-volume to treat as a real sharp/public signal, shown
                # as raw data below instead.)
                _tot_pcts_top = _pub_data.get("total_pcts", {}) if _pub_data else {}
                _tot_public, _tot_sharp = [], []
                for _side, _td in _tot_pcts_top.items():
                    _t, _m = _td.get("tickets", 0), _td.get("money", 0)
                    if _t: _tot_public.append(("Action Network tickets", _side, f"{_t}% of bets"))
                    if abs(_m - _t) >= 10: _tot_sharp.append(("Action Network money", _side, f"{_m}% of $ vs {_t}% of bets"))
                for _sk, _sv in _steam_hits.items():
                    if "total" in _sk:
                        _tot_sharp.append(("Steam move", f"{_sv.get('direction','')}", f"{_sv.get('magnitude',0)} pt move in {_sv.get('elapsed_seconds',0)}s"))
                if _pin_sig_tot and _pin_sig_tot.get("note"):
                    (_tot_sharp if _pin_sig_tot.get("confirms") else _tot_public).append(
                        ("Pinnacle (sharp book)", "model's pick" if _pin_sig_tot.get("confirms") else "opposite of model", _pin_sig_tot["note"])
                    )
                if _vsin_sig_tot and _vsin_sig_tot.get("note"):
                    (_tot_sharp if _vsin_sig_tot.get("confirms") else _tot_public).append(
                        ("VSIN Nevada", "model's pick" if _vsin_sig_tot.get("confirms") else "opposite of model", _vsin_sig_tot["note"])
                    )
                if _wgt_game and _wgt_game.get("total"):
                    _wgt_tot = _wgt_game["total"]
                    _wgt_t1, _wgt_t2 = _wgt_tot.get("side1", {}), _wgt_tot.get("side2", {})
                    if _wgt_t1.get("bet_pct") is not None:
                        _wgt_tot_pub_side = "Over" if _wgt_t1.get("bet_pct", 0) > _wgt_t2.get("bet_pct", 0) else "Under"
                        _tot_public.append(("WiseGuyTeam tickets", _wgt_tot_pub_side, f"{max(_wgt_t1.get('bet_pct',0), _wgt_t2.get('bet_pct',0))}% of bets"))
                    if _wgt_tot.get("sharp_side"):
                        _wgt_tot_sharp_side = "Over" if _wgt_tot["sharp_side"] == "side1" else "Under"
                        _wgt_tot_sharp_d = _wgt_t1 if _wgt_tot["sharp_side"] == "side1" else _wgt_t2
                        _tot_sharp.append(("WiseGuyTeam money", _wgt_tot_sharp_side,
                                          f"{_wgt_tot_sharp_d.get('handle_pct','?')}% of $ vs {_wgt_tot_sharp_d.get('bet_pct','?')}% of bets"))
                if _osk_game and _osk_game.get("consensus_ou_side"):
                    _osk_side = _osk_game["consensus_ou_side"].capitalize()
                    _osk_pct = max(_osk_game.get("over_pct", 0) or 0, _osk_game.get("under_pct", 0) or 0)
                    _tot_public.append(("OddsShark/Covers", _osk_side, f"{_osk_pct}% of public picks"))
                _consensus_verdict("Total", _tot_public, _tot_sharp)

                st.markdown("---")

                _pcol1, _pcol2, _pcol3 = st.columns(3)

                # ML public vs money
                _ml_pcts = _pub_data.get("ml_pcts", {}) if _pub_data else {}
                _home_ml_pub = _ml_pcts.get("home", {})
                _away_ml_pub = _ml_pcts.get("away", {})
                with _pcol1:
                    st.markdown("**Moneyline**")
                    if _home_ml_pub or _away_ml_pub:
                        _home_t = _home_ml_pub.get("tickets",0)
                        _home_m = _home_ml_pub.get("money",0)
                        _away_t = _away_ml_pub.get("tickets",0)
                        _away_m = _away_ml_pub.get("money",0)
                        st.caption(f"{_g.get('home','Home')}: 🎟️ {_home_t}% | 💰 {_home_m}%")
                        st.caption(f"{_g.get('away','Away')}: 🎟️ {_away_t}% | 💰 {_away_m}%")
                        # Sharp signal: money > tickets = sharp money
                        if abs(_home_m - _home_t) >= 15:
                            _sharp_side = _g.get("home","Home") if _home_m > _home_t else _g.get("away","Away")
                            _pub_side   = _g.get("home","Home") if _home_t > _away_t else _g.get("away","Away")
                            if _sharp_side != _pub_side:
                                st.markdown(f"⚡ **Sharp money on {_sharp_side}**")
                                st.caption(
                                    f"Why: Public ({_home_t if _sharp_side==_g.get('home') else _away_t}% tickets) "
                                    f"vs Sharp ({_home_m if _sharp_side==_g.get('home') else _away_m}% money). "
                                    f"When money % >> tickets %, institutional/sharp bettors are fading the public."
                                )
                            else:
                                st.markdown(f"✅ **Public + Sharp agree on {_sharp_side}**")
                                st.caption("Both public tickets and money % point same direction — stronger signal.")
                    elif not (_pin_sig or _vsin_sig or _cov_game or _bp_game):
                        st.caption("No data")

                    if _cov_game:
                        _fav  = _cov_game.get("side","")
                        _pct  = _cov_game.get("public_pct",50)
                        _raw  = _cov_game.get("raw_pcts",{})
                        st.caption(f"**Covers Public (straight-up):**")
                        if not isinstance(_raw, dict):
                            _raw = {}
                        for _team, _tpct in _raw.items():
                            st.caption(f"  {_team}: {_tpct}")
                        if _pct >= 75:
                            st.markdown(f"🎯 **Fade candidate:** {_pct}% picked {_fav} to win")
                            st.caption(
                                f"Why: {_pct}% of contest players picked {_fav} to win. "
                                f"Heavy public sides (75%+) often lose because sharp bettors "
                                f"take the other side, moving the line against the crowd."
                            )
                        elif _pct >= 60:
                            st.caption(f"📊 Mild public lean ({_pct}% picked {_fav} to win) — not extreme enough to fade.")

                    if _bp_game:
                        st.caption(f"🧮 BettingPros: {_bp_game.get('public_pct',0):.0f}% consensus on {_bp_game.get('side','')}")

                    # Additional sources beyond Action Network — shown
                    # whenever present, not just as a fallback for "No data".
                    if _kal_game:
                        st.caption(f"🔷 Kalshi: {_kal_game.get('implied_prob',0.5):.0%} implied ({_kal_game.get('title','')[:40]})")
                    if _poly_game:
                        st.caption(f"🟣 Polymarket: {_poly_game.get('implied_prob',0.5):.0%} implied ({_poly_game.get('title','')[:40]})")
                    if _pin_sig and _pin_sig.get("note"):
                        st.caption(_pin_sig["note"])
                    if _vsin_sig and _vsin_sig.get("note"):
                        st.caption(_vsin_sig["note"])
                _sp_pcts = _pub_data.get("spread_pcts", {}) if _pub_data else {}
                with _pcol2:
                    st.markdown("**Spread**")
                    if _sp_pcts:
                        for _side, _sd in _sp_pcts.items():
                            st.caption(f"{_side}: 🎟️ {_sd.get('tickets',0)}% | 💰 {_sd.get('money',0)}%")
                    if _pin_sig_sp and _pin_sig_sp.get("note"):
                        st.caption(_pin_sig_sp["note"])
                    if _vsin_sig_sp and _vsin_sig_sp.get("note"):
                        st.caption(_vsin_sig_sp["note"])
                    if not _sp_pcts and not _pin_sig_sp and not _vsin_sig_sp:
                        st.caption("No data")

                # Total public vs money
                _tot_pcts = _pub_data.get("total_pcts", {}) if _pub_data else {}
                with _pcol3:
                    st.markdown("**Total**")
                    if _tot_pcts:
                        for _side, _td in _tot_pcts.items():
                            st.caption(f"{_side}: 🎟️ {_td.get('tickets',0)}% | 💰 {_td.get('money',0)}%")
                    if _pin_sig_tot and _pin_sig_tot.get("note"):
                        st.caption(_pin_sig_tot["note"])
                    if _vsin_sig_tot and _vsin_sig_tot.get("note"):
                        st.caption(_vsin_sig_tot["note"])
                    if _kal_game and "total" in (_kal_game.get("title","") + _kal_game.get("event","")).lower():
                        st.caption(f"🔷 Kalshi total: {_kal_game.get('implied_prob',0.5):.0%} implied")
                    if _poly_game and "total" in (_poly_game.get("title","") + _poly_game.get("event","")).lower():
                        st.caption(f"🟣 Polymarket total: {_poly_game.get('implied_prob',0.5):.0%} implied")
                    if not _tot_pcts and not _pin_sig_tot and not _vsin_sig_tot and not _kal_game and not _poly_game:
                        st.caption("No data")

                # ── Steam moves & RLM — this is the actual industry-standard
                # "where's the money" signal: rapid line movement tracked
                # directly at Pinnacle/BetOnline, not a tickets/money survey.
                # A steam move means real sharp money forced the number to
                # move, which is a stronger signal than any public-percent
                # source above. Data already computed per-game earlier in
                # this function (detect_steam_move via bc_utils) — just
                # wasn't surfaced in this expander before. (_steam_hits /
                # _opener_gaps computed earlier, reused here and in the
                # consensus summary above.)
                if _steam_hits or _opener_gaps:
                    st.markdown("**⚡ Steam Moves (Pinnacle/BetOnline line tracking)**")
                    for _sk, _sv in _steam_hits.items():
                        _book_mkt = _sk.replace("_", " ").title()
                        st.caption(
                            f"🔥 {_book_mkt}: moved {_sv.get('magnitude',0)} pts {_sv.get('direction','')} "
                            f"in {_sv.get('elapsed_seconds',0)}s (confidence {_sv.get('confidence',0):.0%})"
                        )
                    for _gk, _gv in _opener_gaps.items():
                        _mkt_name = _gk.replace("_opener_gap", "").title()
                        st.caption(f"📈 {_mkt_name} moved {_gv.get('gap',0):+.1f} pts from open — real sharp-driven movement, not a survey.")
    else:
        st.markdown(empty_state_html("🏟️", "No games loaded yet",
                                      "Pick a sport and load the board to see game lines."),
                    unsafe_allow_html=True)

# ----- TAB 3: LOCKS & LEDGER -----
with tabs[10]:
    st.markdown('<div class="bc-section-header">🔒 Active Locks</div>', unsafe_allow_html=True)

    # Streak indicator: real consecutive win/loss count from the most
    # recent resolved bets, walked backward chronologically. Not shown at
    # all if there's no resolved history yet -- no fabricated "0-streak".
    _streak_hist = sorted(
        [h for h in st.session_state.get("history", []) if h.get("outcome") in ("WIN", "LOSS")],
        key=lambda h: h.get("timestamp", ""),
    )
    if _streak_hist:
        _streak_count = 0
        _streak_type = _streak_hist[-1]["outcome"]
        for h in reversed(_streak_hist):
            if h["outcome"] == _streak_type:
                _streak_count += 1
            else:
                break
        if _streak_count >= 2:
            if _streak_type == "WIN":
                st.markdown(
                    f'<div style="display:inline-flex;align-items:center;gap:6px;background:rgba(255,140,0,0.12);'
                    f'border:1px solid rgba(255,140,0,0.3);border-radius:8px;padding:6px 14px;margin-bottom:10px;">'
                    f'<span style="font-size:18px;">🔥</span>'
                    f'<span style="font-weight:700;color:#ff8c00;">{_streak_count}-bet win streak</span>'
                    f'</div>', unsafe_allow_html=True
                )
            else:
                st.markdown(
                    f'<div style="display:inline-flex;align-items:center;gap:6px;background:rgba(77,184,255,0.12);'
                    f'border:1px solid rgba(77,184,255,0.3);border-radius:8px;padding:6px 14px;margin-bottom:10px;">'
                    f'<span style="font-size:18px;">🥶</span>'
                    f'<span style="font-weight:700;color:#4db8ff;">{_streak_count}-bet cold streak</span>'
                    f'</div>', unsafe_allow_html=True
                )

        # 10-day rolling ROI trend -- real daily net P&L / wagered from
        # resolved history, grouped by calendar day. Only rendered when at
        # least 2 days with resolved bets exist in that window; no fake
        # flat line otherwise.
        from collections import defaultdict as _dd_roi
        from datetime import datetime as _dt_roi, timedelta as _td_roi
        _roi_cutoff = (_dt_roi.now() - _td_roi(days=10)).strftime("%Y-%m-%d")
        _roi_by_day = _dd_roi(lambda: {"wagered": 0.0, "net": 0.0})
        for h in st.session_state.get("history", []):
            _d = h.get("timestamp", "")[:10]
            if _d < _roi_cutoff or h.get("outcome") not in ("WIN", "LOSS"):
                continue
            _w = float(h.get("wager", 0) or 0)
            _roi_by_day[_d]["wagered"] += _w
            if h.get("outcome") == "WIN":
                _roi_by_day[_d]["net"] += (_w * float(h.get("payout_mult", 1.0) or 1.0) - _w) if h.get("payout_mult") else _w
            else:
                _roi_by_day[_d]["net"] -= _w
        _roi_days = sorted(_roi_by_day.keys())
        _roi_pcts = [
            (_roi_by_day[d]["net"] / _roi_by_day[d]["wagered"] * 100) if _roi_by_day[d]["wagered"] else 0
            for d in _roi_days
        ]
        if len(_roi_days) >= 2:
            _roi_min, _roi_max = min(_roi_pcts + [0]), max(_roi_pcts + [0])
            _roi_range = (_roi_max - _roi_min) or 1
            _roi_w, _roi_h = 280, 60
            _roi_pts = " ".join(
                f"{i/(len(_roi_pcts)-1)*_roi_w:.1f},{_roi_h - (v-_roi_min)/_roi_range*_roi_h:.1f}"
                for i, v in enumerate(_roi_pcts)
            )
            _roi_zero_y = _roi_h - (0 - _roi_min) / _roi_range * _roi_h
            _roi_color = "#22c55e" if _roi_pcts[-1] >= 0 else "#e04040"
            st.markdown(
                f'<div class="command-card" style="padding:14px 16px;margin-bottom:14px;max-width:340px;">'
                f'<div class="command-label" style="margin-bottom:6px;">10-Day Rolling ROI</div>'
                f'<svg width="{_roi_w}" height="{_roi_h}" style="display:block;">'
                f'<line x1="0" y1="{_roi_zero_y:.1f}" x2="{_roi_w}" y2="{_roi_zero_y:.1f}" '
                f'stroke="rgba(255,255,255,0.15)" stroke-width="1" stroke-dasharray="3,3"/>'
                f'<polyline points="{_roi_pts}" fill="none" stroke="{_roi_color}" stroke-width="2"/>'
                f'</svg>'
                f'<div style="font-size:0.75rem;color:var(--bc-dim);margin-top:4px;">'
                f'{_roi_days[0]} to {_roi_days[-1]} · latest day: {_roi_pcts[-1]:+.1f}% ROI</div>'
                f'</div>', unsafe_allow_html=True
            )

    if st.session_state.locks:
        # Group locks by timestamp (same minute = same slip)
        from collections import defaultdict
        slips = defaultdict(list)
        for lock in st.session_state["locks"]:
            ts = lock.get("timestamp","")[:16]  # group by YYYY-MM-DD HH:MM
            slip_key = f"{ts}_{lock.get('sport','')}"
            slips[slip_key].append(lock)

        # Sort slips by timestamp descending
        sorted_slips = sorted(slips.items(), key=lambda x: x[0], reverse=True)

        for slip_key, slip_locks in sorted_slips:
            ts = slip_locks[0].get("timestamp","")
            sport = slip_locks[0].get("sport","")
            n = len(slip_locks)
            multiplier = {2:3, 3:5, 4:10, 5:20}.get(n, 3)
            wager = float(slip_locks[0].get("wager") or 0)
            potential = round(wager * multiplier, 2) if wager > 0 else 0

            # Determine if this is a game bet or prop bet
            _is_game_slip = any(l.get("bet_type") == "game" for l in slip_locks)
            _slip_type_label = "🏟️ Game Bet" if _is_game_slip else f"{n}-Pick Prop Slip"
            tc = "#e8a020" if _is_game_slip else "#378add"
            _slip_wager_html = (
                f'<div style="color:#e8a020;font-size:1.0rem;">Wager: ${wager} → Potential: ${potential}</div>'
            if wager > 0 else ""
            )
            # Neither "1-Pick Slip" nor "Single Prop" reads right for a lone
            # locked pick sitting in a slip-card layout — dropping the label
            # entirely for that case rather than trying to name it "correctly".
            # Multi-pick groupings keep the label since it's unambiguous there.
            _slip_label = "" if n == 1 else f"{n}-Pick Slip"
            _slip_label_html = f'<span style="color:var(--bc-text);font-weight:700;font-size:1rem;">{_slip_label}</span> ' if _slip_label else ""
            st.markdown(
                f'<div style="background:var(--bc-bg);border:1px solid {"#e8a02033" if _is_game_slip else "var(--bc-bg2)"};border-radius:8px;padding:1rem;margin-bottom:1rem;">' +
                f'<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0.8rem;">' +
                f'<div>{_slip_label_html}' +
                f'<span style="color:var(--bc-blue);font-size:1.0rem;margin-left:8px;">{sport}</span> ' +
                f'<span style="color:var(--bc-dim);font-size:1.0rem;margin-left:8px;">{ts}</span></div>' +
                f'{_slip_wager_html}' +
                f'</div>',
                unsafe_allow_html=True
            )

            # Individual picks — condensed into a 2-column grid instead of one
            # full-width row per pick, so a 4-6 pick slip doesn't take up an
            # entire page. Single-column only for 1-pick "slips".
            _pick_cells = []
            for lock in slip_locks:
                tier_color = TIER_COLORS.get(lock.get("tier","LEAN"), "#7a8a9a")
                _pick_cells.append(
                    f'<div style="display:flex;align-items:center;justify-content:space-between;padding:0.4rem 0.5rem;border-left:3px solid {tier_color};background:var(--bc-bg-card);border-radius:0 4px 4px 0;overflow:hidden;">' +
                    f'<div style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"><span style="color:var(--bc-text);font-weight:600;font-size:0.95rem;">{lock.get("player","")}</span> ' +
                    f'<span style="color:{tier_color};font-size:0.9rem;">{lock.get("side","OVER")} {lock.get("line","")} {lock.get("prop","")}</span></div>' +
                    f'<span style="color:{tier_color};font-size:0.85rem;font-weight:600;white-space:nowrap;margin-left:6px;">{lock.get("tier","")} +{lock.get("edge",0)*100:.1f}%</span></div>'
                )
            _grid_cols = "1fr" if n == 1 else "1fr 1fr"
            st.markdown(
                f'<div style="display:grid;grid-template-columns:{_grid_cols};gap:0.3rem;margin-bottom:0.3rem;">'
                + "".join(_pick_cells) +
                '</div>',
                unsafe_allow_html=True
            )

            st.markdown('</div>', unsafe_allow_html=True)

            # Pick count → PrizePicks payout multiplier (2-pick=3x, 3-pick=5x,
            # 4-pick=10x, 5-pick=20x) used when logging WIN/LOSS. This was a
            # bare, unlabeled radio always shown full-width — confusing since
            # it already silently defaulted to the correct value (slip size).
            # Only actually needs touching for a PrizePicks Flex Play, where
            # a slip can still pay out at a reduced count even if not every
            # leg hits. Auto-default now, override tucked away for that case.
            _radio_idx = max(0, min(n-2, 3))
            n_pick = [2,3,4,5][_radio_idx]
            with st.expander(f"⚙️ Flex Play? Adjust payout count (currently {n_pick}-pick)", expanded=False):
                st.caption("Only change this if PrizePicks paid out at a different pick count than you entered (Flex Play).")
                n_pick = st.radio("Payout pick count", [2,3,4,5], index=_radio_idx, horizontal=True, key=f"pc_{slip_key}")

            # Slip-level WIN/LOSS/VOID buttons
            btn_col2, btn_col3, btn_col4 = st.columns(3)
            with btn_col2:
                if st.button("✅ WIN SLIP", key=f"win_{slip_key}", use_container_width=True):
                    for _lki, lock in enumerate(slip_locks):
                        log_manual_bet(
                            lock.get("player",""), lock.get("prop",""), lock.get("line",0),
                            lock.get("side","OVER"), lock.get("sport",""), "WIN",
                            # Real fix (2026-08-15): only the first lock in the
                            # slip carries the real wager -- was passing each
                            # lock's own full unit-size wager, so an N-pick
                            # slip's real profit was recorded N times, summing
                            # to N times the real bankroll impact. Confirmed
                            # via real history data (identical per-leg profits
                            # in N-sized groups).
                            (float(lock.get("wager") or 0) if _lki == 0 else 0.0),
                            n_pick, "prop", "PrizePicks",
                            lock.get("timestamp","")[:10],
                            tier=lock.get("tier"), edge=lock.get("edge"), prob=lock.get("prob"),
                            signals=lock.get("signal_values"), clv_capture=lock.get("clv_capture")
                        )
                    # Remove these locks
                    for lock in slip_locks:
                        if lock in st.session_state["locks"]:
                            st.session_state["locks"].remove(lock)
                    save_json_data(LOCKS_PATH, st.session_state.locks)
                    if not save_to_gist("locks", st.session_state.locks):  # persists across restarts
                        st.warning("Saved locally, but the sync to your saved history didn't go through — it may reappear later. Try again in a moment.")
                    st.rerun()
            with btn_col3:
                if st.button("❌ LOSS SLIP", key=f"loss_{slip_key}", use_container_width=True):
                    for _lki, lock in enumerate(slip_locks):
                        log_manual_bet(
                            lock.get("player",""), lock.get("prop",""), lock.get("line",0),
                            lock.get("side","OVER"), lock.get("sport",""), "LOSS",
                            # Same real fix as WIN SLIP above -- a loss should
                            # deduct the real stake once, not once per leg.
                            (float(lock.get("wager") or 0) if _lki == 0 else 0.0),
                            n_pick, "prop", "PrizePicks",
                            lock.get("timestamp","")[:10],
                            tier=lock.get("tier"), edge=lock.get("edge"), prob=lock.get("prob"),
                            signals=lock.get("signal_values"), clv_capture=lock.get("clv_capture")
                        )
                    for lock in slip_locks:
                        if lock in st.session_state["locks"]:
                            st.session_state["locks"].remove(lock)
                    save_json_data(LOCKS_PATH, st.session_state.locks)
                    if not save_to_gist("locks", st.session_state.locks):  # persists across restarts
                        st.warning("Saved locally, but the sync to your saved history didn't go through — it may reappear later. Try again in a moment.")
                    st.rerun()
            with btn_col4:
                if st.button("↩ VOID", key=f"void_{slip_key}", use_container_width=True):
                    for lock in slip_locks:
                        if lock in st.session_state["locks"]:
                            st.session_state["locks"].remove(lock)
                    save_json_data(LOCKS_PATH, st.session_state.locks)
                    if not save_to_gist("locks", st.session_state.locks):  # persists across restarts
                        st.warning("Saved locally, but the sync to your saved history didn't go through — it may reappear later. Try again in a moment.")
                    st.rerun()

            st.markdown("---")
    else:
        st.info("No active locks.")

    # ── CHECK RESULTS BUTTON ───────────────────────────
    st.markdown("---")
    if st.button("🔍 Check Results via ESPN", key="check_results_espn", use_container_width=True):
        if not st.session_state.locks:
            st.info("No active locks to check.")
        else:
            resolved = 0
            skipped = []

            # Comprehensive Elo update — also runs automatically on a timer
            # now (see near board-load above), this keeps the manual button
            # path working too for an on-demand refresh.
            run_comprehensive_elo_update()

            espn_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            sport_map = {
                "NBA": "basketball/nba",
                "MLB": "baseball/mlb",
                "NHL": "hockey/nhl",
                "NFL": "football/nfl",
                "WNBA": "basketball/wnba",
            }
            prop_stat_map = {
                "points": "PTS", "pts": "PTS",
                "rebounds": "REB", "reb": "REB",
                "assists": "AST", "ast": "AST",
                "pra": "PRA", "pts+reb+ast": "PRA",
                "pts+reb": "PTS_REB", "pts+ast": "PTS_AST",
                "reb+ast": "REB_AST", "rebs+asts": "REB_AST",
                "fantasy score": "FANTASY",
                "3-pt made": "3PM", "3pm": "3PM", "3ptm": "3PM", "threes": "3PM",
                "steals": "STL", "blocks": "BLK", "turnovers": "TO",
                "walks": "BB",  # must be checked before 'ks' below -- 'ks' is a substring of 'walks'
                "strikeouts": "SO", "strikeout": "SO", "ks": "SO", "k's": "SO",
                "hits": "H", "home runs": "HR", "home run": "HR",
                "pitches thrown": "PC", "pitches": "PC",
                "innings pitched": "IP",
                "goals": "G", "shots on goal": "SOG", "saves": "SV",
                "receptions": "REC", "pass yards": "PYDS",
                "rush yards": "RYDS", "receiving yards": "RECYDS",
                "hits+runs+rbis": "HRR",
            }

            with st.spinner("Fetching ESPN box scores..."):
                # Group locks by sport — player-prop locks only. Game-type locks
                # (spread/total/ML) have their own dedicated matchup-based
                # resolver further below and must never enter this loop: their
                # "line" field isn't guaranteed to be a plain float (e.g. some
                # spread/alt-line sources store team-prefixed strings), and a
                # single bad conversion here previously aborted resolution for
                # every other lock sharing that sport, mislabeling them all
                # with the same generic error.
                sport_locks = {}
                for lock in st.session_state["locks"]:
                    if lock.get("bet_type") == "game":
                        continue
                    s = lock.get("sport","NBA")
                    sport_locks.setdefault(s, []).append(lock)

                for sport, locks in sport_locks.items():
                    espn_sport = sport_map.get(sport)
                    if not espn_sport:
                        skipped.extend([f"{l.get('player','')} ({sport} not supported)" for l in locks])
                        continue

                    # Get today's scoreboard
                    try:
                        sb = _http.get(
                            f"https://site.api.espn.com/apis/site/v2/sports/{espn_sport}/scoreboard",
                            headers=espn_headers, timeout=10
                        )
                        if sb.status_code != 200:
                            skipped.extend([f"{l.get('player','')} (scoreboard failed)" for l in locks])
                            continue

                        events = sb.json().get("events", [])
                        final_events = [e for e in events if e.get("status",{}).get("type",{}).get("completed", False)]

                        if not final_events:
                            st.info(f"No completed {sport} games found today.")
                            continue

                        # For each completed game get box score
                        player_stats = {}  # name -> {stat: value}
                        for event in final_events:
                            game_id = event.get("id","")
                            try:
                                bs = _http.get(
                                    f"https://site.web.api.espn.com/apis/site/v2/sports/{espn_sport}/summary?event={game_id}&region=us&lang=en&contentorigin=espn",
                                    headers=espn_headers, timeout=10
                                )
                                if bs.status_code != 200:
                                    continue
                                bdata = bs.json()
                                boxscore = bdata.get("boxscore", {})

                                # ESPN summary endpoint - players array has per-player stats
                                # Each entry: {team, statistics: [{keys, labels, athletes: [{athlete, stats}]}]}
                                player_sources = boxscore.get("players", boxscore.get("teams", []))
                                for team in player_sources:
                                    for stat_group in team.get("statistics", []):
                                        stat_keys = stat_group.get("keys", stat_group.get("labels", []))
                                        for athlete in stat_group.get("athletes", []):
                                            aname = athlete.get("athlete",{}).get("displayName","")
                                            stats_vals = athlete.get("stats", [])
                                            if not aname or not stats_vals:
                                                continue
                                            aname_norm = normalize_name(aname)
                                            if aname_norm not in player_stats:
                                                player_stats[aname_norm] = {}
                                            for i, key in enumerate(stat_keys):
                                                if i < len(stats_vals):
                                                    try:
                                                        player_stats[aname_norm][key.upper()] = float(stats_vals[i])
                                                    except (ValueError, TypeError, ZeroDivisionError):
                                                        pass
                                            # Map common stat label variants
                                            for label, variants in [
                                                ("PTS",["PTS","points"]),("REB",["REB","rebounds"]),
                                                ("AST",["AST","assists"]),("STL",["STL"]),("BLK",["BLK"]),
                                                ("TO",["TO","TOV"]),("3PM",["3PM","FG3M"]),
                                                ("SO",["SO","K","Ks","STRIKEOUTS","strikeouts"]),
                                                ("H",["H","HITS","hits"]),("HR",["HR","home runs"]),
                                                ("R",["R","RUNS","runs"]),("RBI",["RBI","rbis"]),
                                                ("PC",["PC","NP","pitches","PITCHES"]),
                                                ("IP",["IP","innings"]),("BB",["BB","walks"]),
                                                ("G",["G","goals"]),("SOG",["SOG","shots"]),
                                                ("SV",["SV","saves"]),
                                            ]:
                                                for i, key in enumerate(stat_keys):
                                                    if any(v.upper() == key.upper() for v in variants) and i < len(stats_vals):
                                                        try:
                                                            player_stats[aname_norm][label] = float(stats_vals[i])
                                                        except (ValueError, TypeError, ZeroDivisionError):
                                                            pass
                            except (ValueError, TypeError):
                                continue

                        # Now resolve locks. Each lock's OUTCOME is graded
                        # independently (unchanged) so a bad value on one
                        # (e.g. an unparsable line) only skips that lock.
                        # Real fix (2026-08-15): the WAGER is a different
                        # question -- locks from the same original slip
                        # (same-minute timestamp, same sport) each carry
                        # their own full unit-size wager, so if a slip gets
                        # resolved through this auto-grader rather than the
                        # WIN/LOSS SLIP buttons (which already had this same
                        # fix applied), an N-pick slip's real profit/loss
                        # would be counted N times. Only the first lock in
                        # each same-slip group keeps its real wager here.
                        _seen_slip_keys = set()
                        for lock in locks:
                            try:
                                player = lock.get("player","")
                                prop = lock.get("prop","").lower()
                                line = float(lock.get("line",0) or 0)
                                side = lock.get("side","OVER")
                                p_norm = normalize_name(player)

                                if p_norm not in player_stats:
                                    skipped.append(f"{player} (not found in box score)")
                                    continue

                                # Find stat key -- check longest/most specific
                                # keys first (e.g. 'pts+reb+ast' before 'pts'),
                                # otherwise a short prefix key matches first by
                                # insertion order and a combo-stat prop like
                                # PRA never reaches its real mapping.
                                stat_key = None
                                for k, v in sorted(prop_stat_map.items(), key=lambda kv: -len(kv[0])):
                                    if k in prop:
                                        stat_key = v
                                        break

                                pstats = player_stats[p_norm]

                                if stat_key == "PRA":
                                    actual = pstats.get("PTS",0) + pstats.get("REB",0) + pstats.get("AST",0)
                                elif stat_key == "PTS_REB":
                                    actual = pstats.get("PTS",0) + pstats.get("REB",0)
                                elif stat_key == "PTS_AST":
                                    actual = pstats.get("PTS",0) + pstats.get("AST",0)
                                elif stat_key == "REB_AST":
                                    actual = pstats.get("REB",0) + pstats.get("AST",0)
                                elif stat_key == "FANTASY":
                                    # Same DraftKings-style formula used elsewhere for
                                    # this stat (fetch_wnba_player_stats / BDL fetch).
                                    actual = (pstats.get("PTS",0) * 1.0 + pstats.get("REB",0) * 1.2 +
                                              pstats.get("AST",0) * 1.5 + pstats.get("STL",0) * 3.0 +
                                              pstats.get("BLK",0) * 3.0 - pstats.get("TO",0) * 1.0)
                                elif stat_key and stat_key in pstats:
                                    actual = pstats[stat_key]
                                else:
                                    # Try fuzzy match
                                    actual = None
                                    for k, v in pstats.items():
                                        if stat_key and stat_key[:2] in k:
                                            actual = v
                                            break
                                    if actual is None:
                                        skipped.append(f"{player} (stat '{prop}' not found)")
                                        continue

                                if actual == line:
                                    outcome = "PUSH"
                                else:
                                    outcome = "WIN" if (side=="OVER" and actual > line) or (side=="UNDER" and actual < line) else "LOSS"
                                icon = "✅" if outcome == "WIN" else ("➖" if outcome == "PUSH" else "❌")
                                st.markdown(f"{icon} **{player}** {side} {line} {lock.get('prop','')} — actual: **{actual}** → **{outcome}**")

                                _slip_grp_key = f"{lock.get('timestamp','')[:16]}_{sport}"
                                _is_first_in_slip = _slip_grp_key not in _seen_slip_keys
                                _seen_slip_keys.add(_slip_grp_key)
                                log_manual_bet(
                                    player, lock.get("prop",""), line, side, sport, outcome,
                                    (float(lock.get("wager") or 0) if _is_first_in_slip else 0.0), 2, "prop", "PrizePicks",
                                    lock.get("timestamp","")[:10],
                                    tier=lock.get("tier"), edge=lock.get("edge"), prob=lock.get("prob"),
                                    signals=lock.get("signal_values"), clv_capture=lock.get("clv_capture")
                                )
                                if lock in st.session_state["locks"]:
                                    st.session_state["locks"].remove(lock)
                                resolved += 1
                            except (ValueError, TypeError, ZeroDivisionError) as e:
                                skipped.append(f"{lock.get('player','')} (error: {str(e)[:40]})")

                    except (ValueError, TypeError, ZeroDivisionError) as e:
                        skipped.extend([f"{l.get('player','')} (scoreboard/box-score error: {str(e)[:40]})" for l in locks])

            if resolved > 0:
                save_json_data(LOCKS_PATH, st.session_state.locks)
                save_to_gist("locks", st.session_state.locks)  # persists across restarts
                st.success(f"✅ Auto-resolved {resolved} prop pick(s) via ESPN box scores")

            # BDL fallback for any NBA picks ESPN missed
            if skipped and BDL_API_KEY:
                nba_skipped = [s for s in skipped if "nba" in s.lower() or any(
                    normalize_name(l.get("player","")) in s.lower()
                    for l in st.session_state.get("locks", []) if l.get("sport","") == "NBA"
                )]
                if nba_skipped:
                    st.caption(f"Trying BDL for {len(nba_skipped)} missed NBA picks...")
                    bdl_resolved = 0
                    for lock in st.session_state["locks"].copy():
                        if lock.get("sport","") != "NBA":
                            continue
                        try:
                            rp = _http.get(
                                "https://api.balldontlie.io/v1/players",
                                headers={"Authorization": BDL_API_KEY},
                                params={"search": lock.get("player",""), "per_page": 1},
                                timeout=8
                            )
                            if rp.status_code != 200:
                                continue
                            players_data = rp.json().get("data", [])
                            if not players_data:
                                continue
                            pid = players_data[0]["id"]
                            rs = _http.get(
                                "https://api.balldontlie.io/v1/stats",
                                headers={"Authorization": BDL_API_KEY},
                                params={"player_ids[]": pid, "per_page": 1},
                                timeout=8
                            )
                            if rs.status_code != 200:
                                continue
                            stats_data = rs.json().get("data", [])
                            if not stats_data:
                                continue
                            stat = stats_data[0]
                            prop = lock.get("prop","").lower()
                            line = float(lock.get("line",0) or 0)
                            side = lock.get("side","OVER")
                            bdl_map = {"points":"pts","rebounds":"reb","assists":"ast","steals":"stl","blocks":"blk","turnovers":"turnover","3-pt made":"fg3m","3pm":"fg3m"}
                            pra = "pra" in prop or "pts+reb+ast" in prop
                            if pra:
                                actual = float(stat.get("pts",0) or 0) + float(stat.get("reb",0) or 0) + float(stat.get("ast",0) or 0)
                            else:
                                stat_key = next((v for k,v in bdl_map.items() if k in prop), None)
                                if not stat_key:
                                    continue
                                actual = float(stat.get(stat_key,0) or 0)
                            outcome = ("WIN" if actual > line else "LOSS") if side == "OVER" else ("WIN" if actual < line else "LOSS")
                            log_manual_bet(lock.get("player",""), lock.get("prop",""), line, side, "NBA", outcome, float(lock.get("wager") or 0), 2, "prop", "PrizePicks", lock.get("timestamp","")[:10], tier=lock.get("tier"), edge=lock.get("edge"), prob=lock.get("prob"), signals=lock.get("signal_values"), clv_capture=lock.get("clv_capture"))
                            if lock in st.session_state["locks"]:
                                st.session_state["locks"].remove(lock)
                            bdl_resolved += 1
                            icon = "✅" if outcome == "WIN" else "❌"
                            st.markdown(f"{icon} **{lock.get('player','')}** (BDL) — actual: **{actual}** → **{outcome}**")
                        except (ValueError, TypeError, ZeroDivisionError):
                            continue
                    if bdl_resolved > 0:
                        save_json_data(LOCKS_PATH, st.session_state.locks)
                        save_to_gist("locks", st.session_state.locks)  # persists across restarts
                        resolved += bdl_resolved

            # Also resolve game line locks
            game_locks = [l for l in st.session_state.get("locks", []).copy() if l.get("bet_type") == "game"]
            _scoreboard_fetch_failures = []
            _espn_debug_log = []
            game_resolved = 0
            if game_locks:
                # Try ESPN scoreboard for final scores.
                # Query each distinct lock date explicitly (ESPN defaults to
                # "today" in its own clock if no `dates` param is passed, which
                # misses anything locked on a prior day) plus today's board as
                # a fallback for late-breaking completions. Also check the day
                # before/after each lock date: ESPN sometimes buckets a late
                # night game under the following UTC calendar day, so a single
                # exact-date query can miss a real, finished game.
                espn_sm = {"NBA":("basketball","nba"),"MLB":("baseball","mlb"),"NFL":("football","nfl"),"NHL":("hockey","nhl"),"WNBA":("basketball","wnba")}
                exact_dates = set()
                padding_dates = set()
                for lock in game_locks:
                    ts = (lock.get("timestamp","") or "")[:10]
                    if re.match(r"^\d{4}-\d{2}-\d{2}$", ts):
                        try:
                            d = datetime.strptime(ts, "%Y-%m-%d")
                            exact_dates.add(d.strftime("%Y%m%d"))
                            for delta in (-1, 1):
                                padding_dates.add((d + timedelta(days=delta)).strftime("%Y%m%d"))
                        except ValueError:
                            exact_dates.add(ts.replace("-",""))
                padding_dates -= exact_dates
                # Priority order matters: check each lock's own exact date first,
                # then ESPN's "today" default, then the +/-1 day padding only as a
                # last resort. Otherwise, for a back-to-back series where the same
                # two teams play on consecutive days (e.g. a 3-game series), an
                # adjacent day's game could be matched before the correct day's
                # game — silently resolving a lock against the wrong game's score.
                dates_to_check = sorted(exact_dates) + [None] + sorted(padding_dates)

                def _norm_team(s):
                    return normalize_name(s or "")

                # Pre-fetch every (sport, date) scoreboard combination in
                # parallel -- was making these calls one at a time,
                # sequentially, inside the loop below. The FETCH has no
                # ordering dependency (each call is independent), only the
                # PROCESSING of results does (exact dates must be applied
                # before padding dates for lock-resolution correctness, per
                # the comment above) -- so this parallelizes the network
                # calls while leaving the processing loop's order and logic
                # completely untouched below.
                _espn_sb_fetch_keys = []
                for _sk, (_es, _el) in espn_sm.items():
                    _sk_locks = [l for l in game_locks if (l.get("sport","") or "").upper() == _sk]
                    if not _sk_locks:
                        continue
                    for _ds in dates_to_check:
                        _espn_sb_fetch_keys.append((_sk, _es, _el, _ds))

                def _espn_sb_fetch_one(_es, _el, _ds):
                    _params = {"dates": _ds} if _ds else {}
                    try:
                        _r = _http.get(
                            f"https://site.api.espn.com/apis/site/v2/sports/{_es}/{_el}/scoreboard",
                            headers={"User-Agent":"Mozilla/5.0"}, params=_params, timeout=8
                        )
                        return (_r.status_code, _r)
                    except Exception as _e:
                        return (None, _e)

                _espn_sb_fns = [(lambda _es=_es, _el=_el, _ds=_ds: _espn_sb_fetch_one(_es, _el, _ds))
                                for _sk, _es, _el, _ds in _espn_sb_fetch_keys]
                _espn_sb_results = _fetch_parallel(_espn_sb_fns, show_progress=False)
                _espn_sb_lookup = {
                    (_sk, _ds): _result
                    for (_sk, _es, _el, _ds), _result in zip(_espn_sb_fetch_keys, _espn_sb_results)
                }

                for sport_key, (es, el) in espn_sm.items():
                    # Only bother querying this sport's scoreboard if we actually
                    # have a lock for it. This also prevents cross-sport false
                    # matches (e.g. an MLB "ATL" hitting an NBA Atlanta abbreviation).
                    sport_locks = [l for l in game_locks if (l.get("sport","") or "").upper() == sport_key]
                    if not sport_locks:
                        continue
                    for date_str in dates_to_check:
                        try:
                            _fetched = _espn_sb_lookup.get((sport_key, date_str))
                            if _fetched is None:
                                _scoreboard_fetch_failures.append(f"{sport_key} {date_str or 'today'}: no result")
                                continue
                            _status, sb = _fetched
                            if _status is None:
                                _scoreboard_fetch_failures.append(f"{sport_key} {date_str or 'today'}: {sb}")
                                continue
                            if sb.status_code != 200:
                                _scoreboard_fetch_failures.append(f"{sport_key} {date_str or 'today'}: HTTP {sb.status_code}")
                                continue
                            _all_events = sb.json().get("events",[])
                            _espn_debug_log.append(
                                f"{sport_key} {date_str or 'today'}: {len(_all_events)} events, "
                                f"{sum(1 for e in _all_events if e.get('status',{}).get('type',{}).get('completed'))} completed"
                            )
                            for event in _all_events:
                                _ev_type = event.get("status",{}).get("type",{})
                                if not _ev_type.get("completed"):
                                    # Surface relevant in-progress games in debug log
                                    # so "no games found" is diagnosable as a timing issue.
                                    _nc_comps = event.get("competitions",[{}])[0]
                                    _nc_teams = _nc_comps.get("competitors",[])
                                    if len(_nc_teams) >= 2:
                                        _nc_h = _nc_teams[0].get("team",{}).get("abbreviation","")
                                        _nc_a = _nc_teams[1].get("team",{}).get("abbreviation","")
                                        _rel_abbrs = {(l.get("player","") or "").upper() for l in sport_locks}
                                        if any((_nc_h and _nc_h.upper() in ab) or (_nc_a and _nc_a.upper() in ab) for ab in _rel_abbrs):
                                            _espn_debug_log.append(f"  ⏳ relevant but not final: {_nc_a} @ {_nc_h} — {_ev_type.get('name','?')}")
                                    continue
                                comps = event.get("competitions",[{}])[0]
                                teams = comps.get("competitors",[])
                                if len(teams) < 2: continue
                                home = teams[0]; away = teams[1]
                                home_name = home.get("team",{}).get("displayName","")
                                away_name = away.get("team",{}).get("displayName","")
                                home_abbr = home.get("team",{}).get("abbreviation","")
                                away_abbr = away.get("team",{}).get("abbreviation","")
                                home_score = float(home.get("score",0) or 0)
                                away_score = float(away.get("score",0) or 0)
                                total = home_score + away_score
                                home_norm, away_norm = _norm_team(home_name), _norm_team(away_name)
                                _relevant_abbrs = {(l.get("player","") or "").upper() for l in sport_locks}
                                _is_relevant = any(
                                    (home_abbr and home_abbr.upper() in ab) or (away_abbr and away_abbr.upper() in ab)
                                    for ab in _relevant_abbrs
                                )
                                if _is_relevant:
                                    _espn_debug_log.append(f"  completed: {away_name} ({away_abbr}) @ {home_name} ({home_abbr}) — {away_score}-{home_score}  [date query: {date_str or 'today'}]")
                                for lock in sport_locks:
                                    if lock not in st.session_state["locks"]:
                                        continue  # already resolved in an earlier date pass
                                    matchup = lock.get("player","")
                                    matchup_norm = _norm_team(matchup)
                                    home_hit = home_norm and home_norm in matchup_norm
                                    away_hit = away_norm and away_norm in matchup_norm
                                    if not home_hit and not away_hit:
                                        # fall back to abbreviation / last-word (mascot) match
                                        home_hit = bool(home_abbr) and home_abbr.lower() in matchup.lower()
                                        away_hit = bool(away_abbr) and away_abbr.lower() in matchup.lower()
                                    if not home_hit and not away_hit:
                                        home_mascot = home_norm.split(" ")[-1] if home_norm else ""
                                        away_mascot = away_norm.split(" ")[-1] if away_norm else ""
                                        home_hit = bool(home_mascot) and home_mascot in matchup_norm
                                        away_hit = bool(away_mascot) and away_mascot in matchup_norm
                                    if not home_hit and not away_hit:
                                        continue
                                    # Per-lock resolution gets its own try/except so a single
                                    # malformed lock (e.g. a "line" value that isn't a clean
                                    # float, such as a team-prefixed spread string) can't abort
                                    # processing for every other event/lock in this date pass.
                                    # This mirrors the fix already applied to the prop-lock
                                    # resolver above (bug found 2026-07-12: a bad line value on
                                    # one game lock was silently killing resolution for every
                                    # game locked that date, including otherwise-clean locks).
                                    try:
                                        pick = lock.get("side","")
                                        raw_line = lock.get("line", 0)
                                        prop_type = lock.get("prop","").upper()
                                        pick_norm = _norm_team(pick)
                                        pick_lower = pick.lower()
                                        # "side" is stored as the full pick string, e.g.
                                        # "Pittsburgh Pirates -1.5" or "Pittsburgh Pirates -150",
                                        # not a bare team name. The old check tested whether the
                                        # (longer) pick string was contained inside the (shorter)
                                        # team name — a superstring can never be a substring of a
                                        # shorter string, so pick_is_home was always False, and
                                        # every SPREAD/ML/ALT LINE lock was silently graded as if
                                        # the away side had been picked, regardless of which side
                                        # was actually locked (bug found 2026-07-12). Fixed by
                                        # checking containment the other way around. Also check
                                        # abbreviations ("MIL +1.5") alongside full names, since
                                        # legacy locks store abbreviated sides too (confirmed from
                                        # actual error report, 2026-07-13) and full-name
                                        # containment alone can't match those.
                                        pick_is_home = (bool(home_norm) and home_norm in pick_norm) or \
                                                       (bool(home_abbr) and home_abbr.lower() in pick_lower)
                                        pick_is_away = (bool(away_norm) and away_norm in pick_norm) or \
                                                       (bool(away_abbr) and away_abbr.lower() in pick_lower)

                                        # Parse "line" to a clean float. Locks created before
                                        # 2026-07-13 can still carry a legacy team-prefixed string
                                        # (e.g. "Pittsburgh Pirates -1.5") -- the 2026-07-12 fix
                                        # mistakenly targeted a dead code path (a stub that always
                                        # returned {}) so the actual bug persisted for new locks
                                        # too until fixed at the source today. Salvage legacy
                                        # strings here by extracting the trailing signed number and
                                        # flipping its sign to home-relative if the string names
                                        # the AWAY team specifically (raw upstream format names
                                        # whichever team is favored, not always home).
                                        try:
                                            line = float(raw_line)
                                        except (TypeError, ValueError):
                                            _m = re.search(r'([+-]?\d+(?:\.\d+)?)\s*$', str(raw_line))
                                            if not _m:
                                                raise ValueError(f"no parseable number in line={raw_line!r}")
                                            line = float(_m.group(1))
                                            _raw_norm = _norm_team(str(raw_line))
                                            _raw_lower = str(raw_line).lower()
                                            # Legacy strings use abbreviations ("PIT -1.5"), not
                                            # full names -- confirmed from the actual error report
                                            # (2026-07-13), so check both.
                                            _names_away = (away_norm and away_norm in _raw_norm) or \
                                                          (bool(away_abbr) and away_abbr.lower() in _raw_lower)
                                            _names_home = (home_norm and home_norm in _raw_norm) or \
                                                          (bool(home_abbr) and home_abbr.lower() in _raw_lower)
                                            if _names_away and not _names_home:
                                                line = -line

                                        outcome = None
                                        if "SPREAD" in prop_type or "ALT" in prop_type:
                                            # ALT LINE (run line / puck line) is scored identically
                                            # to a spread bet — it previously matched neither
                                            # "SPREAD" nor "TOTAL" nor "ML" and so silently never
                                            # resolved at all (bug found 2026-07-12).
                                            if not pick_is_home and not pick_is_away:
                                                raise ValueError(f"can't tell which side was picked from side={pick!r}")
                                            # "line" is always home-relative (negative = home
                                            # favored) -- home_margin>0 means home covers.
                                            # Fixed 2026-07-13: the previous formula
                                            # (pick_score - opp_score + line) only gave the
                                            # right answer for home picks; for an away pick it
                                            # needs the home_margin's sign flipped, not "line"
                                            # added to the away score directly.
                                            home_margin = home_score - away_score + line
                                            if pick_is_home:
                                                outcome = "PUSH" if home_margin == 0 else ("WIN" if home_margin > 0 else "LOSS")
                                            else:
                                                outcome = "PUSH" if home_margin == 0 else ("WIN" if home_margin < 0 else "LOSS")
                                        elif "TOTAL" in prop_type:
                                            # Stored pick text is "OVER 8.5" / "UNDER 8.5", never a
                                            # bare "OVER"/"UNDER" — the old `pick=="OVER"` exact
                                            # match never fired, so the ternary's else branch ran
                                            # every time and logged EVERY total lock as a LOSS
                                            # regardless of the actual result (bug found
                                            # 2026-07-12, likely inflating recorded losses for as
                                            # long as this path has been in use). Fixed to check
                                            # for the OVER/UNDER token anywhere in the pick text.
                                            pick_up = pick.upper()
                                            if "OVER" in pick_up:
                                                outcome = "PUSH" if total == line else ("WIN" if total > line else "LOSS")
                                            elif "UNDER" in pick_up:
                                                outcome = "PUSH" if total == line else ("WIN" if total < line else "LOSS")
                                            else:
                                                raise ValueError(f"can't tell OVER/UNDER from side={pick!r}")
                                        elif "ML" in prop_type:
                                            if not pick_is_home and not pick_is_away:
                                                raise ValueError(f"can't tell which side was picked from side={pick!r}")
                                            win_is_home = home_score > away_score
                                            outcome = "WIN" if pick_is_home == win_is_home else "LOSS"
                                        if outcome:
                                            log_manual_bet(matchup, lock.get("prop",""), line, pick, sport_key, outcome, float(lock.get("wager") or 0), 1, "game", "Bovada/MyBookie", lock.get("timestamp","")[:10], tier=lock.get("tier"), edge=lock.get("edge"), prob=lock.get("prob"), signals=lock.get("signal_values"), clv_capture=lock.get("clv_capture"))
                                            if lock in st.session_state["locks"]: st.session_state["locks"].remove(lock)
                                            resolved += 1
                                            game_resolved += 1
                                            st.markdown(f"{'✅' if outcome=='WIN' else '❌' if outcome=='LOSS' else '➖'} **{matchup}** {prop_type} {pick} {line} → {home_name} {int(home_score)}-{int(away_score)} → **{outcome}**")
                                    except (ValueError, TypeError, ZeroDivisionError) as _lock_err:
                                        _espn_debug_log.append(f"  ⚠️ failed to resolve {matchup} {lock.get('prop','')} (line={lock.get('line')!r}, side={lock.get('side')!r}): {_lock_err}")
                                        continue
                        except (ValueError, TypeError, ZeroDivisionError): continue

            if game_resolved == 0:
                if game_locks:
                    st.info("No completed games found yet for your locked matchups. Try after games finish, or double-check the lock's date if it's been a while.")
                    if _scoreboard_fetch_failures:
                        with st.expander(f"⚠️ {len(_scoreboard_fetch_failures)} ESPN scoreboard request(s) failed"):
                            for f in _scoreboard_fetch_failures:
                                st.caption(f)
                    if _espn_debug_log:
                        with st.expander("🔍 ESPN scoreboard debug (what was actually checked)"):
                            for d in _espn_debug_log:
                                st.caption(d)
                            st.caption("Your locked matchups: " + ", ".join(l.get("player","") for l in game_locks))
                else:
                    st.info("No completed games found yet. Try after games finish.")
                # Even if no game locks resolved this pass, prop locks earlier in
                # the same click may have — refresh so Active Locks isn't stale.
                if resolved > 0:
                    st.rerun()
            else:
                save_json_data(LOCKS_PATH, st.session_state.locks)
                save_to_gist("locks", st.session_state.locks)  # persists across restarts
                st.success(f"✅ Auto-resolved {game_resolved} game pick(s) via ESPN scoreboard")
                st.rerun()

            if skipped:
                with st.expander(f"⚠️ {len(skipped)} picks need manual resolution"):
                    for s in skipped:
                        st.caption(s)

    # Ledger section
    st.markdown('<div class="bc-section-header">📊 Ledger</div>', unsafe_allow_html=True)
    if st.session_state.get("history", []):
        total_bets = len(st.session_state.get("history", []))
        wins = sum(1 for h in st.session_state.get("history", []) if h.get("outcome") == "WIN")
        losses = sum(1 for h in st.session_state.get("history", []) if h.get("outcome") == "LOSS")
        net = sum(h.get("net", 0) for h in st.session_state.get("history", []))
        hit_rate = wins / (wins + losses) if (wins + losses) > 0 else 0
        net_color = "#22c55e" if net >= 0 else "#e04040"
        st.markdown(
            f'<div style="display:flex;gap:1rem;flex-wrap:wrap;margin-bottom:1rem;">' +
            f'<div style="background:var(--bc-bg);border:1px solid var(--bc-border);border-radius:6px;padding:0.5rem 1rem;text-align:center;"><div style="color:var(--bc-dim);font-size:1.05rem;">Total Bets</div><div style="color:var(--bc-text);font-weight:700;font-size:1.3rem;">{total_bets}</div></div>' +
            f'<div style="background:var(--bc-bg);border:1px solid #22c55e33;border-radius:6px;padding:0.5rem 1rem;text-align:center;"><div style="color:var(--bc-dim);font-size:1.05rem;">Wins</div><div style="color:#22c55e;font-weight:700;font-size:1.3rem;">{wins}</div></div>' +
            f'<div style="background:var(--bc-bg);border:1px solid #e0404033;border-radius:6px;padding:0.5rem 1rem;text-align:center;"><div style="color:var(--bc-dim);font-size:1.05rem;">Losses</div><div style="color:#e04040;font-weight:700;font-size:1.3rem;">{losses}</div></div>' +
            f'<div style="background:var(--bc-bg);border:1px solid var(--bc-border);border-radius:6px;padding:0.5rem 1rem;text-align:center;"><div style="color:var(--bc-dim);font-size:1.05rem;">Hit Rate</div><div style="color:var(--bc-text);font-weight:700;font-size:1.3rem;">{hit_rate:.1%}</div></div>' +
            f'<div style="background:var(--bc-bg);border:1px solid var(--bc-border);border-radius:6px;padding:0.5rem 1rem;text-align:center;"><div style="color:var(--bc-dim);font-size:1.05rem;">Net P&L</div><div style="color:{net_color};font-weight:700;font-size:1.3rem;">${net:+.2f}</div></div>' +
            f'</div>',
            unsafe_allow_html=True
        )
    else:
        st.markdown(empty_state_html("📈", "No bet history yet",
                     "Log a bet or lock a pick to start building your track record here."),
                     unsafe_allow_html=True)

    # ROI by Tier + Sport
    if st.session_state.get("history", []):
        st.markdown("---")
        st.markdown("#### 📊 ROI by Tier & Sport")
        roi_col1, roi_col2 = st.columns(2)
        with roi_col1:
            st.markdown("**By Tier**")
            tier_stats_roi = {}
            for h in st.session_state.get("history", []):
                t = h.get("tier","Unknown")
                if t not in tier_stats_roi:
                    tier_stats_roi[t] = {"w":0,"l":0,"net":0}
                if h.get("outcome")=="WIN": tier_stats_roi[t]["w"]+=1
                elif h.get("outcome")=="LOSS": tier_stats_roi[t]["l"]+=1
                tier_stats_roi[t]["net"]+=float(h.get("net",0) or 0)
            _tier_roi_html = []
            for t in ["SOVEREIGN","ELITE","APPROVED","LEAN"]:
                if t in tier_stats_roi:
                    d = tier_stats_roi[t]
                    total = d["w"]+d["l"]
                    hr = d["w"]/total if total>0 else 0
                    nc = "#22c55e" if d["net"]>=0 else "#e04040"
                    _tier_roi_html.append(f'<div style="display:flex;justify-content:space-between;padding:3px 0;font-size:0.9rem;"><span style="color:var(--bc-text);">{t}</span><span style="color:var(--bc-muted);">{d["w"]}W-{d["l"]}L ({hr:.0%})</span><span style="color:{nc};">${d["net"]:+.2f}</span></div>')
            if _tier_roi_html:
                st.markdown("".join(_tier_roi_html), unsafe_allow_html=True)
        with roi_col2:
            st.markdown("**By Sport**")
            sport_stats_roi = {}
            for h in st.session_state.get("history", []):
                s = h.get("sport","Unknown")
                if s not in sport_stats_roi:
                    sport_stats_roi[s] = {"w":0,"l":0,"net":0}
                if h.get("outcome")=="WIN": sport_stats_roi[s]["w"]+=1
                elif h.get("outcome")=="LOSS": sport_stats_roi[s]["l"]+=1
                sport_stats_roi[s]["net"]+=float(h.get("net",0) or 0)
            _sport_roi_html = []
            for s, d in sorted(sport_stats_roi.items(), key=lambda x: x[1]["net"], reverse=True):
                total = d["w"]+d["l"]
                hr = d["w"]/total if total>0 else 0
                nc = "#22c55e" if d["net"]>=0 else "#e04040"
                _sport_roi_html.append(f'<div style="display:flex;justify-content:space-between;padding:3px 0;font-size:0.9rem;"><span style="color:var(--bc-text);">{s}</span><span style="color:var(--bc-muted);">{d["w"]}W-{d["l"]}L ({hr:.0%})</span><span style="color:{nc};">${d["net"]:+.2f}</span></div>')
            if _sport_roi_html:
                st.markdown("".join(_sport_roi_html), unsafe_allow_html=True)

# ----- TAB 4: HISTORY -----
with tabs[13]:
    st.markdown('<div class="bc-section-header">📈 Full Bet History</div>', unsafe_allow_html=True)

    st.caption("Daily = today's essentials. Weekly = signal/model audits. Seasonal = deep reference data (Bankroll Intelligence, Season Regime, full Calibration Dashboard).")
    _view = st.radio("View", ["Daily", "Weekly", "Seasonal", "All"], horizontal=True, key="history_view_selector")

    # ── Resolved Picks by Tier -- real breakdown of settled bets, always
    # visible regardless of Daily/Weekly/Seasonal view since it's a
    # standing reference, not a time-scoped section.
    _rpt_resolved = [h for h in st.session_state.get("history", []) if h.get("outcome") in ("WIN", "LOSS")]
    if _rpt_resolved:
        _rpt_tier_counts = {}
        for _h in _rpt_resolved:
            _t = _h.get("tier") or "Unknown"
            _rpt_tier_counts[_t] = _rpt_tier_counts.get(_t, 0) + 1
        _rpt_total = len(_rpt_resolved)
        _rpt_order = ["SOVEREIGN", "ELITE", "APPROVED", "LEAN"]
        _rpt_colors = {"SOVEREIGN": "#f5c518", "ELITE": "#1e90ff", "APPROVED": "#e8a020", "LEAN": "#2a3a4a"}
        _rpt_bars = ""
        for _t in _rpt_order + [t for t in _rpt_tier_counts if t not in _rpt_order]:
            _n = _rpt_tier_counts.get(_t, 0)
            if not _n:
                continue
            _pct = _n / _rpt_total * 100
            _rpt_bars += (
                f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">'
                f'<span style="width:80px;font-size:0.75rem;color:var(--bc-dim);">{_t.title()}</span>'
                f'<div style="flex:1;height:8px;background:rgba(255,255,255,0.06);border-radius:4px;">'
                f'<div style="width:{_pct}%;height:100%;background:{_rpt_colors.get(_t, "#6a7a8a")};border-radius:4px;"></div></div>'
                f'<span style="width:50px;font-size:0.75rem;color:var(--bc-dim);text-align:right;">{_n} ({_pct:.0f}%)</span>'
                f'</div>'
            )
        with st.expander(f"📊 Resolved Picks by Tier — {_rpt_total} total"):
            st.markdown(_rpt_bars, unsafe_allow_html=True)

    if _view in ("Daily", "All"):

        # ── Auto-resolve CLV for settled bets ──────────────────────────────
        # Buchdahl methodology: compare placement odds vs current market (closing proxy)
        if st.session_state.get("history"):
            _resolved_hist, _clv_changed = resolve_clv_records(st.session_state.get("history", []))
            if _clv_changed:
                st.session_state.history = _resolved_hist
                save_json_data(HISTORY_PATH, st.session_state.get("history", []))

        # ── CLV Performance Dashboard ───────────────────────────────────────
        _clv_sum = get_clv_summary(st.session_state.get("history", []))
        _clv_sum = _clv_sum or {"n_resolved": 0, "avg_clv": 0, "beat_rate": 0, "grade": "INSUFFICIENT"}
        if _clv_sum.get("n_resolved", 0) > 0:

            # ── Brier Score + Calibration Z-Score ──────────────────────────────
            _brier  = compute_brier_score(st.session_state.get("history", []))
            _zscore = compute_calibration_zscore(st.session_state.get("history", []))
            _bs_life = _brier.get("lifetime") or {}
            if _bs_life:
                st.markdown("### 🎯 Model Calibration — Brier Score & Z-Score")
                st.caption("Brier Score: 0=perfect, 0.25=random coin flip. Alert if BS>0.25 or |Z|>2.0")
                _bc1,_bc2,_bc3,_bc4 = st.columns(4)
                _bs_val = _bs_life.get("brier_score",0)
                _bs_color = "#22c55e" if _bs_val < 0.22 else ("#ffd700" if _bs_val < 0.25 else "#e04040")
                _bc1.markdown(f'<div style="background:var(--bc-bg-card);border:1px solid var(--bc-border);border-radius:8px;padding:10px;text-align:center;"><div style="font-size:9px;color:var(--bc-dim);text-transform:uppercase">Brier Score (All)</div><div style="font-size:22px;font-weight:700;color:{_bs_color}">{_bs_val:.3f}</div><div style="font-size:12px;color:{_bs_color}">{_bs_life.get("grade","")}</div></div>', unsafe_allow_html=True)
                _bs_l30 = (_brier.get("L30") or {}).get("brier_score")
                _bc2.markdown(f'<div style="background:var(--bc-bg-card);border:1px solid var(--bc-border);border-radius:8px;padding:10px;text-align:center;"><div style="font-size:9px;color:var(--bc-dim);text-transform:uppercase">Brier L30</div><div style="font-size:22px;font-weight:700;color:#e8f0f8">{_bs_l30:.3f if _bs_l30 else "—"}</div><div style="font-size:12px;color:#6a7a8a">30 day window</div></div>', unsafe_allow_html=True)
                _ll = _bs_life.get("log_loss", 0)
                _bc3.markdown(f'<div style="background:var(--bc-bg-card);border:1px solid var(--bc-border);border-radius:8px;padding:10px;text-align:center;"><div style="font-size:9px;color:var(--bc-dim);text-transform:uppercase">Log Loss</div><div style="font-size:22px;font-weight:700;color:#e8f0f8">{_ll:.3f}</div><div style="font-size:12px;color:#6a7a8a">lower=better</div></div>', unsafe_allow_html=True)
                _z = _zscore.get("z_score")
                _z_color = "#22c55e" if _z and abs(_z) <= 2.0 else "#e04040"
                _z_label = _zscore.get("direction", "insufficient data")
                _bc4.markdown(f'<div style="background:var(--bc-bg-card);border:1px solid var(--bc-border);border-radius:8px;padding:10px;text-align:center;"><div style="font-size:9px;color:var(--bc-dim);text-transform:uppercase">CLV Z-Score</div><div style="font-size:22px;font-weight:700;color:{_z_color}">{f"{_z:+.2f}" if _z else "—"}</div><div style="font-size:12px;color:{_z_color}">{_z_label}</div></div>', unsafe_allow_html=True)
                if _bs_life.get("alert"):
                    st.warning("⚠️ Brier Score > 0.25 — model underperforming random. Throttle user weight by 10% and audit feature extraction.")
                if _zscore.get("alert"):
                    st.warning(f"⚠️ CLV Z-Score |{_z:.2f}| > 2.0 — model is {_z_label}. Consider rebalancing sharp anchor weights.")

                # Per-sport Brier breakdown + adaptive Kelly multiplier
                _per_sport = _brier.get("per_sport", {})
                if _per_sport:
                    st.markdown("**Per-Sport Calibration & Adaptive Kelly Multiplier**")
                    st.caption("Kelly fraction auto-scales based on per-sport Brier score. Green = boosted, red = throttled.")
                    _sp_cols = st.columns(min(len(_per_sport), 6))
                    for _i, (_sp, _sd) in enumerate(sorted(_per_sport.items())):
                        if _i >= 6:
                            break
                        _sp_bs    = _sd.get("brier_score", 0.25)
                        _sp_grade = _sd.get("grade", "—")
                        _base     = 0.15
                        _adapted  = adaptive_kelly_fraction(_base, [], sport=_sp)  # uses global BS
                        # recalculate with actual data
                        try:
                            import math as _m
                            _anchor_bs = 0.22
                            _scale = _anchor_bs + _m.log(_anchor_bs / max(_sp_bs, 0.01)) * 2.5
                            _scale = max(0.33, min(1.5, _scale))
                            _adapted = round(_base * _scale, 3)
                        except Exception:
                            pass
                        _sp_color = "#22c55e" if _adapted > _base else ("#e8a020" if _adapted > _base * 0.6 else "#e04040")
                        _mult_str = f"{'↑' if _adapted >= _base else '↓'}{_adapted/(_base or 1):.1f}x Kelly"
                        _sp_cols[_i].markdown(
                            f'<div style="background:var(--bc-bg-card);border:1px solid var(--bc-border);border-radius:8px;padding:8px;text-align:center;">'
                            f'<div style="font-size:9px;color:var(--bc-dim);text-transform:uppercase">{_sp}</div>'
                            f'<div style="font-size:16px;font-weight:700;color:{_sp_color}">BS {_sp_bs:.3f}</div>'
                            f'<div style="font-size:11px;color:{_sp_color}">{_mult_str}</div>'
                            f'<div style="font-size:9px;color:#6a7a8a">{_sp_grade} · n={_sd.get("n","?")}</div>'
                            f'</div>', unsafe_allow_html=True
                        )
                st.markdown("---")

                # ── Online Signal Performance Monitoring ─────────────────────
                _sig_perf = compute_signal_performance(
                    st.session_state.get("history", []), window_days=30
                )
                if _sig_perf:
                    st.markdown("**Signal Feature Importance — L30 Days**")
                    st.caption("Signals with negative lift are being auto-penalized in weight. Positive lift = boosted.")
                    _sig_cols = st.columns(min(len(_sig_perf), 7))
                    for _si, (_sig, _sp) in enumerate(sorted(_sig_perf.items(),
                                                              key=lambda x: -abs(x[1]["lift"]))):
                        if _si >= 7: break
                        _lift      = _sp["lift"]
                        _factor    = _sp["penalty_factor"]
                        _useful    = _sp["is_useful"]
                        _sc        = "#22c55e" if _useful and _lift > 0.03 else ("#e04040" if not _useful else "#e8a020")
                        _icon      = "✅" if _factor > 1 else ("⚠️" if _factor < 1 else "➖")
                        _sig_cols[_si].markdown(
                            f'<div style="background:var(--bc-bg-card);border:1px solid var(--bc-border);border-radius:8px;padding:8px;text-align:center;">'
                            f'<div style="font-size:9px;color:var(--bc-dim);text-transform:uppercase">{_sig}</div>'
                            f'<div style="font-size:16px;font-weight:700;color:{_sc}">{_lift:+.3f}</div>'
                            f'<div style="font-size:11px;color:{_sc}">{_icon} {_factor:.2f}x wt</div>'
                            f'<div style="font-size:9px;color:#6a7a8a">n={_sp["n_high"]}</div>'
                            f'</div>', unsafe_allow_html=True
                        )
                else:
                    st.info("Signal performance monitoring requires 15+ resolved bets.")

                # ── Game Exposure / Covariance Panel ─────────────────────────
                _open_bets = st.session_state.get("open_bets", [])
                if _open_bets:
                    st.markdown("**Portfolio Game Exposure (Covariance Monitor)**")
                    st.caption(f"Max single-game exposure cap: {int(_MAX_GAME_EXPOSURE*100)}% bankroll. Bets over this receive a correlation haircut.")
                    _exp = compute_game_exposure(_open_bets)
                    if _exp["over_limit"]:
                        st.warning(f"⚠️ Over-concentrated: max game exposure {_exp['max_game']:.0%} exceeds {int(_MAX_GAME_EXPOSURE*100)}% cap — Kelly haircut active")
                    _exp_rows = [{"Game": g, "Exposure": f"{v:.1%}"} for g, v in
                                 sorted(_exp["by_game"].items(), key=lambda x: -x[1])[:10]]
                    if _exp_rows:
                        import pandas as _pd_exp
                        st.markdown(_bc_df_html(_pd_exp.DataFrame(_exp_rows)), unsafe_allow_html=True)

            st.markdown("---")
            st.markdown("### 📊 Closing Line Value (CLV) — Buchdahl Methodology")
            st.caption(
                f"CLV measures whether you beat the no-vig closing line (Pinnacle+Circa consensus). "
                f"Per Buchdahl: **{_clv_sum['n_resolved']} resolved bets** | "
                f"Need 50+ for significance, 1000+ for full confidence."
            )
            _clv_grade  = _clv_sum["grade"]
            _clv_color  = {"ELITE":"#22c55e","GOOD":"#0ea5a0","POSITIVE":"#e8a020",
                           "NEUTRAL":"#6a7a8a","NEGATIVE":"#e04040","INSUFFICIENT":"#6a7a8a"}.get(_clv_grade,"#6a7a8a")
            _cc1,_cc2,_cc3,_cc4 = st.columns(4)
            _cc1.markdown(
                f'<div style="background:var(--bc-bg-card);border:1px solid var(--bc-border);border-radius:8px;padding:10px;text-align:center;">'
                f'<div style="font-size:9px;color:var(--bc-dim);text-transform:uppercase">Avg CLV (No-Vig)</div>'
                f'<div style="font-size:22px;font-weight:700;color:{_clv_color}">'
                f'{_clv_sum["avg_clv"]:+.2%}</div>'
                f'<div style="font-size:12px;color:{_clv_color}">{_clv_grade}</div></div>',
                unsafe_allow_html=True
            )
            _cc2.markdown(
                f'<div style="background:var(--bc-bg-card);border:1px solid var(--bc-border);border-radius:8px;padding:10px;text-align:center;">'
                f'<div style="font-size:9px;color:var(--bc-dim);text-transform:uppercase">Beat Close Rate</div>'
                f'<div style="font-size:22px;font-weight:700;color:#e8f0f8">'
                f'{_clv_sum["beat_rate"]:.1%}</div>'
                f'<div style="font-size:12px;color:#6a7a8a">{_clv_sum["n_resolved"]} bets</div></div>',
                unsafe_allow_html=True
            )
            _be_needed = 50 - _clv_sum["n_resolved"]
            _cc3.markdown(
                f'<div style="background:var(--bc-bg-card);border:1px solid var(--bc-border);border-radius:8px;padding:10px;text-align:center;">'
                f'<div style="font-size:9px;color:var(--bc-dim);text-transform:uppercase">To Significance</div>'
                f'<div style="font-size:22px;font-weight:700;color:#e8f0f8">'
                f'{"✅" if _be_needed <= 0 else str(max(0,_be_needed))+" more"}</div>'
                f'<div style="font-size:12px;color:#6a7a8a">50 bet threshold</div></div>',
                unsafe_allow_html=True
            )
            _full_conf = 1000 - _clv_sum["n_resolved"]
            _cc4.markdown(
                f'<div style="background:var(--bc-bg-card);border:1px solid var(--bc-border);border-radius:8px;padding:10px;text-align:center;">'
                f'<div style="font-size:9px;color:var(--bc-dim);text-transform:uppercase">Full Confidence</div>'
                f'<div style="font-size:22px;font-weight:700;color:#e8f0f8">'
                f'{"✅" if _full_conf <= 0 else str(max(0,_full_conf))+" more"}</div>'
                f'<div style="font-size:12px;color:#6a7a8a">1000 bet threshold</div></div>',
                unsafe_allow_html=True
            )
            st.markdown("---")

            # ── Pinnacle CLV Tracker (moved here — was 1600 lines away in its
            # own separate section, even though it's the same CLV concept from
            # a second data source. Now sits right next to Buchdahl CLV above.
            st.markdown("### 📍 Pinnacle CLV Tracker")
            pinnacle_data = load_json_data(PINNACLE_LINES_PATH, [])
            if len(pinnacle_data) >= 5:
                avg_pclv = sum(r.get("pinnacle_clv", 0) for r in pinnacle_data) / len(pinnacle_data)
                pos_rate = sum(1 for r in pinnacle_data if r.get("positive", False)) / len(pinnacle_data)
                p1, p2, p3 = st.columns(3)
                p1.metric("Avg Pinnacle CLV", f"{avg_pclv:+.2f}")
                p2.metric("Positive Rate", f"{pos_rate:.1%}")
                p3.metric("Bets Tracked", len(pinnacle_data))
            else:
                # NOTE (2026-07): this used to stay stuck at "need 5 more" no
                # matter how many bets were resolved (174+), because
                # record_pinnacle_line() — the only function that writes
                # PINNACLE_LINES_PATH — was built but never called from any
                # lock-creation button. It's now wired into the EV Optimizer,
                # Portfolio Builder, Slip Analyzer, and Game Lines lock actions,
                # so this should start filling in from new locks going forward.
                # There used to be a "Backfill CLV from History" button here too
                # — removed, because it can't actually work: Pinnacle's closing
                # line at the time of a past bet isn't something history ever
                # stored, so the old backfill just wrote a fake 0.0 CLV
                # placeholder (and to the wrong file). Real CLV can only be
                # captured going forward, at lock time.
                st.info(
                    f"Pinnacle CLV activates after 5 resolved bets. Need {max(0, 5 - len(pinnacle_data))} more.\n\n"
                    "This only counts bets locked *after* Pinnacle capture was wired in — it can't be "
                    "backfilled from already-resolved bets, since the Pinnacle closing line at that moment "
                    "was never recorded. Lock a few new picks and this will start filling in."
                )
            st.markdown("---")
            # ── Per-book CLV breakdown ─────────────────────────────────────────
            _clv_by_book = {}
            for _cr in _clv_top:
                _bk = _cr.get("source", "") or "Unknown"
                if not _bk:
                    _bk = "Unknown"
                _cv = _cr.get("clv_vs_close") or _cr.get("clv", 0) or 0
                if _bk not in _clv_by_book:
                    _clv_by_book[_bk] = {"vals": [], "beats": 0}
                _clv_by_book[_bk]["vals"].append(float(_cv))
                if float(_cv) > 0:
                    _clv_by_book[_bk]["beats"] += 1
            if _clv_by_book:
                st.markdown("**CLV by Book**")
                _book_rows = []
                for _bk, _bd in sorted(_clv_by_book.items()):
                    _n  = len(_bd["vals"])
                    _avg = sum(_bd["vals"]) / _n if _n else 0
                    _br  = _bd["beats"] / _n if _n else 0
                    _book_rows.append({"Book": _bk, "Bets": _n,
                                       "Avg CLV": f"{_avg:+.2%}", "Beat Rate": f"{_br:.0%}"})
                _bk_html = '<table style="width:100%;border-collapse:collapse;font-size:12px;">'
                _bk_html += '<tr style="color:var(--bc-dim);text-transform:uppercase;font-size:10px;">'
                for _hdr in ["Book","Bets","Avg CLV","Beat Rate"]:
                    _bk_html += f'<th style="padding:4px 8px;text-align:left;">{_hdr}</th>'
                _bk_html += "</tr>"
                for _row in _book_rows:
                    _rc = "#22c55e" if "+" in _row["Avg CLV"] else "#e04040"
                    _bk_html += f'<tr style="border-top:1px solid #1a2a3a;">'
                    _bk_html += f'<td style="padding:4px 8px;color:var(--bc-text);">{_row["Book"]}</td>'
                    _bk_html += f'<td style="padding:4px 8px;color:var(--bc-muted);">{_row["Bets"]}</td>'
                    _bk_html += f'<td style="padding:4px 8px;color:{_rc};font-weight:700;">{_row["Avg CLV"]}</td>'
                    _bk_html += f'<td style="padding:4px 8px;color:var(--bc-muted);">{_row["Beat Rate"]}</td>'
                    _bk_html += "</tr>"
                _bk_html += "</table>"
                st.markdown(_bk_html, unsafe_allow_html=True)
            st.markdown("---")


        if st.session_state.get("history", []):
            hist_df = pd.DataFrame(st.session_state.get("history", []))
            hist_df = hist_df.iloc[::-1].reset_index(drop=True)

            # Quick stats row at top
            total_bets = len(st.session_state.get("history", []))
            wins = sum(1 for h in st.session_state.get("history", []) if h.get("outcome") == "WIN")
            losses = sum(1 for h in st.session_state.get("history", []) if h.get("outcome") == "LOSS")
            pending = sum(1 for h in st.session_state.get("history", []) if h.get("outcome") == "PENDING")
            total_net = sum(h.get("net", 0) for h in st.session_state.get("history", []))
            win_rate = wins / (wins + losses) if (wins + losses) > 0 else 0
            net_color = "#22c55e" if total_net >= 0 else "#e04040"
            st.markdown(
                f'<div style="display:flex;gap:1rem;margin-bottom:1rem;flex-wrap:wrap;">' +
                f'<div style="background:var(--bc-bg);border:1px solid #22c55e33;border-radius:6px;padding:0.5rem 1rem;text-align:center;"><div style="color:var(--bc-muted);font-size:1.05rem;text-transform:uppercase;">Wins</div><div style="color:#22c55e;font-weight:700;font-size:1.3rem;">{wins}</div></div>' +
                f'<div style="background:var(--bc-bg);border:1px solid #e0404033;border-radius:6px;padding:0.5rem 1rem;text-align:center;"><div style="color:var(--bc-muted);font-size:1.05rem;text-transform:uppercase;">Losses</div><div style="color:#e04040;font-weight:700;font-size:1.3rem;">{losses}</div></div>' +
                f'<div style="background:var(--bc-bg);border:1px solid #e8a02033;border-radius:6px;padding:0.5rem 1rem;text-align:center;"><div style="color:var(--bc-muted);font-size:1.05rem;text-transform:uppercase;">Pending</div><div style="color:#e8a020;font-weight:700;font-size:1.3rem;">{pending}</div></div>' +
                f'<div style="background:var(--bc-bg);border:1px solid var(--bc-border);border-radius:6px;padding:0.5rem 1rem;text-align:center;"><div style="color:var(--bc-muted);font-size:1.05rem;text-transform:uppercase;">Hit Rate</div><div style="color:var(--bc-text);font-weight:700;font-size:1.3rem;">{win_rate:.1%}</div></div>' +
                f'<div style="background:var(--bc-bg);border:1px solid var(--bc-border);border-radius:6px;padding:0.5rem 1rem;text-align:center;"><div style="color:var(--bc-muted);font-size:1.05rem;text-transform:uppercase;">Net P&L</div><div style="color:{net_color};font-weight:700;font-size:1.3rem;">${total_net:+.2f}</div></div>' +
                f'</div>',
                unsafe_allow_html=True
            )

            # Filters
            filter_col1, filter_col2, filter_col3, filter_col4 = st.columns([1,1,1,1])
            with filter_col1:
                tier_filter_h = st.multiselect(
                    "Filter by Tier",
                    ["SOVEREIGN","ELITE","APPROVED","LEAN","PASS","N/A"],
                    default=["SOVEREIGN","ELITE","APPROVED","LEAN","PASS","N/A"],
                    key="hist_tier_filter"
                )
            with filter_col2:
                outcome_filter = st.multiselect(
                    "Filter by Result",
                    ["WIN","LOSS","PENDING"],
                    default=["WIN","LOSS","PENDING"],
                    key="hist_outcome_filter"
                )
            with filter_col3:
                all_sports = ["NBA","MLB","NFL","NHL","WNBA","UFC","Soccer","Golf","Tennis"]
                sport_filter_h = st.multiselect(
                    "Filter by Sport",
                    all_sports,
                    default=all_sports,
                    key="hist_sport_filter"
                )
            with filter_col4:
                # Real-stake-only toggle -- 171 of 280 resolved bets in the real
                # ledger are auto-tracked picks with no wager logged (BDL/Bovada/
                # PrizePicks resolvers track model accuracy whether or not a real
                # bet was placed). They're legitimate for signal/hit-rate tracking
                # but drag down or distort P&L/ROI views if mixed in silently.
                # This isolates the two views instead of picking one by default.
                wager_only_h = st.checkbox(
                    "💰 Real Stake Only",
                    value=False,
                    key="hist_wager_only",
                    help="Hide bets with no wager logged (auto-tracked picks that weren't actually staked). "
                         "Toggle on to see only real-money results and true ROI."
                )

            # Apply filters
            filtered_hist = hist_df.copy()
            if "tier" in filtered_hist.columns:
                filtered_hist = filtered_hist[filtered_hist["tier"].fillna("N/A").isin(tier_filter_h)]
            if "outcome" in filtered_hist.columns:
                filtered_hist = filtered_hist[filtered_hist["outcome"].fillna("PENDING").isin(outcome_filter)]
            if "sport" in filtered_hist.columns:
                filtered_hist = filtered_hist[filtered_hist["sport"].fillna("NBA").isin(sport_filter_h)]
            if wager_only_h and "wager" in filtered_hist.columns:
                filtered_hist = filtered_hist[filtered_hist["wager"].fillna(0).astype(float) > 0]

            # Friendly column names
            display_cols = {
                "timestamp": "Date", "player": "Player", "prop": "Stat",
                "line": "Line", "side": "Side", "tier": "Tier",
                "wager": "Wager ($)", "outcome": "Result", "net": "Net ($)",
                "sport": "Sport", "source": "Platform"
            }
            show_cols = [c for c in display_cols.keys() if c in filtered_hist.columns]
            filtered_hist_display = filtered_hist[show_cols].rename(columns=display_cols)
            st.markdown(_bc_df_html(filtered_hist_display), unsafe_allow_html=True)
            st.caption(f"Showing {len(filtered_hist)} of {len(hist_df)} bets" + (" — real stake only" if wager_only_h else ""))
            if wager_only_h and len(filtered_hist):
                _wo_resolved = filtered_hist[filtered_hist["outcome"].isin(["WIN","LOSS"])] if "outcome" in filtered_hist.columns else filtered_hist
                if len(_wo_resolved) and "wager" in _wo_resolved.columns and "net" in _wo_resolved.columns:
                    _wo_wagered = _wo_resolved["wager"].astype(float).sum()
                    _wo_net = _wo_resolved["net"].astype(float).sum()
                    _wo_roi = (_wo_net / _wo_wagered * 100) if _wo_wagered else 0
                    st.metric("Real-Stake ROI", f"{_wo_roi:+.1f}%", help=f"${_wo_net:+.2f} net on ${_wo_wagered:.2f} actually wagered, {len(_wo_resolved)} resolved bets")

            # Legend
            with st.expander("📖 How to read this tab"):
                st.markdown("""
    **Tier guide:**
    - 🟢 **SOVEREIGN** — Highest conviction, edge ≥15%
    - 🔵 **ELITE** — Strong edge, 10-15%
    - 🟠 **APPROVED** — Solid edge, 5-10%
    - ⚪ **LEAN** — Small edge, 2-5%
    - ⬛ **PASS** — No edge, avoid

    **Result:** WIN = hit the line, LOSS = missed, PENDING = not yet resolved

    **Net ($):** Profit or loss after wager. Green = profit, Red = loss.

    **CLV:** Closing Line Value — positive CLV means you got a better price than the market closed at.
                """)
            st.warning("⚠️ This permanently deletes all logged bets and cannot be undone.")
            _confirm_history_clear_ht = st.checkbox("I understand this cannot be undone", key="confirm_history_clear_ht")
            if st.button("Clear History", disabled=not _confirm_history_clear_ht):
                st.session_state.history = []
                save_json_data(HISTORY_PATH, [])
                save_to_gist("history", st.session_state.get("history", []))
                st.rerun()
            st.markdown("---")
            if len(st.session_state.get("history", [])) >= 5:
                resolved = hist_df[hist_df["outcome"].isin(["WIN","LOSS"])] if "outcome" in hist_df.columns else pd.DataFrame()
                if not resolved.empty:
                    col_a, col_b = st.columns(2)
                    with col_a:
                        st.markdown("**Hit Rate by Tier**")
                        if "tier" in resolved.columns:
                            tier_stats_h = resolved.groupby("tier").apply(lambda x: pd.Series({"Bets": len(x), "Hit Rate": f"{(x['outcome']=='WIN').mean():.1%}", "Net": f"${x['net'].sum():.2f}" if "net" in x else "\u2014"})).reset_index()
                            st.markdown(_bc_df_html(tier_stats_h), unsafe_allow_html=True)
                    with col_b:
                        st.markdown("**Hit Rate by Sport**")
                        if "sport" in resolved.columns:
                            sport_stats_h = resolved.groupby("sport").apply(lambda x: pd.Series({"Bets": len(x), "Hit Rate": f"{(x['outcome']=='WIN').mean():.1%}", "Net": f"${x['net'].sum():.2f}" if "net" in x else "\u2014"})).reset_index()
                            st.markdown(_bc_df_html(sport_stats_h), unsafe_allow_html=True)
                    if "net" in resolved.columns:
                        rc = resolved.copy()
                        rc["cumulative"] = DEFAULT_BANKROLL + rc["net"].cumsum()
                        st.line_chart(rc["cumulative"])
        st.markdown("---")
    if _view in ("Daily", "All"):
        st.markdown("### \U0001f4b0 ROI by Category")
        resolved_h = [h for h in st.session_state.get("history", []) if h.get("outcome") in ("WIN","LOSS")]
        if len(resolved_h) >= 5:
            pick_roi = {}
            for h in resolved_h:
                pc = h.get("pick_count", 2)
                if pc not in pick_roi:
                    pick_roi[pc] = {"bets": 0, "wagered": 0, "returned": 0}
                pick_roi[pc]["bets"] += 1
                pick_roi[pc]["wagered"] += h.get("wager", 0)
                if h["outcome"] == "WIN":
                    pick_roi[pc]["returned"] += h.get("wager", 0) * PRIZEPICKS_MULTIPLIERS.get(pc, 3.0)
            roi_rows = []
            for pc in sorted(pick_roi.keys()):
                data = pick_roi[pc]
                if data["wagered"] > 0:
                    roi = (data["returned"] - data["wagered"]) / data["wagered"] * 100
                    roi_rows.append({"Pick Count": f"{pc}-pick", "Bets": data["bets"], "Wagered": f"${data['wagered']:.2f}", "Returned": f"${data['returned']:.2f}", "ROI": f"{'🟢' if roi > 0 else '🔴'} {roi:+.1f}%"})
            if roi_rows:
                st.markdown(_bc_df_html(pd.DataFrame(roi_rows)), unsafe_allow_html=True)
        else:
            st.caption("Need 5+ resolved bets for ROI analysis.")

        st.markdown("---")
    if _view in ("Daily", "All"):
        st.markdown("### 🔬 Loss Post-Mortem Analyzer")
        st.caption("Select any losing bet to understand why it lost — variance, bad process, or known risk factor.")

        _losses_pm = [h for h in st.session_state.get("history", []) if h.get("outcome") == "LOSS"]
        if not _losses_pm:
            st.info("No losing bets logged yet. Post-mortem activates when you log your first LOSS.")
        else:
            # Build selector labels
            _loss_labels = []
            for _lh in _losses_pm[-30:]:  # last 30 losses
                _lbl = f"{_lh.get('timestamp','?')[:10]} | {_lh.get('player','?')} {_lh.get('prop','?')} {_lh.get('line','?')} {_lh.get('side','?')} [{_lh.get('tier','?')}]"
                _loss_labels.append(_lbl)

            _sel_loss = st.selectbox("Select a losing bet to analyze:", _loss_labels[::-1], key="pm_loss_sel")
            _sel_idx  = _loss_labels[::-1].index(_sel_loss)
            _sel_bet  = _losses_pm[-30:][::-1][_sel_idx]

            # Run post-mortem
            _pm = analyze_loss_postmortem(_sel_bet, st.session_state.get("history", []))

            # Verdict header
            _pm_colors = {
                "REAL PATTERN":      "#e04040",
                "GOOD PROCESS":      "#22c55e",
                "LIKELY VARIANCE":   "#0ea5a0",
                "MARGINAL BET":      "#f59e0b",
                "RISK FACTOR":       "#f59e0b",
                "UNCLEAR":           "#6a7a8a",
            }
            _pm_color = next((v for k,v in _pm_colors.items() if k in _pm["verdict"]), "#6a7a8a")
            _conf_color = {"HIGH":"#22c55e","MEDIUM":"#f59e0b","LOW":"#6a7a8a"}.get(_pm["confidence"],"#6a7a8a")

            st.markdown(
                f'<div style="background:var(--bc-bg-card);border:2px solid {_pm_color}44;border-radius:12px;padding:16px;margin:8px 0">'
                f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">'
                f'<span style="font-size:18px;font-weight:700;color:{_pm_color}">⚖️ {_pm["verdict"]}</span>'
                f'<span style="font-size:12px;color:{_conf_color};background:{_conf_color}22;padding:3px 10px;border-radius:10px">Confidence: {_pm["confidence"]}</span>'
                f'</div>'
                f'<div style="font-size:15px;color:#e2e8f0;line-height:1.5;margin-bottom:10px;">{_pm.get("plain_english_summary","")}</div>'
                f'<div style="color:#8899aa;font-size:12px">{_sel_bet.get("player","")} {_sel_bet.get("prop","")} {_sel_bet.get("line","")} {_sel_bet.get("side","")} | {_sel_bet.get("sport","")} | {_sel_bet.get("tier","")} | Edge: {_sel_bet.get("edge",0):.1%} | Prob: {_sel_bet.get("prob",0):.0%}</div>'
                f'</div>',
                unsafe_allow_html=True
            )

            # Detail cards
            _pm_cols = st.columns(2)
            with _pm_cols[0]:
                if _pm["clv_note"]:
                    st.markdown(f"**📈 Closing Line Value**")
                    st.caption(_pm["clv_note"])
                if _pm["variance_note"]:
                    st.markdown(f"**🎲 Variance**")
                    st.caption(_pm["variance_note"])
                if _pm["tier_note"]:
                    st.markdown(f"**🏆 Tier**")
                    st.caption(_pm["tier_note"])

            with _pm_cols[1]:
                if _pm["signals_note"]:
                    st.markdown(f"**⚡ Signal Flags**")
                    st.caption(_pm["signals_note"])
                if _pm["pattern_note"]:
                    st.markdown(f"**📊 Historical Pattern**")
                    st.caption(_pm["pattern_note"])

            # Reasons breakdown
            if _pm["reasons"]:
                st.markdown("**🔍 Analysis Breakdown:**")
                for _r in _pm["reasons"]:
                    st.caption(f"• {_r}")

            # Recommendation
            st.markdown(
                f'<div style="background:#0a1a0a;border:1px solid #22c55e44;border-radius:8px;padding:12px;margin-top:8px">'
                f'<span style="color:#22c55e;font-weight:600">💡 Recommendation:</span>'
                f'<span style="color:var(--bc-text);font-size:13px"> {_pm["recommendation"]}</span>'
                f'</div>',
                unsafe_allow_html=True
            )


        st.markdown("---")
        with st.expander("📊 Advanced Performance Metrics — Injury Tracker", expanded=False):
            st.markdown("### \U0001f921 Injury Performance Tracker")
            injury_results, n_injured = analyze_injury_performance()
            if injury_results is None:
                st.info(f"Injury tracker activates after 20 injury-tagged resolved bets. Current: {n_injured}. Need {20 - n_injured} more.")
            else:
                col_i1, col_i2, col_i3 = st.columns(3)
                col_i1.metric("Injured WR", f"{injury_results['injured_wr']:.1%}")
                col_i2.metric("Healthy WR", f"{injury_results['healthy_wr']:.1%}")
                col_i3.metric("WR Gap", f"{injury_results['wr_gap']:+.1%}")
        st.markdown("---")
    if _view in ("Weekly", "All"):
        st.markdown("### \U0001f52c Signal Performance Analysis")
        signal_results, n_resolved = analyze_signal_performance()
        if signal_results is None:
            st.info(f"Signal analysis activates at 20 resolved bets. Current: {n_resolved}. Need {20 - n_resolved} more.")
        else:
            st.success(f"\u2705 Analyzing {n_resolved} resolved bets")
            st.markdown(_bc_df_html(pd.DataFrame(signal_results)), unsafe_allow_html=True)

        # ── Engine 2: Loss Pattern Analyzer ──
        st.markdown("---")

        # ── Signal Correlation Matrix ──────────────────────────────
    if _view in ("Weekly", "All"):
        st.markdown("### 🔗 Signal Correlation Matrix")
        st.caption("Are your signals independent? High phi (ϕ) = signals fire together frequently = possible double-counting. Run this after 20+ bets.")
        _perf_data = load_json_data(SIGNAL_PERFORMANCE_PATH, [], mem_ttl=60)
        _corr_rows, _corr_n, _corr_warnings = compute_signal_correlation_matrix(_perf_data)
        if _corr_rows is None:
            st.info(f"Correlation matrix activates at 20 resolved bets. Current: {_corr_n}.")
        else:
            if _corr_warnings:
                for w in _corr_warnings:
                    st.warning(w)
            else:
                st.success("✅ No high-overlap signal pairs detected — signals appear independent.")
            _show_all_corr = st.checkbox("Show all signal pairs", value=False, key="show_all_corr")
            _display_rows = _corr_rows if _show_all_corr else [r for r in _corr_rows if r["Phi (ϕ)"] != 0][:10]
            if _display_rows:
                st.markdown(_bc_df_html(pd.DataFrame(_display_rows)), unsafe_allow_html=True)
            st.caption("Phi (ϕ): 0=uncorrelated, 1=always fire together. Co-occur %: when Signal A fires, how often does B also fire?")

        st.markdown("---")

        # ── Signal Lift Analysis ───────────────────────────────────
        with st.expander("📊 Advanced Performance Metrics — Signal Lift Analysis", expanded=False):
            st.markdown("### 📈 Signal Lift Analysis")
            st.caption("Does each signal actually improve results above the base model? Incremental lift = win rate improvement from adding that signal.")
            _lift_rows, _lift_n = compute_signal_lift_analysis(_perf_data)
            if _lift_rows is None:
                st.info(f"Lift analysis activates at 30 resolved bets. Current: {_lift_n}.")
            else:
                _negative = [r for r in _lift_rows if "Negative" in r["Grade"]]
                if _negative:
                    st.warning(f"⚠️ {len(_negative)} signal(s) showing negative drag — consider reducing weight: {', '.join(r['Signal'] for r in _negative)}")
                st.markdown(_bc_df_html(pd.DataFrame(_lift_rows)), unsafe_allow_html=True)
                st.caption("Incremental Lift = WR(Base+Signal) minus WR(Base only). Positive = signal adds value. Negative = signal hurts model.")

        st.markdown("---")

        # ── Signal Stability Analysis ──────────────────────────────
    if _view in ("Weekly", "All"):
        st.markdown("### 📅 Signal Stability (30d / 90d / Season)")
        st.caption("Are signals consistent over time? Unstable signals may be chasing recent variance. Use this to audit optimizer decisions.")
        _stab_rows, _stab_n = compute_signal_stability(_perf_data)
        if _stab_rows is None:
            st.info(f"Stability analysis activates at 30 resolved bets. Current: {_stab_n}.")
        else:
            _unstable = [r for r in _stab_rows if "Unstable" in r["Stability"]]
            if _unstable:
                st.warning(f"⚠️ Unstable signals detected (high variance across windows): {', '.join(r['Signal'] for r in _unstable)}")
            else:
                st.success("✅ All signals showing stable win rates across time windows.")
            st.markdown(_bc_df_html(pd.DataFrame(_stab_rows)), unsafe_allow_html=True)
            st.caption("Stable = WR consistent across L30d/L90d/Season. Unstable = hot/cold streaks — reduce optimizer trust for that signal.")

        st.markdown("---")
        st.checkbox("🔧 Show ML debug on Game Lines", key="show_ml_debug", value=False)
    if _view in ("Weekly", "All"):
        st.markdown("### 🧠 Loss Pattern Analysis")
        _lp = st.session_state.get("loss_patterns", [])
        _resolved_count = len([h for h in st.session_state.get("history",[]) if h.get("outcome") in ("WIN","LOSS")])
        if _resolved_count < 20:
            st.info(f"Loss pattern analysis activates at 20 resolved bets. Current: {_resolved_count}. Need {20 - _resolved_count} more.")
        elif not _lp:
            st.success("✅ No significant loss patterns detected — model performing as expected across all segments.")
        else:
            st.warning(f"⚠️ {len(_lp)} pattern(s) detected in your bet history — review and consider adjustments:")
            for pattern in _lp:
                st.markdown(f"- {pattern}")
            st.caption("These patterns auto-update every time you load the board. Weight optimizer will incorporate them at 50 bets.")

        # ── NFL Prop ROI by Position ──────────────────────────────
        if st.session_state.get("last_sport") == "NFL" or any(h.get("sport") == "NFL" for h in st.session_state.get("history", [])):
            st.markdown("---")
            st.markdown("### 🏈 NFL Prop ROI by Position")
            st.caption("Tracks win rate and ROI separately for QB/RB/WR/TE/K props. Activates after 10 NFL bets.")
            _nfl_bets = [h for h in st.session_state.get("history", []) if h.get("sport") == "NFL" and h.get("outcome") in ("WIN","LOSS")]
            if len(_nfl_bets) >= 10:
                # Classify prop by position
                _pos_groups = {
                    "QB":  ["pass", "completion", "interception", "qb", "touchdown pass"],
                    "RB":  ["rush", "carry", "rb", "running back"],
                    "WR":  ["receiv", "target", "catch", "wr", "wide"],
                    "TE":  ["tight", "te "],
                    "DEF": ["sack", "tackle", "defense"],
                }
                _pos_stats = {}
                for _nb in _nfl_bets:
                    _prop_lower = (_nb.get("prop","") + " " + _nb.get("player","")).lower()
                    _pos = "Other"
                    for _pg, _keywords in _pos_groups.items():
                        if any(kw in _prop_lower for kw in _keywords):
                            _pos = _pg
                            break
                    if _pos not in _pos_stats:
                        _pos_stats[_pos] = {"wins":0,"losses":0,"stake":0,"payout":0}
                    _ps = _pos_stats[_pos]
                    _stake = float(_nb.get("wager",0) or 0)
                    _ps["stake"] += _stake
                    if _nb["outcome"] == "WIN":
                        _ps["wins"] += 1
                        _mult = PRIZEPICKS_MULTIPLIERS.get(_nb.get("pick_count",2), 3.0)
                        _ps["payout"] += _stake * _mult
                    else:
                        _ps["losses"] += 1
                _nfl_pos_rows = []
                for _pos, _ps in sorted(_pos_stats.items()):
                    _total = _ps["wins"] + _ps["losses"]
                    _wr = _ps["wins"] / _total if _total else 0
                    _roi = (_ps["payout"] - _ps["stake"]) / _ps["stake"] if _ps["stake"] else 0
                    _nfl_pos_rows.append({
                        "Position":  _pos,
                        "Bets":      _total,
                        "Win Rate":  f"{_wr:.1%}",
                        "ROI":       f"{_roi:+.1%}",
                        "Net Units": f"{(_ps['payout']-_ps['stake']):.1f}u",
                    })
                if _nfl_pos_rows:
                    st.markdown(_bc_df_html(pd.DataFrame(_nfl_pos_rows)), unsafe_allow_html=True)
            else:
                st.info(f"NFL position ROI activates after 10 NFL bets. Current: {len(_nfl_bets)}.")

        # ── Bankroll Intelligence ───────────────────────────────
        st.markdown("---")
    if _view in ("Seasonal", "All"):
        st.markdown("### 🏦 Bankroll Intelligence")
        st.caption("Model-aware stake sizing. Adjusts Kelly fraction based on current model confidence.")
        _bi = compute_bankroll_multiplier()
        if not isinstance(_bi, dict):
            _bi = {}
        _bi.setdefault("color", "#FFFFFF")
        _bi.setdefault("label", "Standard")
        _bi.setdefault("multiplier", 1.0)
        _bi.setdefault("kelly_advised", 0.0)
        _bi.setdefault("reasons_up", [])
        _bi.setdefault("reasons_down", [])
        if not isinstance(_bi, dict):
            _bi = {}
        _bi.setdefault("color", "#8a9ab0")
        _bi.setdefault("label", "Normal")
        _bi.setdefault("multiplier", 1.0)
        _bi.setdefault("kelly_advised", 0.02)
        _bi.setdefault("reasons_up", [])
        _bi.setdefault("reasons_down", [])
        st.markdown(
            f'<div style="background:var(--bc-bg);border:1px solid {_bi["color"]}44;border-radius:8px;padding:0.8rem;">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;">'
            f'<span style="color:{_bi["color"]};font-size:1.1rem;font-weight:700;">{_bi["label"]}</span>'
            f'<span style="color:var(--bc-text);font-size:1.4rem;font-weight:700;">{_bi["multiplier"]:.2f}x</span>'
            f'</div>'
            f'<div style="color:var(--bc-muted);font-size:0.85rem;margin-top:4px;">'
            f'Kelly advised: {_bi["kelly_advised"]:.1%} of bankroll per bet</div>'
            + (f'<div style="color:#22c55e;font-size:0.85rem;">✅ {" · ".join(_bi["reasons_up"])}</div>' if _bi["reasons_up"] else "")
            + (f'<div style="color:#e04040;font-size:0.85rem;">⚠️ {" · ".join(_bi["reasons_down"])}</div>' if _bi["reasons_down"] else "")
            + '</div>',
            unsafe_allow_html=True
        )


        # ── Scanbet Auto-Fetch — All Sports (runs in user's browser) ────────────
        # JS runs in YOUR browser on board load — bypasses Cloudflare automatically.
        # Sports with known filterId: direct GetEvents call.
        # Sports with sportId: GenerateFilterHash first, then GetEvents.
        # Result pushed to Gist → BetCouncil reads on next board load.
        _scanbet_sport_map = {
            "MLB":    {"filterId": "f3e9a7ebfb522115", "sportId": 8},
            "NBA":    {"filterId": None,                "sportId": 4},
            "NFL":    {"filterId": None,                "sportId": 11},
            "UFC":    {"filterId": None,                "sportId": 7},
            "TENNIS": {"filterId": "c470e5ce21f765bf", "sportId": None},
            "SOCCER": {"filterId": "195765953ceb385a", "sportId": None},
            "NHL":    {"filterId": None,                "sportId": 6},
        }
        _sbs = _scanbet_sport_map.get(sport_sel, {})
        _sb_filter_id = _sbs.get("filterId","") or ""
        _sb_sport_id  = _sbs.get("sportId") or 0

        if _sb_filter_id or _sb_sport_id:
            _scanbet_js = f"""
            <script>
            (function() {{
                var sport = '{sport_sel}';
                var filterId = '{_sb_filter_id}';
                var sportId  = {_sb_sport_id};
                var gistId   = '{GITHUB_GIST_ID}';
                var gistTok  = '{GITHUB_TOKEN}';
                var throttleKey = 'scanbet_last_run_' + sport;
                var now = Date.now();
                var lastRun = localStorage.getItem(throttleKey);
                if (lastRun && (now - parseInt(lastRun)) < 300000) {{
                    console.log('[BetCouncil] Scanbet ' + sport + ': skipping (ran < 5min ago)');
                    return;
                }}

                var GQL_URL = 'https://scanbet.io/graphql';
                var EVENTS_QUERY = 'query GetEvents($input:GetEventsInput!){{events(input:$input){{pageData{{sports{{sportName leagues{{leagueName events{{eventId home away eventOdds{{odds parseTime}}}}}}}}}}totalPages page}}}}';

                function pushToGist(data) {{
                    return fetch('https://api.github.com/gists/' + gistId, {{
                        method: 'PATCH',
                        headers: {{
                            'Authorization': 'token ' + gistTok,
                            'Content-Type': 'application/json',
                            'Accept': 'application/vnd.github.v3+json'
                        }},
                        body: JSON.stringify({{files: {{'betcouncil_scanbet_drops.json': {{content: JSON.stringify(data, null, 2)}}}}}})
                    }}).then(function(r) {{
                        if (r.ok) {{
                            localStorage.setItem(throttleKey, Date.now().toString());
                            console.log('[BetCouncil] ✅ Scanbet ' + sport + ' drops pushed (' + (data.data && data.data.events ? 'got events' : 'no events') + ')');
                        }}
                    }});
                }}

                function getEvents(fid) {{
                    fetch(GQL_URL, {{
                        method: 'POST',
                        headers: {{'content-type': 'application/json'}},
                        body: JSON.stringify({{
                            operationName: 'GetEvents',
                            variables: {{input: {{filterId: fid, page: 1, bookmakerId: 1}}}},
                            query: EVENTS_QUERY
                        }})
                    }}).then(function(r) {{ return r.json(); }})
                      .then(function(data) {{ pushToGist(data); }})
                      .catch(function(e) {{ console.log('[BetCouncil] Scanbet GetEvents error:', e); }});
                }}

                if (filterId) {{
                    // Direct — already have filterId
                    getEvents(filterId);
                }} else if (sportId) {{
                    // Generate filterId first via GenerateFilterHash mutation
                    fetch(GQL_URL, {{
                        method: 'POST',
                        headers: {{'content-type': 'application/json'}},
                        body: JSON.stringify({{
                            operationName: 'GenerateFilterHash',
                            variables: {{input: {{
                                bookmakerId: 1,
                                filters: {{updateTimeFilter:'all_time',startTimeFilter:'all_time',minInitialMax:0,minCurrentMax:0}},
                                selectedSports: {{sportIds:[sportId],allSportsSelected:false,allLeaguesSelected:true,selectedLeagues:[{{sportId:sportId,allSportLeaguesSelected:true,leagueIds:[]}}]}}
                            }}}},
                            query: 'mutation GenerateFilterHash($input:GenerateFilterHashInput!){{generateFilterHash(input:$input){{filterId}}}}'
                        }})
                    }}).then(function(r) {{ return r.json(); }})
                      .then(function(d) {{
                        var fid = d && d.data && d.data.generateFilterHash && d.data.generateFilterHash.filterId;
                        if (fid) {{ getEvents(fid); }}
                        else {{ console.log('[BetCouncil] Scanbet: could not generate filterId for sport', sportId); }}
                      }})
                      .catch(function(e) {{ console.log('[BetCouncil] Scanbet GenerateFilterHash error:', e); }});
                }}
            }})();
            </script>
            """
            st.components.v1.html(_scanbet_js, height=0, scrolling=False)

        # ── Auto-harvester: EVSharps JWT + Caesars WAF + FanDuel + BetMGM ────────
        # All run silently in YOUR browser on every board load.
        # No need to visit any site manually — BetCouncil does it automatically.
        _harvester_js = f"""
        <script>
        (function() {{
            var GIST_ID  = '{GITHUB_GIST_ID}';
            var GIST_TOK = '{GITHUB_TOKEN}';
            var sport    = '{sport_sel}';

            // BUG FIX (2026-07): pushGist() used to fire concurrent PATCH requests
            // against the same Gist whenever multiple harvest sources completed
            // around the same time (common right after page load). GitHub's Gist
            // API returns 409 Conflict when two PATCHes race, and the old code
            // never checked r.ok or retried -- it logged nothing on failure, so
            // some harvested updates were silently dropped every session with no
            // visible symptom. Fixed by serializing all writes through a single
            // promise chain (only one PATCH in flight at a time) with automatic
            // retry-with-backoff specifically on 409.
            var __bcGistQueue = Promise.resolve();

            function __bcPushGistOnce(filename, content) {{
                return fetch('https://api.github.com/gists/' + GIST_ID, {{
                    method: 'PATCH',
                    headers: {{
                        'Authorization': 'token ' + GIST_TOK,
                        'Content-Type': 'application/json',
                        'Accept': 'application/vnd.github.v3+json'
                    }},
                    body: JSON.stringify({{files: {{[filename]: {{content: JSON.stringify(content, null, 2)}}}}}})
                }});
            }}

            function pullGist(filename) {{
                return fetch('https://api.github.com/gists/' + GIST_ID, {{
                    method: 'GET',
                    headers: {{
                        'Authorization': 'token ' + GIST_TOK,
                        'Accept': 'application/vnd.github.v3+json'
                    }}
                }}).then(function(r) {{ return r.json(); }})
                  .then(function(d) {{
                    var f = d.files && d.files[filename];
                    if (!f || !f.content) return null;
                    try {{ return JSON.parse(f.content); }} catch (e) {{ return null; }}
                  }}).catch(function(e) {{ return null; }});
            }}

            function pushGist(filename, content) {{
                __bcGistQueue = __bcGistQueue.then(function() {{
                    return __bcPushGistOnce(filename, content).then(function(r) {{
                        if (r.ok) {{
                            console.log('[BetCouncil] ✅ Auto-pushed: ' + filename);
                            return;
                        }}
                        if (r.status === 409) {{
                            // Conflict from a racing write elsewhere -- wait briefly and retry once.
                            return new Promise(function(resolve) {{ setTimeout(resolve, 800); }})
                                .then(function() {{ return __bcPushGistOnce(filename, content); }})
                                .then(function(r2) {{
                                    if (r2.ok) {{
                                        console.log('[BetCouncil] ✅ Auto-pushed (after retry): ' + filename);
                                    }} else {{
                                        console.log('[BetCouncil] ⚠️ Gist push failed after retry: ' + filename + ' status=' + r2.status);
                                    }}
                                }});
                        }}
                        console.log('[BetCouncil] ⚠️ Gist push failed: ' + filename + ' status=' + r.status);
                    }}).catch(function(e) {{
                        console.log('[BetCouncil] Gist push error:', filename, e.message);
                    }});
                }});
                return __bcGistQueue;
            }}

            function throttled(key, ms, fn) {{
                var last = localStorage.getItem('bc_harvest_' + key);
                if (last && (Date.now() - parseInt(last)) < ms) return;
                localStorage.setItem('bc_harvest_' + key, Date.now().toString());
                fn();
            }}

            // ── 1. EVSharps JWT auto-refresh (every 50 min) ─────────────────────
            // BUG FIX (2026-07): refresh_token was hardcoded to the same seed
            // value on every call. Supabase rotates the refresh token on each
            // use (standard OAuth2 refresh-token rotation) -- after the first
            // successful rotation, every later attempt kept sending the now-
            // invalidated original token, failed silently (.catch only logs to
            // console, no Gist push), and never recovered on its own. This is
            // the direct explanation for betcouncil_tokens.json / betcouncil_
            // evsharps_ev_*.json staying stale for 9+ days regardless of
            // whether a browser tab was open to run this at all. Now pulls the
            // last-saved refresh token from Gist first and uses that.
            throttled('evsharps', 3000000, function() {{
                pullGist('betcouncil_tokens.json').then(function(saved) {{
                    var currentRefresh = (saved && saved.ev_refresh) || 'z325a7doims5';
                    fetch('https://nkdhryqpiulrepmphwmt.supabase.co/auth/v1/token?grant_type=refresh_token', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json',
                                   'apikey': '{SUPABASE_ANON}'}},
                        body: JSON.stringify({{refresh_token: currentRefresh}})
                    }}).then(function(r) {{ return r.json(); }})
                      .then(function(d) {{
                        if (d.access_token) {{
                            pushGist('betcouncil_tokens.json', {{
                                ev_jwt: d.access_token,
                                ev_refresh: d.refresh_token || currentRefresh,
                                captured_at: new Date().toISOString(),
                                source: 'betcouncil_auto_harvest'
                            }});
                            console.log('[BetCouncil] ✅ EVSharps JWT refreshed automatically');
                        }} else {{
                            console.log('[BetCouncil] ⚠️ EVSharps refresh returned no access_token -- refresh token may be dead, needs manual re-auth:', JSON.stringify(d));
                        }}
                      }}).catch(function(e) {{ console.log('[BetCouncil] EVSharps refresh error:', e); }});
                }});
            }});

            // ── 2. Caesars auth token passive capture (hooks fetch, pushes on every authenticated call) ──
            if (!window.__bcCzrHooked) {{
                window.__bcCzrHooked = true;
                var __bcOrigFetchCzr = window.fetch;
                window.fetch = function() {{
                    var __bcArgsCzr = arguments;
                    var __bcUrlCzr = (typeof __bcArgsCzr[0] === 'string') ? __bcArgsCzr[0] : (__bcArgsCzr[0] && __bcArgsCzr[0].url);
                    var __bcReqInitCzr = __bcArgsCzr[1] || {{}};

                    return __bcOrigFetchCzr.apply(this, __bcArgsCzr).then(function(response) {{
                        try {{
                            if (__bcUrlCzr && __bcUrlCzr.indexOf('api.americanwagering.com') !== -1) {{
                                var __bcAuthCzr = '';
                                var __bcWafCzr = '';
                                var __bcSessCzr = '';
                                try {{
                                    var __bcHeadersCzr = __bcReqInitCzr.headers || {{}};
                                    if (__bcHeadersCzr instanceof Headers) {{
                                        __bcAuthCzr = __bcHeadersCzr.get('authorization') || '';
                                        __bcWafCzr = __bcHeadersCzr.get('x-aws-waf-token') || '';
                                        __bcSessCzr = __bcHeadersCzr.get('sessionid') || '';
                                    }} else {{
                                        __bcAuthCzr = __bcHeadersCzr['authorization'] || __bcHeadersCzr['Authorization'] || '';
                                        __bcWafCzr = __bcHeadersCzr['x-aws-waf-token'] || '';
                                        __bcSessCzr = __bcHeadersCzr['sessionid'] || '';
                                    }}
                                }} catch (eHeadCzr) {{}}

                                if (__bcAuthCzr && __bcAuthCzr.toLowerCase().indexOf('bearer ') === 0) {{
                                    var __bcBearerCzr = __bcAuthCzr.substring(7);
                                    if (__bcBearerCzr !== window.__bcCzrLastBearer) {{
                                        window.__bcCzrLastBearer = __bcBearerCzr;
                                        pushGist('betcouncil_caesars_tokens.json', {{
                                            bearer_jwt: __bcBearerCzr,
                                            waf_token: __bcWafCzr,
                                            session_id: __bcSessCzr,
                                            captured_at: new Date().toISOString(),
                                            source: 'betcouncil_auto_harvest_passive'
                                        }});
                                        console.log('[BetCouncil] ✅ Caesars tokens captured (bearer + waf)');
                                    }}
                                }}
                            }}
                        }} catch (eOuterCzr) {{
                            console.log('[BetCouncil] Caesars passive capture error:', eOuterCzr.message);
                        }}
                        return response;
                    }});
                }};
                console.log('[BetCouncil] Caesars passive harvester hooked — browse Caesars to capture tokens');
            }}



            // ── 3. FanDuel odds passive capture (hooks fetch, pushes on every getMarketPrices call) ──
            if (!window.__bcFdHooked) {{
                window.__bcFdHooked = true;
                var __bcOrigFetch = window.fetch;
                window.fetch = function() {{
                    var __bcArgs = arguments;
                    var __bcUrl = (typeof __bcArgs[0] === 'string') ? __bcArgs[0] : (__bcArgs[0] && __bcArgs[0].url);
                    var __bcReqInit = __bcArgs[1] || {{}};

                    return __bcOrigFetch.apply(this, __bcArgs).then(function(response) {{
                        try {{
                            if (__bcUrl && __bcUrl.indexOf('getMarketPrices') !== -1) {{
                                // Capture x-px-context from the outgoing request headers
                                var __bcPxContext = '';
                                try {{
                                    var __bcHeaders = __bcReqInit.headers || {{}};
                                    if (__bcHeaders instanceof Headers) {{
                                        __bcPxContext = __bcHeaders.get('x-px-context') || '';
                                    }} else {{
                                        __bcPxContext = __bcHeaders['x-px-context'] || '';
                                    }}
                                }} catch (eHead) {{}}

                                var __bcClone = response.clone();
                                __bcClone.json().then(function(data) {{
                                    if (Array.isArray(data) && data.length) {{
                                        pushGist('betcouncil_fd_props_' + sport + '.json', {{
                                            sport: sport,
                                            captured_at: new Date().toISOString(),
                                            markets: data,
                                            source: 'betcouncil_auto_harvest_passive'
                                        }});
                                        console.log('[BetCouncil] ✅ FanDuel odds captured: ' + data.length + ' markets');

                                        if (__bcPxContext) {{
                                            pushGist('fanduel_tokens.json', {{
                                                px_context: __bcPxContext,
                                                captured_at: new Date().toISOString(),
                                                source: 'betcouncil_auto_harvest_passive'
                                            }});
                                        }}
                                    }}
                                }}).catch(function(eJson) {{
                                    console.log('[BetCouncil] FanDuel odds parse error:', eJson.message);
                                }});
                            }}
                        }} catch (eOuter) {{
                            console.log('[BetCouncil] FanDuel passive capture error:', eOuter.message);
                        }}
                        return response;
                    }});
                }};
                console.log('[BetCouncil] FanDuel passive harvester hooked — browse FanDuel props to capture odds');
            }}


            // ── 4. BetMGM: retired 2026-07-12 (in-app fetch), then fully removed
            //    2026-07-17 -- scripts/tampermonkey_betmgm_harvester.user.js turned out
            //    to be producing no data at all (confirmed via Gist), and
            //    scrape_betmgm_curlffi() in betcouncil_auto_scraper.py already covers
            //    BetMGM server-side via WAF impersonation-profile rotation. The
            //    LINE_DEVIATION cross-book signal now sources BetMGM from that pool
            //    directly (filtered by Book=="BetMGM") instead of a Gist file.
            //    Tampermonkey BetMGM harvester can be disabled/uninstalled.

            // ── Action Network in-app harvester removed 2026-07-17: it wrote to
            //    betcouncil_actionnetwork_{{sport}}.json under a "data" key, while
            //    actionnetwork_refresh.py (GitHub Actions cron, unauthenticated,
            //    confirmed live) writes the SAME filename under a "games" key --
            //    two processes racing to overwrite one file with incompatible
            //    shapes. The cron script already covers this server-side with no
            //    browser needed; removing the conflicting write, not just a
            //    redundant one.

            // ── 6. Covers.com consensus betting % (every 20 min) ─────────
            // URL FIX (Jul 9 2026): old www.covers.com/api/widget/matchups path
            // is unconfirmed/likely dead along with the old /consensus page;
            // contests.covers.com/consensus/topconsensus is the confirmed-live
            // current page (server-rendered HTML, not JSON — parsed server-side
            // by fetch_covers_consensus() in fetchers.py instead of here).
            var coversSportMap = {{'MLB':'mlb','NBA':'nba','NFL':'nfl','NHL':'nhl','WNBA':'wnba','CFL':'cfl'}};
            var coversSport = coversSportMap[sport];
            if (coversSport) {{
                throttled('covers_' + sport, 1200000, function() {{
                    fetch('https://contests.covers.com/consensus/topconsensus/' + coversSport + '/overall', {{
                        headers: {{'Accept':'text/html','Referer':'https://www.covers.com/'}}
                    }}).then(function(r){{return r.text();}}).then(function(html){{
                        pushGist('betcouncil_covers_' + sport + '.json', {{sport:sport,captured_at:new Date().toISOString(),html:html,source:'betcouncil_auto_harvest'}});
                    }}).catch(function(e){{console.log('[BetCouncil] Covers error:',e.message);}});
                }});
            }}

            // ── 7. DraftKings props (every 20 min) ───────────────────────
            var dkCatMap = {{'MLB':84240,'NBA':42648,'NFL':88808,'NHL':42133,'UFC':9}};
            var dkCat = dkCatMap[sport];
            if (dkCat) {{
                throttled('dk_props_' + sport, 1200000, function() {{
                    fetch('https://sportsbook.draftkings.com/api/odds/v1/categories/' + dkCat + '/subcategories?format=json', {{
                        headers:{{'Accept':'application/json','Referer':'https://sportsbook.draftkings.com/'}}
                    }}).then(function(r){{return r.json();}}).then(function(data){{
                        pushGist('betcouncil_dk_props_' + sport + '.json', {{sport:sport,captured_at:new Date().toISOString(),data:data,source:'betcouncil_auto_harvest'}});
                    }}).catch(function(e){{console.log('[BetCouncil] DK props error:',e.message);}});
                }});
            }}

            // ── 8. Unabated sharp lines (every 30 min) ───────────────────
            throttled('unabated_' + sport, 1800000, function() {{
                fetch('https://unabated.com/api/lines?sport=' + sport.toLowerCase(), {{
                    headers:{{'Accept':'application/json','Referer':'https://unabated.com/'}}
                }}).then(function(r){{return r.json();}}).then(function(data){{
                    pushGist('betcouncil_unabated_' + sport + '.json', {{sport:sport,captured_at:new Date().toISOString(),data:data,source:'betcouncil_auto_harvest'}});
                }}).catch(function(e){{console.log('[BetCouncil] Unabated error:',e.message);}});
            }});

            // ── 9. OddsJam +EV (every 20 min) ────────────────────────────
            throttled('oddsjam_' + sport, 1200000, function() {{
                fetch('https://oddsjam.com/api/v2/positive-ev?sport=' + sport.toLowerCase() + '&sportsbook=pinnacle', {{
                    headers:{{'Accept':'application/json','Referer':'https://oddsjam.com/'}}
                }}).then(function(r){{return r.json();}}).then(function(data){{
                    pushGist('betcouncil_oddsjam_' + sport + '.json', {{sport:sport,captured_at:new Date().toISOString(),data:data,source:'betcouncil_auto_harvest'}});
                }}).catch(function(e){{console.log('[BetCouncil] OddsJam error:',e.message);}});
            }});

            // ── 10. PropSwap secondary market (every 30 min) ─────────────
            throttled('propswap_' + sport, 1800000, function() {{
                fetch('https://www.propswap.com/api/listings?sport=' + sport.toLowerCase() + '&status=active&limit=100', {{
                    headers:{{'Accept':'application/json','Referer':'https://www.propswap.com/'}}
                }}).then(function(r){{return r.json();}}).then(function(data){{
                    pushGist('betcouncil_propswap_' + sport + '.json', {{sport:sport,captured_at:new Date().toISOString(),data:data,source:'betcouncil_auto_harvest'}});
                }}).catch(function(e){{console.log('[BetCouncil] PropSwap error:',e.message);}});
            }});

            // ── EVSharps EV data harvester removed 2026-07-17: evsharps_ev_data
            //    session state was never read anywhere downstream, and the same
            //    Railway API (api-production-3a3b.up.railway.app/api/ev) already
            //    runs unauthenticated server-side via
            //    scripts/evsharps_dingers_harvester.py -- confirmed working from
            //    a GitHub Actions IP, no JWT/browser needed for MLB HR props.

            // ── 13. Underdog Fantasy props (every 20 min) ────────────────────
            var udSportMap = {{'MLB':'MLB','NBA':'NBA','NFL':'NFL','NHL':'NHL','WNBA':'WNBA'}};
            var udSport = udSportMap[sport];
            if (udSport) {{
                throttled('underdog_' + sport, 1200000, function() {{
                    fetch('https://api.underdogfantasy.com/beta/v5/over_under_lines?sport_id=' + udSport, {{
                        headers:{{'Accept':'application/json','Referer':'https://underdogfantasy.com/'}}
                    }}).then(function(r){{return r.json();}}).then(function(data){{
                        pushGist('betcouncil_underdog_' + sport + '.json', {{sport:sport,captured_at:new Date().toISOString(),data:data,source:'betcouncil_auto_harvest'}});
                        console.log('[BetCouncil] ✅ Underdog ' + sport + ' harvested');
                    }}).catch(function(e){{console.log('[BetCouncil] Underdog error:',e.message);}});
                }});
            }}

            // ── 14. Bovada game lines (every 20 min) ─────────────────────────
            // CORS STATUS: CORS-BLOCKED from browser (no Access-Control-Allow-Origin
            // header on bovada.lv responses). Gist will remain empty from this hook.
            // The data IS accessible server-side (Python fetcher uses Kambi API as
            // fallback). For browser harvest, add a Tampermonkey passive hook that
            // intercepts XHR/fetch calls WHILE BROWSING www.bovada.lv — same pattern
            // as the Caesars/FanDuel passive hooks already in this script.
            var bvSportMap = {{'MLB':'/baseball/mlb','NBA':'/basketball/nba',
                               'NFL':'/football/nfl','NHL':'/hockey/nhl',
                               'UFC':'/fighting/ufc','WNBA':'/basketball/wnba'}};
            var bvPath = bvSportMap[sport];
            if (bvPath) {{
                throttled('bovada_' + sport, 1200000, function() {{
                    fetch('https://www.bovada.lv/services/sports/event/v2/events/A/description' + bvPath + '?lang=en', {{
                        headers: {{
                            'Accept':  'application/json',
                            'Referer': 'https://www.bovada.lv/'
                        }}
                    }}).then(function(r) {{ return r.json(); }}).then(function(data) {{
                        pushGist('betcouncil_bovada_' + sport + '.json', {{
                            sport: sport, captured_at: new Date().toISOString(),
                            data: data, source: 'betcouncil_auto_harvest'
                        }});
                        console.log('[BetCouncil] ✅ Bovada ' + sport + ' harvested');
                    }}).catch(function(e) {{ console.log('[BetCouncil] Bovada (CORS expected):', e.message); }});
                }});
            }}

            // ── 15. Polymarket prediction markets (every 30 min) ─────────────
            throttled('polymarket_' + sport, 1800000, function() {{
                fetch('https://gamma-api.polymarket.com/markets?tag=' + sport.toLowerCase() + '&limit=50&active=true', {{
                    headers:{{'Accept':'application/json'}}
                }}).then(function(r){{return r.json();}}).then(function(data){{
                    pushGist('betcouncil_polymarket_' + sport + '.json', {{sport:sport,captured_at:new Date().toISOString(),data:data,source:'betcouncil_auto_harvest'}});
                }}).catch(function(e){{console.log('[BetCouncil] Polymarket error:',e.message);}});
            }});

            // ── 16. Novig props (every 20 min) ───────────────────────────────
            var nvSportMap = {{'MLB':'baseball','NBA':'basketball','NFL':'football','NHL':'hockey'}};
            var nvSport = nvSportMap[sport];
            if (nvSport) {{
                /* Novig: api.novig.com is DNS-dead (2025). Disabled browser fetch.
       Python fallback uses fetch_novig_lines → SBR consensus. */
    // throttled('novig_' + sport, 1200000, function() {{
    //                 fetch('https://api.novig.com/lines?sport=' + nvSport + '&market=player_props', {{
    //                     headers:{{'Accept':'application/json','Referer':'https://novig.com/'}}
    //                 }}).then(function(r){{return r.json();}}).then(function(data){{
    //                     pushGist('betcouncil_novig_' + sport + '.json', {{sport:sport,captured_at:new Date().toISOString(),data:data,source:'betcouncil_auto_harvest'}});
                    }}).catch(function(e){{console.log('[BetCouncil] Novig error:',e.message);}});
                }});
            }}

            // ── 17. MyBookie game lines (every 25 min) ───────────────────────
            // CORS STATUS: CORS-BLOCKED from browser (no Access-Control-Allow-Origin
            // header). MyBookie also has no public JSON API — their sportsbook is an
            // SPA; all data endpoints return HTML when called cross-origin. The
            // previous URL (/api/v1/sports/{{sport}}/lines) returned HTML, not JSON.
            // To harvest MyBookie data, add a Tampermonkey passive hook that fires
            // while browsing mybookie.ag and intercepts their internal XHR calls
            // (use DevTools → Network → XHR while on the sportsbook page to find
            // the actual API path their frontend calls).
            var mbSportMap = {{'MLB':'baseball','NBA':'basketball',
                               'NFL':'football','NHL':'hockey','UFC':'mma'}};
            var mbSport = mbSportMap[sport];
            if (mbSport) {{
                throttled('mybookie_' + sport, 1500000, function() {{
                    // Best-effort attempt — will CORS-fail from Streamlit domain.
                    // The actual internal API path must be discovered from DevTools.
                    fetch('https://mybookie.ag/sportsbook/api/events?sport=' + mbSport, {{
                        headers: {{
                            'Accept':  'application/json',
                            'Referer': 'https://mybookie.ag/'
                        }}
                    }}).then(function(r) {{ return r.json(); }}).then(function(data) {{
                        pushGist('betcouncil_mybookie_' + sport + '.json', {{
                            sport: sport, captured_at: new Date().toISOString(),
                            data: data, source: 'betcouncil_auto_harvest'
                        }});
                        console.log('[BetCouncil] ✅ MyBookie ' + sport + ' harvested');
                    }}).catch(function(e) {{ console.log('[BetCouncil] MyBookie (CORS/no-API expected):', e.message); }});
                }});
            }}

            // ── 18. ParlaySavant +EV props (every 20 min) ────────────────────
            // CORS STATUS: CORS-BLOCKED from browser (no Access-Control-Allow-Origin
            // header). ParlaySavant is a Next.js SPA — their internal API routes
            // (probed: /api/props, /api/ev-plays, /api/player-props, /api/ev,
            // /api/best-bets, /api/positive-ev, /api/trpc/props.getEV) all return
            // HTML when called cross-origin. No public JSON API is accessible.
            //
            // Preferred path: the Python server-side fetcher fetch_parlaysavant_ev()
            // already runs on every board load via the dispatch table and populates
            // 'parlaysavant_ev_h' in session_state. Use that instead.
            //
            // To harvest ParlaySavant from the browser, add a Tampermonkey passive
            // hook that fires while browsing parlaysavant.com and intercepts the
            // actual internal fetch calls (check DevTools → Network while on the
            // +EV tab to find the real API route their app calls).
            throttled('parlaysavant_' + sport, 1200000, function() {{
                // Best-effort attempt — will CORS-fail. Real route needs DevTools.
                fetch('https://parlaysavant.com/api/ev-plays?sport=' + sport.toLowerCase(), {{
                    headers: {{
                        'Accept':  'application/json',
                        'Referer': 'https://parlaysavant.com/'
                    }}
                }}).then(function(r) {{ return r.json(); }}).then(function(data) {{
                    pushGist('betcouncil_parlaysavant_' + sport + '.json', {{
                        sport: sport, captured_at: new Date().toISOString(),
                        data: data, source: 'betcouncil_auto_harvest'
                    }});
                    console.log('[BetCouncil] ✅ ParlaySavant ' + sport + ' harvested');
                }}).catch(function(e) {{ console.log('[BetCouncil] ParlaySavant (CORS expected; use Python fetcher):', e.message); }});
            }});

            // ── 19. Bet365 game lines (every 25 min) ─────────────────────────
            var b365Map={{'MLB':'baseball','NBA':'basketball','NFL':'american-football','NHL':'ice-hockey','UFC':'mma','SOCCER':'soccer'}};
            var b365Sport=b365Map[sport];
            if(b365Sport){{
                // NOTE: Bet365 blocks cross-origin requests (CORS) from the Streamlit
                // domain, so this fetch will fail with ERR_FAILED in browser DevTools.
                // The correct approach is a Tampermonkey passive hook that intercepts
                // XHR/fetch calls WHILE BROWSING bet365.com — similar to the Caesars
                // and FanDuel passive harvesters already in this script.
                //
                // The previous URL used cid=97&ctid=97 (hardcoded match-result market,
                // returns only Home/Away/Tie — no spread or total). The sport-specific
                // cid values for spreads/totals vary per sport and must be discovered
                // from DevTools while browsing Bet365.
                //
                // Attempting the sport-aware REST endpoint as a best-effort fallback
                // (may be CORS-blocked, but at least uses the correct sport path):
                var b365CidMap={{'MLB':14,  // baseball game lines
                                 'NBA':7,   // basketball game lines
                                 'NHL':17,  // hockey game lines
                                 'NFL':12,  // football game lines
                                 'SOCCER':1}};
                var b365Cid=b365CidMap[sport]||97;
                throttled('bet365_'+sport,1500000,function(){{
                    fetch('https://www.bet365.com/SportsBook.API/web?lid=1&zid=0&pd='+encodeURIComponent('W#SS'+b365Cid+';')+'&cid='+b365Cid+'&ctid='+b365Cid,{{
                        headers:{{'Accept':'application/json','Referer':'https://www.bet365.com/','Origin':'https://www.bet365.com'}}
                    }}).then(function(r){{if(!r.ok)throw new Error('b365 '+r.status);return r.json();}}).then(function(data){{
                        pushGist('betcouncil_bet365_'+sport+'.json',{{sport:sport,captured_at:new Date().toISOString(),data:data,source:'betcouncil_auto_harvest'}});
                    }}).catch(function(e){{console.log('[BetCouncil] Bet365 error (CORS expected):',e.message);}});
                }});
            }}

            // ── 20. Pregame.com sharp plays (every 30 min) ───────────────────
            throttled('pregame_'+sport,1800000,function(){{
                fetch('https://pregame.com/api/sharp-plays?sport='+sport.toLowerCase(),{{headers:{{'Accept':'application/json','Referer':'https://pregame.com/'}}}}).then(function(r){{return r.json();}}).then(function(data){{pushGist('betcouncil_pregame_'+sport+'.json',{{sport:sport,captured_at:new Date().toISOString(),data:data,source:'betcouncil_auto_harvest'}});}}).catch(function(e){{console.log('[BetCouncil] Pregame error:',e.message);}});
            }});

            // ── 22. FantasyLabs ownership projections (every 30 min) ──────────
            var flSportMap={{'MLB':'mlb','NBA':'nba','NFL':'nfl','NHL':'nhl'}};
            var flSport=flSportMap[sport];
            if(flSport){{
                throttled('fantasylabs_'+sport,1800000,function(){{
                    fetch('https://www.fantasylabs.com/api/player_models/1/'+flSport+'/?projectionsource=4',{{headers:{{'Accept':'application/json','Referer':'https://www.fantasylabs.com/'}}}}).then(function(r){{return r.json();}}).then(function(data){{pushGist('betcouncil_fantasylabs_'+sport+'.json',{{sport:sport,captured_at:new Date().toISOString(),data:data,source:'betcouncil_auto_harvest'}});}}).catch(function(e){{console.log('[BetCouncil] FantasyLabs error:',e.message);}});
                }});
            }}

            // ── 23. Rotowire injuries/lineups (every 15 min) ─────────────────
            var rwSportMap={{'MLB':'baseball','NBA':'basketball','NFL':'football','NHL':'hockey'}};
            var rwSport=rwSportMap[sport];
            if(rwSport){{
                throttled('rotowire_'+sport,900000,function(){{
                    fetch('https://www.rotowire.com/'+rwSport+'/tables/injury-report.php',{{headers:{{'Accept':'application/json','Referer':'https://www.rotowire.com/'}}}}).then(function(r){{return r.json();}}).then(function(data){{pushGist('betcouncil_rotowire_'+sport+'.json',{{sport:sport,captured_at:new Date().toISOString(),data:data,source:'betcouncil_auto_harvest'}});}}).catch(function(e){{console.log('[BetCouncil] Rotowire error:',e.message);}});
                }});
            }}

            // ── 24. Sleeper ADP/ownership data (every 30 min) ────────────────
            throttled('sleeper_'+sport,1800000,function(){{
                fetch('https://api.sleeper.app/v1/players/'+sport.toLowerCase(),{{headers:{{'Accept':'application/json'}}}}).then(function(r){{return r.json();}}).then(function(data){{pushGist('betcouncil_sleeper_'+sport+'.json',{{sport:sport,captured_at:new Date().toISOString(),data:data,source:'betcouncil_auto_harvest'}});}}).catch(function(e){{console.log('[BetCouncil] Sleeper error:',e.message);}});
            }});

            // ── 25. NumberFire projections (every 30 min) ────────────────────
            var nfSportMap={{'MLB':'mlb','NBA':'nba','NFL':'nfl','NHL':'nhl'}};
            var nfSport=nfSportMap[sport];
            if(nfSport){{
                throttled('numberfire_'+sport,1800000,function(){{
                    fetch('https://www.numberfire.com/api/v1/'+nfSport+'/projections',{{headers:{{'Accept':'application/json','Referer':'https://www.numberfire.com/'}}}}).then(function(r){{return r.json();}}).then(function(data){{pushGist('betcouncil_numberfire_'+sport+'.json',{{sport:sport,captured_at:new Date().toISOString(),data:data,source:'betcouncil_auto_harvest'}});}}).catch(function(e){{console.log('[BetCouncil] NumberFire error:',e.message);}});

            // ── 26. SportsInsights betting % + steam (every 15 min) ──────────────
            throttled('sportsinsights_'+sport,900000,function(){{
                fetch('https://www.sportsinsights.com/api/sportsbookodds/'+sport.toLowerCase()+'?sportsbooks=1,2,3,4,5,6,7,8',{{headers:{{'Accept':'application/json','Referer':'https://www.sportsinsights.com/'}}}}).then(function(r){{return r.json();}}).then(function(data){{pushGist('betcouncil_sportsinsights_'+sport+'.json',{{sport:sport,captured_at:new Date().toISOString(),data:data,source:'betcouncil_auto_harvest'}});}}).catch(function(e){{
                    // Try alternate endpoint
                    fetch('https://www.sportsinsights.com/betting-trends/?sport='+sport.toLowerCase(),{{headers:{{'Accept':'application/json','Referer':'https://www.sportsinsights.com/'}}}}).then(function(r2){{return r2.json();}}).then(function(d2){{pushGist('betcouncil_sportsinsights_'+sport+'.json',{{sport:sport,captured_at:new Date().toISOString(),data:d2,source:'betcouncil_auto_harvest_alt'}});}}).catch(function(e2){{console.log('[BetCouncil] SportsInsights error:',e2.message);}});
                }});
            }});

            // ── 27. OddsShark consensus + line history (every 20 min) ────────────
            var osMap={{'MLB':'baseball','NBA':'basketball','NFL':'football','NHL':'hockey'}};
            var osSport=osMap[sport];
            if(osSport){{
                throttled('oddsshark_'+sport,1200000,function(){{
                    fetch('https://www.oddsshark.com/api/scores/'+osSport+'/date/'+new Date().toISOString().split('T')[0].replace(/-/g,''),{{headers:{{'Accept':'application/json','Referer':'https://www.oddsshark.com/','X-Requested-With':'XMLHttpRequest'}}}}).then(function(r){{return r.json();}}).then(function(data){{pushGist('betcouncil_oddsshark_'+sport+'.json',{{sport:sport,captured_at:new Date().toISOString(),data:data,source:'betcouncil_auto_harvest'}});}}).catch(function(e){{console.log('[BetCouncil] OddsShark error:',e.message);}});
                }});
            }}

            // ── 28. VegasInsider opening vs current lines (every 20 min) ─────────
            var viMap={{'MLB':'baseball','NBA':'basketball','NFL':'football','NHL':'hockey','UFC':'mma'}};
            var viSport=viMap[sport];
            if(viSport){{
                throttled('vegasinsider_'+sport,1200000,function(){{
                    fetch('https://www.vegasinsider.com/api/odds/'+viSport+'/?ajax=1',{{headers:{{'Accept':'application/json','X-Requested-With':'XMLHttpRequest','Referer':'https://www.vegasinsider.com/'}}}}).then(function(r){{return r.json();}}).then(function(data){{pushGist('betcouncil_vegasinsider_'+sport+'.json',{{sport:sport,captured_at:new Date().toISOString(),data:data,source:'betcouncil_auto_harvest'}});}}).catch(function(e){{console.log('[BetCouncil] VegasInsider error:',e.message);}});
                }});
            }}

            // ── 29. Props.cash cross-book prop lines (every 20 min) ──────────────
            throttled('propscash_'+sport,1200000,function(){{
                fetch('https://props.cash/api/props?sport='+sport.toLowerCase()+'&limit=200',{{headers:{{'Accept':'application/json','Referer':'https://props.cash/'}}}}).then(function(r){{return r.json();}}).then(function(data){{pushGist('betcouncil_propscash_'+sport+'.json',{{sport:sport,captured_at:new Date().toISOString(),data:data,source:'betcouncil_auto_harvest'}});}}).catch(function(e){{console.log('[BetCouncil] Props.cash error:',e.message);}});
            }});

            // ── 30. BaseballPress MLB lineups (every 15 min, MLB only) ───────────
            // NOTE (2026-07): LineStar (GetFastUpdateV2/GetPropBets/GetSalariesV5)
            // used to run here as an in-browser Tampermonkey harvester. It's now
            // handled server-side by the "LineStar Data Refresh" GitHub Actions
            // workflow (.github/workflows/linestar_refresh.yml, hourly cron,
            // scripts/linestar_harvester.py) which pushes the same three Gist
            // files per sport with no browser/session dependency at all. Removed
            // the duplicate browser-side version rather than run both.

            // ── 39. Scores and Odds betting % (every 15 min) ─────────────────────
            var soMap={{'MLB':'baseball','NBA':'basketball','NFL':'football','NHL':'hockey'}};
            var soSport2=soMap[sport];
            if(soSport2){{
                throttled('scoresandodds_'+sport,900000,function(){{
                    fetch('https://www.scoresandodds.com/api/'+soSport2+'/betting-trends',{{headers:{{'Accept':'application/json','Referer':'https://www.scoresandodds.com/'}}}}).then(function(r){{return r.json();}}).then(function(data){{pushGist('betcouncil_scoresandodds_'+sport+'.json',{{sport:sport,captured_at:new Date().toISOString(),data:data,source:'betcouncil_auto_harvest'}});}}).catch(function(e){{console.log('[BetCouncil] ScoresAndOdds error:',e.message);}});
                }});
            }}

            // ── 40. Kalshi prediction markets (every 30 min) ─────────────────────
            throttled('kalshi_'+sport,1800000,function(){{
                fetch('https://trading-api.kalshi.com/trade-api/v2/events/?status=open&series_ticker='+sport,{{headers:{{'Accept':'application/json'}}}}).then(function(r){{return r.json();}}).then(function(data){{pushGist('betcouncil_kalshi2_'+sport+'.json',{{sport:sport,captured_at:new Date().toISOString(),data:data,source:'betcouncil_auto_harvest'}});}}).catch(function(e){{console.log('[BetCouncil] Kalshi error:',e.message);}});
            }});

                }});
            }}

            // ── New: Pickswise expert picks (every 30 min) ───────────────────
            throttled('pickswise_'+sport,1800000,function(){{
                fetch('https://www.pickswise.com/api/picks?sport='+sport.toLowerCase()+'&type=expert&limit=50',{{headers:{{'Accept':'application/json','Referer':'https://www.pickswise.com/'}}}}).then(function(r){{return r.json();}}).then(function(data){{pushGist('betcouncil_pickswise_'+sport+'.json',{{sport:sport,captured_at:new Date().toISOString(),data:data,source:'betcouncil_auto_harvest'}});}}).catch(function(e){{
                    // Try alternate Pickswise endpoint
                    fetch('https://www.pickswise.com/api/v2/predictions?sport='+sport.toLowerCase(),{{headers:{{'Accept':'application/json'}}}}).then(function(r2){{return r2.json();}}).then(function(d2){{pushGist('betcouncil_pickswise_'+sport+'.json',{{sport:sport,captured_at:new Date().toISOString(),data:d2,source:'betcouncil_auto_harvest'}});}}).catch(function(e2){{console.log('[BetCouncil] Pickswise error:',e2.message);}});
                }});
            }});

            // ── New: BetUS props (every 25 min) ──────────────────────────────
            var betUsSportMap={{'MLB':'baseball','NBA':'basketball','NFL':'football','NHL':'hockey','WNBA':'wnba'}};
            var betUsSport=betUsSportMap[sport];
            if(betUsSport){{
                throttled('betus_'+sport,1500000,function(){{
                    fetch('https://www.betus.com.pa/sportsbook/props-builder/api/'+betUsSport+'/player-props',{{headers:{{'Accept':'application/json','Referer':'https://www.betus.com.pa/'}}}}).then(function(r){{return r.json();}}).then(function(data){{pushGist('betcouncil_betus_'+sport+'.json',{{sport:sport,captured_at:new Date().toISOString(),data:data,source:'betcouncil_auto_harvest'}});}}).catch(function(e){{console.log('[BetCouncil] BetUS error:',e.message);}});
                }});
            }}

            // ── New: Bet105 game lines (every 25 min) ────────────────────────
            throttled('bet105_'+sport,1500000,function(){{
                fetch('https://app.bet105.ag/api/sports/lines?sport='+sport.toLowerCase(),{{headers:{{'Accept':'application/json','Referer':'https://app.bet105.ag/'}}}}).then(function(r){{return r.json();}}).then(function(data){{pushGist('betcouncil_bet105_'+sport+'.json',{{sport:sport,captured_at:new Date().toISOString(),data:data,source:'betcouncil_auto_harvest'}});}}).catch(function(e){{console.log('[BetCouncil] Bet105 error:',e.message);}});
            }});

            // ── New: BetWhale lines (every 25 min) ───────────────────────────
            throttled('betwhale_'+sport,1500000,function(){{
                fetch('https://betwhale.ag/api/sports/'+sport.toLowerCase()+'/lines',{{headers:{{'Accept':'application/json','Referer':'https://betwhale.ag/'}}}}).then(function(r){{return r.json();}}).then(function(data){{pushGist('betcouncil_betwhale_'+sport+'.json',{{sport:sport,captured_at:new Date().toISOString(),data:data,source:'betcouncil_auto_harvest'}});}}).catch(function(e){{console.log('[BetCouncil] BetWhale error:',e.message);}});
            }});

            // ── New: Ybets lines (every 25 min) ──────────────────────────────
            throttled('ybets_'+sport,1500000,function(){{
                fetch('https://ybets.net/api/sport/'+sport.toLowerCase()+'/lines',{{headers:{{'Accept':'application/json','Referer':'https://ybets.net/'}}}}).then(function(r){{return r.json();}}).then(function(data){{pushGist('betcouncil_ybets_'+sport+'.json',{{sport:sport,captured_at:new Date().toISOString(),data:data,source:'betcouncil_auto_harvest'}});}}).catch(function(e){{console.log('[BetCouncil] Ybets error:',e.message);}});
            }});

            // ── New: Zamba.co lines (every 25 min) ───────────────────────────
            throttled('zamba_'+sport,1500000,function(){{
                fetch('https://www.zamba.co/api/sports/'+sport.toLowerCase()+'/events',{{headers:{{'Accept':'application/json','Referer':'https://www.zamba.co/'}}}}).then(function(r){{return r.json();}}).then(function(data){{pushGist('betcouncil_zamba_'+sport+'.json',{{sport:sport,captured_at:new Date().toISOString(),data:data,source:'betcouncil_auto_harvest'}});}}).catch(function(e){{console.log('[BetCouncil] Zamba error:',e.message);}});
            }});


            // ── EVBets +EV feed (every 20 min) — free, 94 books, no login ──
            var evbSportMap={{'MLB':'baseball-mlb','NBA':'basketball-nba','NFL':'american-football-nfl','NHL':'hockey-nhl','UFC':'mma-mixed-martial-arts','SOCCER':'soccer-epl','WNBA':'basketball-wnba'}};
            var evbSport=evbSportMap[sport];
            if(evbSport){{
                throttled('evbets_'+sport,1200000,function(){{
                    // Value bets feed
                    fetch('https://evbets.app/value-bets/'+evbSport,{{headers:{{'Accept':'application/json','Referer':'https://evbets.app/'}}}}).then(function(r){{return r.json();}}).then(function(data){{
                        pushGist('betcouncil_evbets_'+sport+'.json',{{sport:sport,captured_at:new Date().toISOString(),data:data,source:'betcouncil_auto_harvest'}});
                        console.log('[BetCouncil] ✅ EVBets +EV feed harvested for '+sport);
                    }}).catch(function(e){{
                        // Fallback: try the API endpoint directly
                        fetch('https://evbets.app/api/value-bets?sport='+evbSport+'&min_ev=2&limit=100',{{headers:{{'Accept':'application/json'}}}}).then(function(r2){{return r2.json();}}).then(function(d2){{
                            pushGist('betcouncil_evbets_'+sport+'.json',{{sport:sport,captured_at:new Date().toISOString(),data:d2,source:'betcouncil_auto_harvest_api'}});
                        }}).catch(function(e2){{console.log('[BetCouncil] EVBets error:',e2.message);}});
                    }});
                }});
            }}

            // ── EVBets prop bets feed (every 20 min) ─────────────────────────
            if(evbSport){{
                throttled('evbets_props_'+sport,1200000,function(){{
                    fetch('https://evbets.app/prop-bets/'+evbSport,{{headers:{{'Accept':'application/json','Referer':'https://evbets.app/prop-bets/'}}}}).then(function(r){{return r.json();}}).then(function(data){{
                        pushGist('betcouncil_evbets_props_'+sport+'.json',{{sport:sport,captured_at:new Date().toISOString(),data:data,source:'betcouncil_auto_harvest'}});
                    }}).catch(function(e){{console.log('[BetCouncil] EVBets props error:',e.message);}});
                }});
            }}
        }})();
        </script>
        """
        st.components.v1.html(_harvester_js, height=0, scrolling=False)

        # ── Season Regime ────────────────────────────────────────
        st.markdown("---")
    if _view in ("Seasonal", "All"):
        st.markdown("### 📅 Season Regime — All Sports")
        st.caption("Live season phase detection for all sports. Off-season suppresses stale signals automatically.")
        _all_sports_regime = ["NBA","MLB","NFL","NHL","WNBA","GOLF","TENNIS","SOCCER","UFC"]
        _regime_color_map = {
            "Off-season":"#e04040","Preseason":"#f59e0b","Early Season":"#f59e0b",
            "Mid Season":"#22c55e","Late Season":"#0ea5a0","Playoffs":"#a855f7",
        }
        _rcols = st.columns(3)
        for _rsi, _rsp in enumerate(_all_sports_regime):
            _regime = detect_season_regime(_rsp)
            _rphase = _regime["regime"]
            _rcolor = _regime_color_map.get(_rphase, "#6a7a8a")
            _radj   = _regime.get("adjustments", {})
            _radj_str = ", ".join(f"{k}:{v:+.2f}" for k,v in _radj.items()) if _radj else "none"
            _rdesc = _regime["description"][:55] + "..." if len(_regime["description"]) > 55 else _regime["description"]
            _rcols[_rsi % 3].markdown(
                f'<div style="background:var(--bc-bg);border:1px solid {_rcolor}55;border-radius:8px;padding:10px;margin-bottom:8px;">'
                f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                f'<span style="color:var(--bc-text);font-weight:700;font-size:13px;">{_rsp}</span>'
                f'<span style="color:{_rcolor};font-size:11px;font-weight:600;background:{_rcolor}22;padding:2px 8px;border-radius:10px;">{_rphase}</span></div>'
                f'<div style="color:var(--bc-dim);font-size:11px;margin-top:4px;">{_rdesc}</div>'
                f'<div style="color:#e8a020;font-size:10px;margin-top:3px;">adj: {_radj_str}</div>'
                f'</div>',
                unsafe_allow_html=True
            )

        # ── Daily Bet Sizing Optimizer ─────────────────────────────────
        st.markdown("---")
    if _view in ("Daily", "All"):
        st.markdown("### 💰 Daily Bet Sizing Optimizer")
        st.caption("Optimal wager sizes for today's picks — accounts for tier Kelly, correlation, and daily risk cap.")
        _board_for_sizing = [p for p in st.session_state.get("board_data",[])
                             if p.get("Tier") in ("SOVEREIGN","ELITE","APPROVED","LEAN")
                             and p.get("Edge",0) > 0]
        if _board_for_sizing:
            _bankroll_sz = st.session_state.get("bankroll", 100.0)
            _max_risk_pct = st.slider("Max daily risk %", 5, 25, 15, key="max_risk_slider") / 100
            _sized = optimize_daily_bet_sizing(
                picks=_board_for_sizing[:20],
                bankroll=_bankroll_sz,
                max_daily_risk_pct=_max_risk_pct,
            )
            _sz_c1,_sz_c2,_sz_c3,_sz_c4 = st.columns(4)
            _sz_c1.metric("Total Risk", f"${_sized['total_risk']:.2f}", f"{_sized['total_risk_pct']:.1%} of bankroll")
            _sz_c2.metric("Corr Adj", f"{_sized['correlation_adj']:.0%}", help="Reduction from correlated picks")
            _sz_c3.metric("Scale Applied", f"{_sized['scale_applied']:.0%}", help="Cap enforcement scaling")
            _sz_c4.metric("Max Daily", f"${_sized['max_daily_risk']:.2f}")
            if _sized.get("warning"):
                st.warning(_sized["warning"])
            st.markdown("**Recommended allocation per tier (per bet):**")
            _ra = _sized.get("recommended_allocation",{})
            _ra_cols = st.columns(4)
            for ci,(_tier,_amt) in enumerate([("SOVEREIGN",_ra.get("SOVEREIGN",0)),
                                               ("ELITE",_ra.get("ELITE",0)),
                                               ("APPROVED",_ra.get("APPROVED",0)),
                                               ("LEAN",_ra.get("LEAN",0))]):
                _tc = TIER_COLORS[_tier]
                _ra_cols[ci].markdown(
                    f'<div style="background:var(--bc-bg-card);border:1px solid {_tc}44;border-radius:8px;padding:10px;text-align:center">'
                    f'<div style="color:{_tc};font-size:11px;font-weight:700">{_tier}</div>'
                    f'<div style="color:var(--bc-text);font-size:18px;font-weight:700">${_amt:.2f}</div>'
                    f'</div>', unsafe_allow_html=True)
            # Show sized picks
            _sized_df = [{"Player":p.get("Player",""),"Prop":p.get("Prop",""),"Tier":p.get("Tier",""),
                           "Edge":f"{p.get('Edge',0):.1%}","Wager":f"${p.get('adj_wager',0):.2f}"}
                         for p in _sized.get("picks_sized",[]) if p.get("adj_wager",0) > 0]
            if _sized_df:
                st.markdown(_bc_df_html(_sized_df), unsafe_allow_html=True)
        else:
            st.info("Load a board to see sizing recommendations.")

        # ── Projection Confidence Overview ──────────────────────
        st.markdown("---")
    if _view in ("Weekly", "All"):
        st.markdown("### 🎯 Projection Confidence & Market Intelligence")
        st.caption("Confidence score (0-100) based on sample size, injury certainty, lineup confirmation, market agreement, and volatility.")
        _board_conf = st.session_state.get("board_data", [])
        if _board_conf:
            _high_conf  = [p for p in _board_conf if p.get("ProjConfidence",0) >= 80]
            _med_conf   = [p for p in _board_conf if 60 <= p.get("ProjConfidence",0) < 80]
            _low_conf   = [p for p in _board_conf if p.get("ProjConfidence",0) < 60]
            _role_changes = [p for p in _board_conf if p.get("RoleChange")]
            _cc1, _cc2, _cc3, _cc4 = st.columns(4)
            _cc1.metric("🟢 High Conf", len(_high_conf), help="Score ≥80 — trust projection")
            _cc2.metric("🟡 Moderate", len(_med_conf), help="Score 60-79")
            _cc3.metric("🔴 Low Conf", len(_low_conf), help="Score <60 — use with caution")
            _cc4.metric("🔄 Role Changes", len(_role_changes), help="Players with detected role change")
            if _role_changes:
                st.markdown("**Role Change Alerts:**")
                for _rc_prop in _role_changes[:5]:
                    _rcd = _rc_prop.get("RoleChange",{})
                    _rcc = "#22c55e" if _rcd.get("direction")=="UP" else "#e04040"
                    st.markdown(
                        f'<div style="background:var(--bc-bg-card);border-left:3px solid {_rcc};'
                        f'border-radius:4px;padding:4px 8px;margin-bottom:3px;">'
                        f'<span style="color:{_rcc};">{_rcd.get("note","")}</span></div>',
                        unsafe_allow_html=True
                    )
            # Market vs model divergence for top props
            _model_bullish = [p for p in _board_conf
                              if p.get("MarketVsModel",{}) and
                              p.get("MarketVsModel",{}).get("signal") == "MODEL_BULLISH"
                              and p.get("Tier") in ("SOVEREIGN","ELITE")]
            if _model_bullish:
                st.markdown("**Model > Market (potential value):**")
                for _mb in _model_bullish[:3]:
                    _mvm = _mb.get("MarketVsModel",{})
                    st.caption(f"  {_mb.get('Player','')} {_mb.get('Prop','')}: {_mvm.get('note','')}")

        # ── Signal ROI Audit ─────────────────────────────────────
        st.markdown("---")
    if _view in ("Weekly", "All"):
        st.markdown("### 📊 Per-Signal ROI Audit")
        st.caption("Which signals actually predict wins? Updates as resolved bets accumulate.")
        _sig_audit = compute_signal_roi_audit(st.session_state.get("history", []))
        _resolved_count = len([h for h in st.session_state.get("history", []) if h.get("outcome") in ("WIN","LOSS")])
        if _sig_audit:
            _audit_rows = []
            for _sn, _sd in _sig_audit.items():
                _audit_rows.append({
                    "Signal":   _sn,
                    "Sample":   _sd["sample"],
                    "Win Rate": f"{_sd['win_rate']:.0%}",
                    "ROI":      _sd["roi_pct"],
                    "Verdict":  _sd["verdict"],
                })
    # DUPLICATE REMOVED: import pandas as _pd
            _audit_df = _pd.DataFrame(_audit_rows)
            st.markdown(_bc_df_html(_audit_df), unsafe_allow_html=True)
        elif _resolved_count < 20:
            st.info(f"Signal ROI audit activates at 20 resolved bets. ({_resolved_count}/20)")
        if _resolved_count >= 100:
            _bq_weights, _learned = get_bq_weights(st.session_state.get("history", []))
            if _learned:
                st.success("✅ BQ weights are now learned from your results (500+ bets)")
            elif _resolved_count >= 200:
                st.info(f"BQ weight learning activates at 500 bets. ({_resolved_count}/500) — current weights: Edge 40%, Alignment 20%, Agreement 20%, Volatility 10%, CLV 10%")
        else:
            st.info("No signals with 5+ samples yet.")

        # ── Signal Attribution ──────────────────────────────────
        st.markdown("---")
    if _view in ("Weekly", "All"):
        st.markdown("### 🔬 Signal Attribution Engine")
        st.caption("Which signals actually created profit? Activates at 20 resolved bets.")
        _attr_rows, _attr_n = compute_signal_attribution(st.session_state.get("history", []))
        if _attr_rows is None:
            st.info(f"Signal attribution activates at 20 resolved bets. Current: {_attr_n}.")
        else:
            _drag = [r for r in _attr_rows if "Drag" in r["Grade"]]
            if _drag:
                st.warning(f"⚠️ Signals with negative ROI: {', '.join(r['Signal'] for r in _drag)} — consider reducing weight")
            st.markdown(_bc_df_html(pd.DataFrame(_attr_rows)), unsafe_allow_html=True)
            st.caption("Net Units = total P&L generated when this signal was active. Grade = signal contribution quality.")

        # ── Portfolio Exposure ───────────────────────────────────
        st.markdown("---")
    if _view in ("Daily", "All"):
        st.markdown("### 🎯 Portfolio Exposure")
        st.caption("Am I over-concentrated? Checks sport, team, and player exposure across today's locked picks.")
        _portfolio = compute_portfolio_exposure(st.session_state.get("board_data", []))
        if _portfolio:
            # Prop correlation score
            _active_for_corr = [p for p in (st.session_state.get("board_data", []) or [])
                                if p.get("Tier") in ("SOVEREIGN","ELITE","APPROVED")][:8]
            _corr_score, _corr_groups = compute_prop_correlation_score(_active_for_corr)
            _corr_color = "#22c55e" if _corr_score < 0.25 else "#e8a020" if _corr_score < 0.50 else "#e04040"
            _p1, _p2, _p3, _p4 = st.columns(4)
            _p1.metric("Active Bets", _portfolio["n_active"])
            _p2.metric("Total Stake", f"${_portfolio['total_stake']:.2f}")
            _p3.metric("% of Bankroll", f"{_portfolio['total_pct_br']:.1f}%")
            _p4.metric("Correlation Score", f"{_corr_score:.2f}",
                       delta="High — review" if _corr_score > 0.50 else "Low — diversified",
                       delta_color="inverse" if _corr_score > 0.50 else "off")
            if _corr_score > 0.50 and _corr_groups:
                st.warning(f"⚠️ High portfolio correlation ({_corr_score:.2f}) — bets may rise and fall together:")
                st.markdown(_bc_df_html(pd.DataFrame(_corr_groups)), unsafe_allow_html=True)
            # Cross-team same-game correlations (e.g. QB TDs ↔ opposing WR receiving)
            try:
                from prop_market_intelligence import find_cross_team_correlations as _fctc
                _cross = _fctc(_active_for_corr)
                if _cross:
                    st.caption("🔗 **Cross-team correlations** (same game, opposing teams):")
                    st.markdown(_bc_df_html(pd.DataFrame(_cross)), unsafe_allow_html=True)
            except Exception:
                pass
            if _portfolio["warnings"]:
                for w in _portfolio["warnings"]:
                    st.warning(w)
            if _portfolio["recommendations"]:
                for rec in _portfolio["recommendations"]:
                    st.info(f"💡 {rec}")
            if _portfolio["sport_breakdown"]:
                _sport_rows = [{"Sport": k, "Count": v.get("count",0), "Exposure %": f"{v.get('pct',0):.1f}%"}
                               for k,v in sorted(_portfolio["sport_breakdown"].items(),
                               key=lambda x: -x[1].get("count",0) if isinstance(x[1],dict) else -float(x[1] or 0))]
                st.markdown(_bc_df_html(pd.DataFrame(_sport_rows)), unsafe_allow_html=True)
        else:
            st.markdown(empty_state_html("📊", "No portfolio exposure yet",
                         "Load the board and lock a few picks to see how your risk is spread across sports and games."),
                         unsafe_allow_html=True)

        # ── Model Drift Detection ────────────────────────────────
        st.markdown("---")
    if _view in ("Daily", "All"):
        st.markdown("### 📡 Model Drift Detection")
        st.caption("Compares recent 50-bet ROI vs all-time. Fires alert if model performance diverges.")
        _drift = compute_model_drift(st.session_state.get("history", []))
        if _drift is None:
            _total_res = len([h for h in st.session_state.get("history", []) if h.get("outcome") in ("WIN","LOSS")])
            st.info(f"Model drift detection activates at 60+ resolved bets. Current: {_total_res}.")
        else:
            _dc = "#22c55e" if not _drift["alert"] else "#e04040"
            st.markdown(
                f'<div style="background:var(--bc-bg);border:1px solid {"#e04040" if _drift["alert"] else "var(--bc-bg2)"};border-radius:8px;padding:0.8rem;">'
                f'<div style="color:{_dc};font-size:1.1rem;font-weight:700;">{_drift["status"]}</div>'
                f'<div style="display:flex;gap:2rem;margin-top:0.5rem;">'
                f'<span style="color:var(--bc-muted);">All-time ROI/bet: <b>{_drift["all_time_roi"]:+.3f}u</b></span>'
                f'<span style="color:var(--bc-muted);">Recent L{_drift["window"]} ROI/bet: <b style="color:{_dc};">{_drift["recent_roi"]:+.3f}u</b></span>'
                f'<span style="color:var(--bc-muted);">Drift: <b style="color:{_dc};">{_drift["drift"]:+.3f}u</b></span>'
                f'</div></div>',
                unsafe_allow_html=True
            )

        # ── Weekly Model Report ──────────────────────────────────
        st.markdown("---")
    if _view in ("Weekly", "All"):
        st.markdown("### 📋 Weekly Model Report")
        st.caption("Auto-generated weekly performance summary. No manual analysis needed.")
        _perf_data_wr = load_json_data(SIGNAL_PERFORMANCE_PATH, [], mem_ttl=60)
        _weekly = generate_weekly_model_report(st.session_state.get("history", []), _perf_data_wr)
        if _weekly:
            _wr1, _wr2 = st.columns(2)
            with _wr1:
                st.html(f"""
    | Metric | Value |
    |--------|-------|
    | Period | {_weekly['period']} |
    | Bets | {_weekly['bets']} ({_weekly['wins']} W) |
    | Win Rate | {_weekly['win_rate']} |
    | Net Units | {_weekly['net_units']} |
    | ROI/bet | {_weekly['roi_per_bet']} |
    """)
            with _wr2:
                st.html(f"""
    | Metric | Value |
    |--------|-------|
    | Best Sport | {_weekly['best_sport']} |
    | Worst Sport | {_weekly['worst_sport']} |
    | Best Signal | {_weekly['best_signal']} |
    | Worst Signal | {_weekly['worst_signal']} |
    | Avg CLV | {_weekly['avg_clv']} |
    """)
            st.caption(f"Calibration: {_weekly['calibration']}")
        else:
            st.info("No resolved bets in the last 7 days. Weekly report will generate automatically.")

        # ── Post-Mortem Reports ──────────────────────────────────
        st.markdown("---")
    if _view in ("Daily", "All"):
        st.markdown("### 🔍 Daily Post-Mortem")
        st.caption("Why did we win or lose? Breaks down signal performance by day.")
        _pm_col1, _pm_col2 = st.columns([2,1])
        with _pm_col1:
            _pm_date = st.date_input("Analyze date",
                                      value=date.today() - __import__("datetime").timedelta(days=1),
                                      key="pm_date")
        _pm = generate_post_mortem(st.session_state.get("history", []), _pm_date.strftime("%Y-%m-%d"))
        if _pm:
            _pm_color = "#22c55e" if _pm["net"] > 0 else "#e04040" if _pm["net"] < 0 else "#8a9ab0"
            st.markdown(
                f'<div style="background:var(--bc-bg);border:1px solid {_pm_color}44;border-radius:8px;padding:0.8rem;">'
                f'<div style="color:{_pm_color};font-size:1.1rem;font-weight:700;">{_pm["verdict"]}</div>'
                f'<div style="color:var(--bc-muted);font-size:0.9rem;margin-top:4px;">Primary cause: {_pm["cause"]}</div>'
                f'</div>',
                unsafe_allow_html=True
            )
            _pm_c1, _pm_c2 = st.columns(2)
            with _pm_c1:
                if _pm["failing"]:
                    st.markdown("**⚠️ Failing Signals:**")
                    for sig, net, w, l in _pm["failing"]:
                        st.markdown(f"- {sig}: {net:+.1f}u ({w}W/{l}L)")
                if _pm["watch_next"]:
                    st.caption(f"Watch next session: {', '.join(_pm['watch_next'])}")
                if _pm["bet_type_breakdown"]:
                    st.markdown("**Props vs. Game Lines:**")
                    for bt, btd in _pm["bet_type_breakdown"].items():
                        _u = f" · {btd['untracked']} untracked" if btd["untracked"] else ""
                        st.caption(f"{bt}: {btd['net']:+.1f}u ({btd['wr']} WR){_u}")
            with _pm_c2:
                if _pm["succeeding"]:
                    st.markdown("**✅ Succeeding Signals:**")
                    for sig, net, w, l in _pm["succeeding"]:
                        st.markdown(f"- {sig}: {net:+.1f}u ({w}W/{l}L)")
                if _pm["tier_breakdown"]:
                    st.markdown("**Tier breakdown:**")
                    for t, td in _pm["tier_breakdown"].items():
                        _u = f" · {td['untracked']} untracked" if td["untracked"] else ""
                        st.caption(f"{t}: {td['net']:+.1f}u ({td['wr']} WR){_u}")
            if _pm["n_untracked"]:
                st.warning(f"⚠️ {_pm['n_untracked']} of {_pm['n']} picks this day had no wager entered — "
                           "they graded WIN/LOSS correctly but contributed $0.0u, which understates real net "
                           "for whichever tier/bet_type they fall in. Log a stake on auto-resolved locks to fix this.")
            if _pm["top_losses"]:
                st.markdown("**Biggest losses today:**")
                for tl in _pm["top_losses"]:
                    _prob_str = f" · modeled {tl['prob']}% win prob" if "prob" in tl else ""
                    if "clv_pct" in tl:
                        _clv_str = f" · {tl['clv_tag']} ({tl['clv_pct']:+.1f}% vs close)"
                    elif "clv_points" in tl:
                        _clv_str = f" · {tl['clv_tag']} ({tl['clv_points']:+.1f}pts vs close)"
                    else:
                        _clv_str = ""
                    st.caption(f"{tl['label']} ({tl['sport']}, {tl['bet_type']}, {tl['tier']}): {tl['net']:+.1f}u{_prob_str}{_clv_str}")
            if _pm["n_clv_resolved"]:
                st.caption(f"Avg prop CLV today: {_pm['avg_clv']:+.2f}% ({_pm['n_clv_resolved']} of {_pm['n']} picks with a resolved closing line)")
            if _pm["n_clv_resolved_game"]:
                st.caption(f"Avg game-line CLV today: {_pm['avg_clv_points']:+.2f}pts ({_pm['n_clv_resolved_game']} of {_pm['n']} picks with a resolved closing line)")
        else:
            st.info(f"No resolved bets found for {_pm_date.strftime('%B %d, %Y')}.")

        # ── Signal Interaction Analysis ──────────────────────────
        st.markdown("---")
    if _view in ("Weekly", "All"):
        st.markdown("### 🔗 Signal Interaction Analysis")
        st.caption("Which signal combinations are stronger than either signal alone? Activates at 50 resolved bets.")
        _perf_data_int = load_json_data(SIGNAL_PERFORMANCE_PATH, [], mem_ttl=60)
        _int_rows, _int_n = compute_signal_interactions(_perf_data_int)
        if _int_rows is None:
            st.info(f"Signal interaction analysis activates at 50 resolved bets. Current: {_int_n}.")
        else:
            _synergistic = [r for r in _int_rows if "Synergistic" in r["Interaction"]]
            _conflicting = [r for r in _int_rows if "Conflicting" in r["Interaction"]]
            if _synergistic:
                st.success(f"✅ {len(_synergistic)} synergistic pair(s): " +
                           ", ".join(f"{r['Signal A']}+{r['Signal B']} ({r['Synergy']})" for r in _synergistic[:2]))
            if _conflicting:
                st.warning(f"⚠️ {len(_conflicting)} conflicting pair(s): " +
                           ", ".join(f"{r['Signal A']}+{r['Signal B']} ({r['Synergy']})" for r in _conflicting[:2]))
            st.markdown(_bc_df_html(pd.DataFrame(_int_rows)), unsafe_allow_html=True)
            st.caption("Synergy = WR(both active) minus WR(best signal alone). Positive = combination is stronger.")

        # ── Weight Recommendations ───────────────────────────────
        st.markdown("---")
    if _view in ("Weekly", "All"):
        st.markdown("### ⚖️ Weight Adjustment Recommendations")
        st.caption("Auto-applies once a signal clears a 95% confidence interval that excludes coin-flip (30+ bets/signal, 100+ bets/sport). Adjustments are capped at ±30% of the hand-tuned base weight. Every change is logged below.")
        _sport_wr = st.session_state.get("last_sport", "NBA")
        _cur_weights = get_effective_signal_weights(_sport_wr)
        _recs, _recs_n = generate_weight_recommendations(
            st.session_state.get("history", []), _sport_wr, current_weights=_cur_weights
        )
        if _recs is None:
            st.info(f"Weight recommendations activate after 100 {_sport_wr} bets. Current: {_recs_n}.")
        else:
            _wt_overrides = load_json_data(WEIGHT_OVERRIDES_PATH, {}, mem_ttl=60)
            _wt_log = load_json_data(WEIGHT_ADJUSTMENT_LOG_PATH, [], mem_ttl=60)
            if not isinstance(_wt_overrides, dict): _wt_overrides = {}
            if not isinstance(_wt_log, list): _wt_log = []
            _sport_ovr = dict(_wt_overrides.get(_sport_wr, {}))
            _newly_applied = []
            for rec in _recs:
                _wkey = rec["Signal"].lower()[:6]
                _already = _sport_ovr.get(_wkey)
                if _already is None or abs(float(_already) - rec["Suggested W"]) > 1e-6:
                    _sport_ovr[_wkey] = rec["Suggested W"]
                    _newly_applied.append(rec)
            if _newly_applied:
                _wt_overrides[_sport_wr] = _sport_ovr
                save_json_data(WEIGHT_OVERRIDES_PATH, _wt_overrides)
                save_to_gist("weight_overrides", _wt_overrides)
                for rec in _newly_applied:
                    _wt_log.append({
                        "timestamp": datetime.now().isoformat(timespec="seconds"),
                        "sport": _sport_wr, "signal": rec["Signal"], "action": rec["Action"],
                        "from": rec["Current W"], "to": rec["Suggested W"],
                        "n": rec["N"], "win_rate": rec["Win Rate"],
                        "ci_low": rec["CI Low"], "ci_high": rec["CI High"],
                    })
                save_json_data(WEIGHT_ADJUSTMENT_LOG_PATH, _wt_log)
                save_to_gist("weight_adjustment_log", _wt_log)
                st.success(f"✅ Auto-applied {len(_newly_applied)} weight adjustment(s) for {_sport_wr} — statistically significant at 95% confidence.")
                for rec in _newly_applied:
                    st.caption(f"**{rec['Signal']}**: {rec['Current W']:.3f} → {rec['Suggested W']:.3f} ({rec['Action']}) — {rec['Reason']}")
            elif _recs:
                st.caption(f"{len(_recs)} signal(s) currently qualify and are already applied — no change since last check.")
            else:
                st.success("✅ No signals have cleared the 95% significance bar yet for this sport. Weights unchanged.")
            _sport_log = [l for l in _wt_log if l.get("sport") == _sport_wr]
            if _sport_log:
                with st.expander(f"📜 Auto-adjustment log — {_sport_wr} ({len(_sport_log)} change(s))"):
                    for l in reversed(_sport_log[-20:]):
                        st.caption(f"{l.get('timestamp','')[:16]} · {l.get('signal','')} {l.get('action','')} {l.get('from',0):.3f}→{l.get('to',0):.3f} (n={l.get('n','?')}, WR={l.get('win_rate',0):.0%})")

        st.markdown("---")
        # ── Closing Line Beat Rate ──────────────────────────────
        st.markdown("---")
    if _view in ("Daily", "All"):
        st.markdown("### 📐 Closing Line Beat Rate")
        st.caption("Does the model project correctly vs where the closing line ends up? Higher = genuine market edge.")
        _clb_rate, _clb_total = get_closing_line_hit_rate(st.session_state.get("history", []))
        if _clb_rate is not None:
            _clb1, _clb2, _clb3 = st.columns(3)
            _clb1.metric("Beat Closing Line", f"{_clb_rate:.1%}")
            _clb2.metric("Sample Size", _clb_total)
            _clb3.metric("Status", "✅ Edge" if _clb_rate >= 0.55 else "⚠️ Watch" if _clb_rate >= 0.50 else "❌ Review")
            if _clb_rate >= 0.55:
                st.success(f"Model beats closing line {_clb_rate:.1%} — genuine edge confirmed.")
            elif _clb_rate < 0.50:
                st.warning(f"Model below 50% closing line beat rate — review signal weights.")
        else:
            st.info(f"Activates after 10 resolved bets with CLV data. ({_clb_total} tracked so far)")


            st.markdown("---")
    if _view in ("Seasonal", "All"):
            st.markdown("### 🎯 Calibration Dashboard — Predicted vs Actual Hit Rate")
            st.caption(
                "If your model is well-calibrated, the bars should match the diagonal. "
                "Bars above diagonal = underconfident (model is too conservative). "
                "Bars below = overconfident (model claims more edge than it has)."
            )

            # ── Build calibration data from history ──────────────────────────────
            _hist_all = st.session_state.get("history", [])
            _resolved  = [r for r in _hist_all if r.get("outcome") in ("WIN","LOSS")]
            # Calibration specifically requires a REAL predicted probability to
            # mean anything -- comparing "predicted vs actual" is meaningless if
            # the predicted number was a placeholder. Manual entries used to
            # fabricate prob from the known outcome (0.60 if WIN else 0.45) when
            # none was supplied -- those are excluded from calibration math only
            # (has_real_prob is explicitly False). Non-manual entries and manual
            # entries with a real supplied prob are trusted normally. Excluded
            # bets still count fully toward hit rate, P&L, and every other
            # metric that doesn't require a real prediction.
            # BUG FIX (2026-07): `.get("has_real_prob", True) is not False` meant
            # any record MISSING the key entirely (129 of 280 in the real
            # ledger) defaulted to included, same fake-probability contamination
            # problem as compute_calibration_buckets() had. Only 11 of 280 have
            # has_real_prob explicitly True -- require that explicitly.
            _cal_resolved = [r for r in _resolved if r.get("has_real_prob") is True]

            if len(_cal_resolved) >= 30:
                # ── Tier calibration ─────────────────────────────────────────────
                _tier_cal = {}
                for _r in _cal_resolved:
                    _t = _r.get("tier","")
                    if _t not in ("SOVEREIGN","ELITE","APPROVED","LEAN"): continue
                    _tier_cal.setdefault(_t, {"wins":0,"total":0,"prob_sum":0.0})
                    _tier_cal[_t]["total"] += 1
                    _tier_cal[_t]["wins"]  += int(_r.get("outcome") == "WIN")
                    _tier_cal[_t]["prob_sum"] += float(_r.get("prob",0.5) or 0.5)

                _tier_order = ["SOVEREIGN","ELITE","APPROVED","LEAN"]
                _tier_colors = TIER_COLORS

                if _tier_cal:
                    _cal_cols = st.columns(len(_tier_cal))
                    _col_idx  = 0
                    for _tier in _tier_order:
                        if _tier not in _tier_cal: continue
                        _tc   = _tier_cal[_tier]
                        _n    = _tc["total"]
                        _hr   = _tc["wins"] / _n if _n else 0
                        _pp   = _tc["prob_sum"] / _n if _n else 0.5
                        _err  = _pp - _hr  # positive = overconfident
                        _color = _tier_colors.get(_tier, "#6a7a8a")
                        _err_color = "#22c55e" if abs(_err) < 0.03 else ("#ffd700" if abs(_err) < 0.07 else "#e04040")
                        _status = "✅ Calibrated" if abs(_err) < 0.03 else ("⚠️ Overconfident" if _err > 0 else "⚡ Underconfident")
                        _cal_cols[_col_idx].markdown(
                            f'<div style="background:var(--bc-bg-card);border:1px solid {_color}40;border-radius:10px;padding:12px;text-align:center">'
                            f'<div style="font-size:10px;color:{_color};font-weight:700;text-transform:uppercase;letter-spacing:1px">{_tier}</div>'
                            f'<div style="font-size:11px;color:var(--bc-dim);margin:4px 0">n={_n} bets</div>'
                            f'<div style="display:flex;justify-content:space-between;margin:6px 0">'
                            f'<span style="font-size:11px;color:#8899aa">Predicted</span>'
                            f'<span style="font-size:14px;font-weight:700;color:#e8f0f8">{_pp:.1%}</span></div>'
                            f'<div style="display:flex;justify-content:space-between;margin:6px 0">'
                            f'<span style="font-size:11px;color:#8899aa">Actual</span>'
                            f'<span style="font-size:14px;font-weight:700;color:{_color}">{_hr:.1%}</span></div>'
                            f'<div style="background:#1a2a3a;border-radius:4px;height:6px;margin:8px 0">'
                            f'<div style="background:{_color};border-radius:4px;height:6px;width:{min(100,_hr*100):.0f}%"></div></div>'
                            f'<div style="font-size:11px;color:{_err_color};font-weight:600">{_status}</div>'
                            f'<div style="font-size:10px;color:{_err_color}">Error: {_err:+.1%}</div>'
                            f'</div>',
                            unsafe_allow_html=True
                        )
                        _col_idx += 1

                    st.markdown("")

                # ── Probability bucket calibration (reliability diagram) ──────────
                st.markdown("#### 📈 Reliability Diagram — by Probability Bucket")
                st.caption("Each bucket shows: how often the model predicted that probability range vs how often it actually hit.")

                _buckets = {}
                _bucket_labels = ["40-45%","45-50%","50-55%","55-60%","60-65%","65-70%","70%+"]
                _bucket_ranges = [(0.40,0.45),(0.45,0.50),(0.50,0.55),(0.55,0.60),(0.60,0.65),(0.65,0.70),(0.70,1.0)]
                for _lo,_hi in _bucket_ranges:
                    _buckets[(_lo,_hi)] = {"wins":0,"total":0,"pred_sum":0.0}
                for _r in _cal_resolved:
                    _p = float(_r.get("prob",0) or 0)
                    for (_lo,_hi) in _bucket_ranges:
                        if _lo <= _p < _hi:
                            _buckets[(_lo,_hi)]["total"] += 1
                            _buckets[(_lo,_hi)]["wins"]  += int(_r.get("outcome") == "WIN")
                            _buckets[(_lo,_hi)]["pred_sum"] += _p
                            break

                _rel_rows = []
                for (_lo,_hi),_label in zip(_bucket_ranges,_bucket_labels):
                    _b = _buckets[(_lo,_hi)]
                    if _b["total"] < 3: continue
                    _actual = _b["wins"] / _b["total"]
                    _pred   = _b["pred_sum"] / _b["total"]
                    _diff   = _actual - _pred
                    _rel_rows.append({
                        "Bucket": _label,
                        "n": _b["total"],
                        "Predicted": f"{_pred:.1%}",
                        "Actual":    f"{_actual:.1%}",
                        "Gap":       f"{_diff:+.1%}",
                        "Status":    "✅" if abs(_diff) < 0.04 else ("⚡" if _diff > 0 else "⚠️"),
                    })
                if _rel_rows:
                    st.markdown(_bc_df_html(_rel_rows), unsafe_allow_html=True)

                # ── Sport calibration breakdown ───────────────────────────────────
                st.markdown("#### 🏆 By Sport")
                _sport_cal = {}
                for _r in _cal_resolved:
                    _sp = _r.get("sport","")
                    if not _sp: continue
                    _sport_cal.setdefault(_sp, {"wins":0,"total":0,"prob_sum":0.0,"edge_sum":0.0})
                    _sport_cal[_sp]["total"]    += 1
                    _sport_cal[_sp]["wins"]     += int(_r.get("outcome") == "WIN")
                    _sport_cal[_sp]["prob_sum"] += float(_r.get("prob",0.5) or 0.5)
                    _sport_cal[_sp]["edge_sum"] += float(_r.get("edge",0) or 0)

                _sport_rows = []
                for _sp, _sc in sorted(_sport_cal.items(), key=lambda x:-x[1]["total"]):
                    _n  = _sc["total"]
                    _hr = _sc["wins"] / _n
                    _pp = _sc["prob_sum"] / _n
                    _ae = _sc["edge_sum"] / _n
                    _err = _pp - _hr
                    _sport_rows.append({
                        "Sport":      _sp,
                        "Bets":       _n,
                        "Hit Rate":   f"{_hr:.1%}",
                        "Pred Prob":  f"{_pp:.1%}",
                        "Avg Edge":   f"{_ae:+.2%}",
                        "Cal Error":  f"{_err:+.1%}",
                        "Status":     "✅ Good" if abs(_err) < 0.04 else ("⚠️ Over" if _err > 0 else "⚡ Under"),
                    })
                if _sport_rows:
                    st.markdown(_bc_df_html(_sport_rows), unsafe_allow_html=True)

                # ── Calibration trend (last 30 vs lifetime) ───────────────────────
                st.markdown("#### 📅 Recent vs Lifetime")
                _recent = [r for r in _cal_resolved[-30:] if r.get("prob")]
                if len(_recent) >= 5:
                    _r_hr   = sum(1 for r in _recent if r.get("outcome") == "WIN") / len(_recent)
                    _r_pp   = sum(float(r.get("prob",0.5)) for r in _recent) / len(_recent)
                    _l_hr   = sum(1 for r in _cal_resolved if r.get("outcome") == "WIN") / len(_cal_resolved)
                    _l_pp   = sum(float(r.get("prob",0.5)) for r in _cal_resolved) / len(_cal_resolved)
                    _tc1,_tc2,_tc3,_tc4 = st.columns(4)
                    _tc1.metric("Last 30 Hit Rate",    f"{_r_hr:.1%}", f"{_r_hr-_l_hr:+.1%} vs lifetime")
                    _tc2.metric("Last 30 Avg Prob",    f"{_r_pp:.1%}", f"{_r_pp-_l_pp:+.1%} vs lifetime")
                    _tc3.metric("Lifetime Hit Rate",   f"{_l_hr:.1%}")
                    _tc4.metric("Lifetime Avg Prob",   f"{_l_pp:.1%}", f"Error: {_l_pp-_l_hr:+.1%}")

                # ── Auto-calibration status ───────────────────────────────────────
                st.markdown("---")
                _cal_thresh = st.session_state.get("calibrated_thresholds", {})
                if _cal_thresh.get("_calibrated"):
                    st.markdown("#### ⚙️ Active Threshold Calibration")
                    st.caption(f"Auto-calibrated from {_cal_thresh.get('_n_records',0)} {_cal_thresh.get('_sport','')} bets")
                    _thresh_rows = []
                    for _t in ["SOVEREIGN","ELITE","APPROVED","LEAN"]:
                        _base = {"SOVEREIGN":0.12,"ELITE":0.08,"APPROVED":0.04,"LEAN":0.03}.get(_t,0)
                        _cur  = _cal_thresh.get(_t, _base)
                        _log  = _cal_thresh.get("_log",{}).get(_t,"")
                        _thresh_rows.append({
                            "Tier":      _t,
                            "Base":      f"{_base:.3f}",
                            "Current":   f"{_cur:.3f}",
                            "Change":    f"{_cur-_base:+.4f}",
                            "Direction": "⬆️ Tighter" if _cur > _base else ("⬇️ Looser" if _cur < _base else "➡️ Unchanged"),
                            "Detail":    _log[:60] if _log else "—",
                        })
                    st.markdown(_bc_df_html(_thresh_rows), unsafe_allow_html=True)
                else:
                    st.info(f"⏳ Auto-calibration activates after 15+ bets per tier. Currently {len(_resolved)} resolved bets logged.")
            else:
                st.info(f"📊 Calibration Dashboard needs **{max(0,30-len(_cal_resolved))} more bets with a real logged prediction** to unlock "
                        f"(has_real_prob=True). Currently {len(_cal_resolved)} of {len(_resolved)} total resolved bets have one — "
                        f"most logged bets don't carry a real probability yet (auto-resolved/OCR-imported bets can't), so this is "
                        f"expected to take a while even as total bet count grows.")


    # ----- TAB 5: LOG BET -----

    # ----- TAB 5: SLIP ANALYZER -----
with tabs[7]:
    st.markdown('<div class="bc-section-header">🔍 Slip Analyzer</div>', unsafe_allow_html=True)
    st.caption("Enter any prop slip — from PrizePicks, ParlayPlay, Underdog, or anywhere. The model analyzes each pick and scores the full parlay.")

    board = st.session_state.get("board_data", [])
    board_loaded = bool(board)

    if not board_loaded:
        st.info("💡 Load the board first for full signal analysis. Or enter picks manually below — we'll analyze using historical averages.")

    st.markdown("### Enter Your Slip")
    st.caption("Add 2–6 picks. The model will analyze each one individually and score the combined parlay.")

    # Initialize slip state
    if "analyzer_picks" not in st.session_state:
        st.session_state["analyzer_picks"] = []

    # Screenshot upload section
    with st.expander("📸 Upload a screenshot of your slip (auto-parse)", expanded=False):
        slip_imgs = st.file_uploader(
            "Upload screenshot of your PrizePicks, ParlayPlay, or Underdog slip",
            type=["jpg", "jpeg", "png", "heic", "webp"],
            key="slip_screenshot",
            accept_multiple_files=True
        )
        if slip_imgs:
            if st.button("🔍 Parse Screenshot", key="parse_slip_screenshot"):
                # Clear stale picks AND previous analysis results before starting fresh
                st.session_state["analyzer_picks"] = []
                st.session_state["analyzer_results"] = []
                st.session_state["ocr_raw_text"] = ""
                all_parsed = []
                with st.spinner("Reading screenshot..."):
                    for img_file in slip_imgs:
                        img_bytes = img_file.read()
                        result = parse_bet_screenshot_ocr(img_bytes)
                        if result:
                            all_parsed.extend(result)
                if all_parsed:
                    # Convert OCR results to analyzer format
                    analyzer_picks = []
                    for bet in all_parsed:
                        # Only skip bets that are already settled (WIN or LOSS from completed games)
                        # PENDING bets (live/upcoming slips) should pass through for analysis
                        if bet.get("outcome") in ("WIN", "LOSS") and not bet.get("overall_result") == "PENDING":
                            continue
                        analyzer_picks.append({
                            "player": bet.get("player", ""),
                            "stat": bet.get("prop", ""),
                            "line": float(bet.get("line", 0) or 0),
                            "side": bet.get("side", "OVER"),
                            "sport": bet.get("sport") or "OTHER",
                        })
                    if analyzer_picks:
                        st.session_state["analyzer_picks"] = analyzer_picks
                        st.success(f"✅ Found {len(analyzer_picks)} picks from screenshot")
                        st.rerun()
                    else:
                        st.warning("Screenshot parsed but no pending picks found. Try the paste option below.")
                else:
                    _has_key = bool(st.secrets.get("OCR_SPACE_API_KEY", ""))
                    if not _has_key:
                        st.error("OCR_SPACE_API_KEY not set in secrets — screenshot parsing disabled.")
                    else:
                        st.error("Could not read screenshot. Check OCR Debug below, or paste the slip manually.")
        with st.expander("🔍 OCR Debug — what was extracted", expanded=False):
            raw = st.session_state.get("ocr_raw_text", "")
            if raw:
                st.markdown(f'<pre style="color:#e0e0e0;background:#1a1a2e;padding:10px;border-radius:6px;font-size:12px;white-space:pre-wrap;word-break:break-word;">{raw[:800]}</pre>', unsafe_allow_html=True)
            else:
                st.caption("Upload a screenshot to see extracted text.")

    def _guess_sport_from_stat(stat_text: str) -> str:
        """Infers sport from the stat name itself, so a pasted mixed-sport
        slip doesn't need a manual per-pick sport selection. Checks the
        most distinctive (least ambiguous) phrases first -- a multi-word
        combo like 'Hits+Runs+RBIs' or 'Passing Yards' is far more sport-
        specific than a single generic word like 'Points' or 'Assists',
        which several sports share. Falls back to MLB (previous hardcoded
        default) only when nothing distinctive matches, rather than
        guessing wildly on an ambiguous single word."""
        s = stat_text.lower()
        # Ordered most-distinctive-first; first match wins.
        checks = [
            ("MLB",    ["strikeout", "hits+runs+rbi", "total bases", "earned run",
                        "pitcher outs", "pitching outs", "hitter fs", "pitcher fs",
                        "home run", "rbi", "walks allowed", "hits allowed"]),
            ("NFL",     ["passing yard", "rushing yard", "receiving yard", "reception",
                        "passing td", "interception", "completion", "sack", "field goal"]),
            ("NHL",     ["shots on goal", "power play point", "save", "blocked shot",
                        "goal+assist", "shorthanded"]),
            ("Tennis",  ["ace", "double fault", "total games", "total sets", "break point"]),
            ("Golf",    ["stroke", "birdie", "bogey", "eagle"]),
            ("UFC",     ["significant strike", "takedown", "submission attempt"]),
            ("Soccer",  ["shots on target", "tackle", "clean sheet", "yellow card"]),
            ("NBA",     ["pts+reb", "pts+ast", "reb+ast", "3-pt made", "3pt made",
                        "point", "rebound", "assist", "turnover", "block", "steal"]),
        ]
        for sport, phrases in checks:
            if any(p in s for p in phrases):
                return sport
        return "MLB"

    # Manual entry in slip analyzer kept minimal - screenshot/text only
    with st.expander("📋 Paste slip text or screenshot", expanded=False):
        paste_text = st.text_area(
            "Paste your slip here (one pick per line)",
            placeholder="Nikola Jokic OVER 27.5 Points\nJayson Tatum OVER 8.5 Rebounds\nLuka Doncic OVER 7.5 Assists",
            height=120,
            key="slip_paste_input"
        )
        if st.button("📥 Parse Slip", key="parse_slip_btn"):
            if paste_text.strip():
                parsed_picks = []
                for line in paste_text.strip().split("\n"):
                    line = line.strip()
                    if not line:
                        continue
                    # Pattern 1: Standard format — Player OVER/UNDER line Stat
                    m = re.match(
                        r"([A-Za-z][A-Za-z\s\.'-]+?)\s+(OVER|UNDER|MORE|LESS)\s+([\d\.]+)\s+(.+)",
                        line, re.IGNORECASE
                    )
                    if m:
                        player = m.group(1).strip()
                        side = "OVER" if m.group(2).upper() in ("OVER","MORE") else "UNDER"
                        try:
                            line_val = float(m.group(3))
                        except (ValueError, TypeError):
                            continue
                        stat = m.group(4).strip()
                        parsed_picks.append({
                            "player": player, "stat": stat,
                            "line": line_val, "side": side,
                            "sport": _guess_sport_from_stat(stat)
                        })
                        continue
                    # Pattern 2: PrizePicks raw — "James Wood ↑ 6.5 Hitter FS"
                    #             or "James Wood  6.5 Hitter FS" (arrow stripped by copy)
                    m2 = re.match(
                        r"([A-Za-z][A-Za-z\s\.'-]+?)\s+([↑↓⬆⬇▲▼])?\s*([\d\.]+)\s+(.+)",
                        line
                    )
                    if m2:
                        player = m2.group(1).strip()
                        arrow = m2.group(2) or ""
                        side = "UNDER" if arrow in "↓⬇▼" else "OVER"
                        try:
                            line_val = float(m2.group(3))
                        except (ValueError, TypeError):
                            continue
                        stat = m2.group(4).strip()
                        # Strip trailing jersey numbers or team codes
                        stat = re.sub(r"\s*#\d+.*$", "", stat).strip()
                        parsed_picks.append({
                            "player": player, "stat": stat,
                            "line": line_val, "side": side,
                            "sport": _guess_sport_from_stat(stat)
                        })
                        continue
                if parsed_picks:
                    st.session_state["analyzer_picks"] = parsed_picks
                    st.session_state["analyzer_results"] = []
                    st.success(f"✅ Parsed {len(parsed_picks)} picks")
                    st.rerun()
                else:
                    st.error("Could not parse. Format: Player Name OVER/UNDER Line Stat")

    # Board paste — for pasting a whole list of AVAILABLE props (no side
    # picked yet), like copying PrizePicks' board directly. Different from
    # the paste box above, which expects an already-decided OVER/UNDER pick
    # per line. This one runs each prop through the model and suggests a
    # side (or PASS if there's no real projection backing it yet).
    with st.expander("📋 Paste a board list (get Over/Under suggestions)", expanded=False):
        st.caption(
            "Paste a raw copy of a PrizePicks prop list — the whole board, before you've "
            "picked a side on anything. Works for any sport in the format shown below; "
            "the model checks each one using the same logic as the rest of the app and "
            "suggests Over, Under, or Pass. You don't need to reformat anything per "
            "sport — just tell it which sport you pasted."
        )
        _board_sport = st.selectbox("Sport", SPORTS, key="_board_paste_sport")
        _board_text = st.text_area(
            "Paste the board list here", height=200, key="_board_paste_text",
            placeholder="Lanlana Tararudee - Player\nLanlana Tararudee\n@ Hanne Vandewinkel Sun 1:00am\n21.5\nTotal Games\nLessMore\n..."
        )

        def _clear_board_paste():
            st.session_state["_board_paste_text"] = ""
            st.session_state["_board_paste_results"] = []

        _bpc1, _bpc2 = st.columns([1, 1])
        with _bpc1:
            _board_analyze_clicked = st.button("🔍 Analyze Board", key="_board_paste_analyze_btn")
        with _bpc2:
            st.button("🗑️ Clear", key="_board_paste_clear_btn", on_click=_clear_board_paste)

        def _analyze_one_board_prop(prop, _board_sport, _t_wta, _t_ctx):
            """Runs on a worker thread -- no st.* rendering calls here, only
            data fetching/computation. Returns the row dict for later
            (main-thread) rendering."""
            player, opponent = prop["player"], prop["opponent"]
            line_val, stat = prop["line"], prop["stat"]
            suggestion, edge_str, edge_val, avg_val = "PASS", "", 0.0, None
            _smart_sig, _tier, _no_data = {}, "PASS", False

            if _board_sport == "Tennis" and "game" in stat.lower():
                # Specialized two-player model (both players + surface +
                # format) — more accurate for this stat than the generic
                # single-player path below, so it takes priority.
                _p_norm = normalize_name(player)
                _tour_key = "wta" if _p_norm in _t_wta else "atp"
                _ctx = _t_ctx.get(_tour_key, {})
                _p1_stats = fetch_tennis_player_stats(player, _tour_key)
                _p2_stats = fetch_tennis_player_stats(opponent, _tour_key)
                if _p1_stats or _p2_stats:
                    _proj = compute_tennis_games_projection(
                        _p1_stats or {}, _p2_stats or {},
                        surface=_ctx.get("surface", "hard"),
                        is_best_of_5=_ctx.get("is_slam", False),
                    )
                    avg_val = _proj["fair_games"]
                    edge_val = avg_val - line_val
                    _abs_edge = abs(edge_val)
                    if _abs_edge < 0.5:
                        suggestion, edge_str, _tier = "PASS", f"({edge_val:+.1f} games, too thin)", "PASS"
                    else:
                        suggestion = "OVER" if edge_val > 0 else "UNDER"
                        edge_str = f"({edge_val:+.1f} games)"
                        # Games-differential bucketed to the same tier
                        # labels used elsewhere, on a scale appropriate
                        # for a games-count edge rather than a % edge.
                        _tier = ("SOVEREIGN" if _abs_edge >= 2.5 else
                                 "ELITE" if _abs_edge >= 1.75 else
                                 "APPROVED" if _abs_edge >= 1.0 else "LEAN")
                else:
                    _no_data = True
                    suggestion, edge_str = "PASS", "no player stats found — can't project"
            else:
                # Same model engine used everywhere else in Slip Analyzer
                # (board cache -> rolling avgs -> live per-sport fetch ->
                # historical table -> league baseline), scored from the
                # Over side so edge sign tells us which way it leans.
                _smart_sig, _tier, _no_data = {}, "PASS", False
                try:
                    _is_home = (prop["matchup_type"] == "vs")
                    _scored = score_pick_standalone(player, stat, line_val, "OVER", _board_sport, is_home=_is_home)
                    edge_val = _scored.get("edge", 0.0)
                    avg_val = _scored.get("avg", 0.0)
                    _smart_sig = _scored.get("smart_signal_data", {})
                    _tier = _scored.get("tier", "PASS")
                    _no_data = _scored.get("no_real_data", False)
                except Exception:
                    edge_val, avg_val = 0.0, 0.0
                if _no_data:
                    _all_errs = st.session_state.get("errors", [])
                    _recent_err = next(
                        (e for e in reversed(_all_errs)
                         if e.get("player") == player or player.lower() in str(e.get("player", "")).lower()),
                        None
                    )
                    if _recent_err:
                        suggestion, edge_str = "PASS", f"[v4-cache-expiry] no data — {_recent_err.get('source','')}: {_recent_err.get('error','')[:80]}"
                    else:
                        suggestion, edge_str = "PASS", f"[v4-cache-expiry] no real player data found — can't project ({len(_all_errs)} errors logged total)"
                elif avg_val:
                    if _smart_sig.get("smart_signal"):
                        suggestion = _smart_sig.get("signal_a_direction", "OVER" if edge_val > 0 else "UNDER")
                        edge_str = f"⚡ Smart Signal — {_smart_sig['signal_a_hit_rate']:.0%} historical ({_smart_sig['signal_a_n']} picks) + edge {edge_val:+.1%}"
                    elif edge_val >= 0.04:
                        suggestion, edge_str = "OVER", f"(edge {edge_val:+.1%})"
                    elif edge_val <= -0.04:
                        suggestion, edge_str = "UNDER", f"(edge {edge_val:+.1%})"
                    else:
                        _lean = "Over" if edge_val >= 0 else "Under"
                        suggestion, edge_str = "PASS", f"(leans {_lean} {edge_val:+.1%}, too thin either way)"

            return {
                "player": player, "opponent": opponent, "matchup_type": prop["matchup_type"],
                "line": line_val, "stat": stat, "suggestion": suggestion,
                "edge_str": edge_str, "edge_val": edge_val, "avg": avg_val,
                "sport": _board_sport, "smart_signal": bool(_smart_sig.get("smart_signal")),
                "tier": _tier, "no_real_data": _no_data,
            }

        if _board_analyze_clicked:
            _board_props = parse_pp_board_paste(_board_text)
            if not _board_props:
                st.warning("Couldn't find any props in that paste. Check the format matches a PrizePicks board copy.")
            else:
                # Sport-mismatch check: team abbreviations that only exist
                # in one league or the other (no cross-league ambiguity),
                # so we can catch e.g. WNBA props pasted while NBA is
                # selected in the dropdown -- exactly the mix-up that
                # caused a long, confusing "no data" debugging chase.
                _league_exclusive_teams = {
                    # Verified against real WNBA team abbreviations pulled
                    # live earlier this session, cross-checked against
                    # standard NBA abbreviations -- teams that exist in
                    # BOTH leagues (ATL, CHI, DAL, IND, MIN, PHX, POR, TOR)
                    # are deliberately excluded from both sets since they
                    # give no signal either way. 'LAS' included alongside
                    # ESPN's 'LA' since PrizePicks' own board uses 'LAS'
                    # for the Sparks, confirmed from a real pasted board.
                    "WNBA": {"SEA", "GS", "LA", "LAS", "CON", "NY", "LV", "WSH"},
                    "NBA": {"OKC", "HOU", "ORL", "WAS", "BKN", "UTA", "MEM", "NOP",
                             "MIA", "NYK", "MIL", "PHI", "GSW", "BOS", "SAC", "CLE",
                             "LAL", "LAC", "SAS", "DET", "CHA", "DEN"},
                }
                _pasted_teams = {p.get("team", "").upper() for p in _board_props if p.get("team")}
                _other_sport_hits = {}
                for _lg, _teams in _league_exclusive_teams.items():
                    if _lg == _board_sport:
                        continue
                    _hit = _pasted_teams & _teams
                    if _hit:
                        _other_sport_hits[_lg] = _hit
                if _other_sport_hits and _board_sport in ("NBA", "WNBA"):
                    _hit_lg, _hit_teams = next(iter(_other_sport_hits.items()))
                    st.warning(
                        f"⚠️ This looks like **{_hit_lg}** data (team codes: {', '.join(sorted(_hit_teams))}), "
                        f"but **{_board_sport}** is selected above. Switch the Sport dropdown to {_hit_lg} and "
                        f"re-analyze, or these props will show as 'no data' even though they're valid."
                    )

                _t_wta = fetch_tennis_scoreboard("wta") if _board_sport == "Tennis" else {}
                _t_ctx = fetch_tennis_tournament_context() if _board_sport == "Tennis" else {}
                # Pre-warm shared caches ONCE, sequentially, before
                # parallelizing -- avoids worker threads racing to
                # populate the same session_state key simultaneously.
                # An EMPTY cached result expires after 5 min instead of
                # sticking for the whole session -- otherwise a single
                # transient failure (or a fix landing mid-session) would
                # silently block every retry until a full page reload.
                if _board_sport == "WNBA":
                    _rolling_cached = st.session_state.get("wnba_rolling_avgs")
                    _rolling_ts = st.session_state.get("wnba_rolling_avgs_ts", 0)
                    _rolling_stale = (not _rolling_cached) and (time.time() - _rolling_ts > 300)
                    if _rolling_cached is None or _rolling_stale:
                        st.session_state["wnba_rolling_avgs"] = fetch_wnba_rolling_averages() or {}
                        st.session_state["wnba_rolling_avgs_ts"] = time.time()
                    _fetch_wnba_roster_via_teams()

                # Each prop needs its own independent network call for
                # player stats -- these were previously running strictly
                # serially (one 5-12s call after another), which is the
                # main remaining source of slow analysis on boards with
                # many different players. Running them concurrently cuts
                # wall-clock time roughly in proportion to worker count.
                #
                # IMPORTANT: st.session_state (read/written internally by
                # score_pick_standalone, fetch_wnba_player_stats's
                # diagnostic logging, and the WNBA rolling-avg/roster
                # caches) is bound to Streamlit's per-thread script-run
                # context, which worker threads don't have by default --
                # session_state calls on a thread without it silently
                # no-op instead of raising, so this must be attached to
                # every worker thread explicitly or all of that state
                # access quietly does nothing.
                _script_ctx = get_script_run_ctx()

                def _analyze_with_ctx(p):
                    add_script_run_ctx(threading.current_thread(), _script_ctx)
                    return _analyze_one_board_prop(p, _board_sport, _t_wta, _t_ctx)

                with st.spinner(f"Analyzing {len(_board_props)} props..."):
                    with ThreadPoolExecutor(max_workers=8) as _ex:
                        _board_rows = list(_ex.map(_analyze_with_ctx, _board_props))
                st.session_state["_board_paste_results"] = _board_rows
                st.success(f"Found {len(_board_rows)} props.")

        _board_rows = st.session_state.get("_board_paste_results", [])
        if _board_rows:
            if any(r.get("suggestion") == "PASS" for r in _board_rows):
                st.caption(
                    "PASS means both Over and Under are too thin to call — not just the side shown. "
                    "Manually picking the other side won't turn a PASS into a stronger tier."
                )
            _sugg_color = {"OVER": "#22c55e", "UNDER": "#e04040", "PASS": "#6a7a8a"}
            for _bi, row in enumerate(_board_rows):
                _rc1, _rc2 = st.columns([5, 1])
                with _rc1:
                    _sig_prefix = '<span style="color:#a855f7;font-weight:700;">⚡ </span>' if row.get("smart_signal") else ""
                    _tier_val = row.get("tier", "PASS")
                    _tier_color = TIER_COLORS.get(_tier_val, "#6a7a8a")
                    _tier_badge = (
                        f'<span style="background:{_tier_color}22;color:{_tier_color};'
                        f'border:1px solid {_tier_color};border-radius:5px;padding:3px 9px;'
                        f'font-size:13px;font-weight:700;margin-right:6px;">{_tier_val}</span>'
                    )
                    st.markdown(
                        f'<div style="padding:6px 0;">'
                        f'{_tier_badge}{_sig_prefix}<b>{row["player"]}</b> · {row["stat"]} {row["line"]} — '
                        f'<span style="color:{_sugg_color[row["suggestion"]]};font-weight:700;">'
                        f'{row["suggestion"]}</span> '
                        f'<span style="color:#8ab4d4;font-size:12px;">{row["edge_str"]}</span>'
                        f'</div>', unsafe_allow_html=True,
                    )
                with _rc2:
                    _already_locked = any(
                        l.get("player") == row["player"] and l.get("prop") == row["stat"]
                        for l in st.session_state.get("locks", [])
                    )
                    if row["suggestion"] == "PASS":
                        st.caption("—")
                    elif _already_locked:
                        st.caption("🔒 Locked")
                    elif st.button("🔒 Lock", key=f"_board_lock_{_bi}"):
                        st.session_state["locks"].append({
                            "player": row["player"], "prop": row["stat"],
                            "line": row["line"], "side": row["suggestion"],
                            "wager": active_unit(), "prob": 0.5 + abs(row["edge_val"]),
                            "edge": row["edge_val"], "tier": _get_cal_tier(row["edge_val"], row["sport"]),
                            "status": "PENDING",
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "sport": row["sport"], "team": "",
                            "signal_values": {}, "source": "board_paste",
                            "smart_signal": row.get("smart_signal", False),
                        })
                        save_json_data(LOCKS_PATH, st.session_state.locks)
                        if not save_to_gist("locks", st.session_state.locks):
                            st.warning("Locked locally, but the sync didn't go through — try again in a moment if it doesn't stick.")
                        st.rerun()
            st.caption(
                "🔒 Lock adds the pick to Locks & Ledger the same as any other pick — it flows into "
                "your history, calibration (SEM/Brier), and CLV tracking once it settles. "
                "PASS picks can't be locked."
            )

    st.markdown("---")
    # Show current slip
    if st.session_state["analyzer_picks"]:
        st.markdown("---")
        st.markdown(f"### Your Slip ({len(st.session_state['analyzer_picks'])} picks)")

        for i, pick in enumerate(st.session_state["analyzer_picks"]):
            col_p1, col_p2 = st.columns([5, 1])
            with col_p1:
                st.markdown(f"**{pick['player']}** {pick['side']} {pick['line']} {pick['stat']} ({pick.get('sport','NBA')})")
            with col_p2:
                if st.button("❌", key=f"remove_pick_{i}"):
                    st.session_state["analyzer_picks"].pop(i)
                    st.rerun()

        if st.button("🗑️ Clear Slip", key="clear_slip"):
            st.session_state["analyzer_picks"] = []
            st.session_state["analyzer_results"] = []
            st.session_state["ocr_raw_text"] = ""
            st.rerun()

        st.markdown("---")

        if st.button("🔍 Analyze This Slip", key="analyze_slip_btn", type="primary"):
            picks = st.session_state["analyzer_picks"]
            results = []

            for pick in picks:
                player = pick["player"]
                stat = pick["stat"]
                line = pick["line"]
                side = pick["side"]
                sport = pick.get("sport") or "OTHER"

                # Score via full standalone pipeline (board → rolling → BDL → table → baseline)
                scored = score_pick_standalone(player, stat, line, side, sport)
                edge        = scored["edge"]
                prob        = scored["prob"]
                avg         = scored["avg"]
                tier        = scored["tier"]
                ev_2        = scored["ev_2"]
                confidence  = scored["confidence"]
                data_source = scored["data_source"]
                better_line = ""
                dk_note     = ""
                sharp_flag  = ""
                line_note   = ""

                # Check board for extra context (line diff note, sharp flag, better line)
                board_match = None
                if board:
                    norm_player = normalize_name(player)
                    _sps_idx = score_pick_standalone._board_index_cache.get("_index", {})
                    if score_pick_standalone._board_index_cache.get("_id") == id(board):
                        board_match = _sps_idx.get((norm_player, stat.lower()))
                    else:
                        for b in board:
                            if normalize_name(b.get("Player","")) == norm_player and                            b.get("Prop","").lower() == stat.lower():
                                board_match = b
                                break
                if board_match:
                    better_line = board_match.get("BetterLineNote", "")
                    dk_note     = board_match.get("DKSalaryNote", "")
                    sharp_flag  = board_match.get("SharpFlag", "")
                    board_line  = board_match.get("Line", line)
                    line_diff   = round(float(line) - float(board_line), 1)
                    if line_diff != 0:
                        direction = "higher" if line_diff > 0 else "lower"
                        line_note = f"⚠️ Your line ({line}) is {abs(line_diff)} {direction} than board ({board_line})"

                # Determine recommendation
                _smart_sig = scored.get("smart_signal_data", {})
                if _smart_sig.get("smart_signal"):
                    rec = "⚡ SMART SIGNAL"
                    rec_color = "#a855f7"
                elif edge >= 0.08:
                    rec = "✅ STRONG PLAY"
                    rec_color = "#22c55e"
                elif edge >= 0.04:
                    rec = "✅ PLAY"
                    rec_color = "#0ea5a0"
                elif edge >= 0.0:
                    rec = "⚠️ LEAN"
                    rec_color = "#e8a020"
                elif edge >= -0.05:
                    rec = "⚠️ WEAK"
                    rec_color = "#e07020"
                else:
                    rec = "❌ FADE"
                    rec_color = "#e04040"

                results.append({
                    "player": player, "stat": stat, "line": line,
                    "side": side, "sport": sport,
                    "edge": edge, "prob": prob, "avg": avg,
                    "tier": tier, "ev_2": ev_2,
                    "rec": rec, "rec_color": rec_color,
                    "better_line": better_line,
                    "dk_note": dk_note,
                    "sharp_flag": sharp_flag,
                    "signal_values": _board_prop_signal_values(board_match) if board_match else {},
                    "line_note": line_note,
                    "confidence": confidence,
                    "data_source": data_source,
                    "board_matched": board_match is not None,
                    "smart_signal_data": _smart_sig,
                })

            st.session_state["analyzer_results"] = results

    # Display results
    if st.session_state.get("analyzer_results"):
        results = st.session_state["analyzer_results"]
        st.markdown("## 📊 Analysis Results")

        all_probs = [r["prob"] for r in results]
        combined_prob = parlay_prob(all_probs)
        n_picks = len(results)
        multiplier = PRIZEPICKS_MULTIPLIERS.get(n_picks, 3.0)
        breakeven = prizepicks_breakeven_prob(n_picks)
        parlay_ev = combined_prob - breakeven
        ev_color = "#22c55e" if parlay_ev > 0 else "#e04040"

        # Overall verdict
        strong_plays = sum(1 for r in results if r["edge"] >= 0.08)
        fades = sum(1 for r in results if r["edge"] < -0.05)

        if fades > 0:
            overall = f"❌ AVOID — {fades} pick(s) model says FADE"
            overall_color = "#e04040"
        elif strong_plays == n_picks:
            overall = "✅ STRONG SLIP — All picks have solid edge"
            overall_color = "#22c55e"
        elif strong_plays >= n_picks // 2:
            overall = "✅ GOOD SLIP — Most picks have edge"
            overall_color = "#0ea5a0"
        elif parlay_ev > 0:
            overall = "⚠️ MARGINAL — Positive EV but weak individual picks"
            overall_color = "#e8a020"
        else:
            overall = "❌ SKIP — Combined EV is negative"
            overall_color = "#e04040"

        st.markdown(
            f'<div style="background:var(--bc-bg-card);border:2px solid {overall_color};border-radius:10px;'
            f'padding:16px 20px;margin-bottom:14px;">'
            f'<div style="font-size:18px;font-weight:700;color:{overall_color};margin-bottom:8px;">{overall}</div>'
            f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;">'
            f'<div style="background:#060c14;border-radius:6px;padding:8px;text-align:center;">'
            f'<div style="font-size:9px;color:var(--bc-dim);text-transform:uppercase">Combined Prob</div>'
            f'<div style="font-size:20px;font-weight:700;color:#e8f0f8">{combined_prob:.1%}</div></div>'
            f'<div style="background:#060c14;border-radius:6px;padding:8px;text-align:center;">'
            f'<div style="font-size:9px;color:var(--bc-dim);text-transform:uppercase">{n_picks}-pick Payout</div>'
            f'<div style="font-size:20px;font-weight:700;color:#e8f0f8">{multiplier}x</div></div>'
            f'<div style="background:#060c14;border-radius:6px;padding:8px;text-align:center;">'
            f'<div style="font-size:9px;color:var(--bc-dim);text-transform:uppercase">Breakeven</div>'
            f'<div style="font-size:20px;font-weight:700;color:#e8f0f8">{breakeven:.1%}</div></div>'
            f'<div style="background:#060c14;border-radius:6px;padding:8px;text-align:center;">'
            f'<div style="font-size:9px;color:var(--bc-dim);text-transform:uppercase">True EV</div>'
            f'<div style="font-size:20px;font-weight:700;color:{ev_color}">{parlay_ev:+.1%}</div></div>'
            f'</div></div>',
            unsafe_allow_html=True
        )

        # Individual pick results
        st.markdown("### Pick-by-Pick Breakdown")
        for r in results:
            tier_color = TIER_COLORS.get(r["tier"], "#7a8a9a")
            avg_display = f"{r['avg']:.1f}" if r["avg"] else "No data"
            try:
                _fp_match = get_favoredprops_match(r["player"], r["stat"], r["sport"], r.get("side"))
            except Exception:
                _fp_match = {}
            _fp_html = ""
            if _fp_match:
                _fp_hit = _fp_match.get("l10_hit_rate")
                _fp_hit_str = f"{_fp_hit:.0%} L10 hit rate" if isinstance(_fp_hit, (int, float)) else ""
                _fp_html = (
                    f'<div style="font-size:12px;color:#6a9ac9;margin-top:4px;">'
                    f'📊 FavoredProps: {_fp_match.get("n_books","?")} books, avg {_fp_match.get("avg_odds","")}'
                    f'{" · " + _fp_hit_str if _fp_hit_str else ""}</div>'
                )
            st.markdown(
                f'<div style="background:var(--bc-bg-card);border:1px solid var(--bc-border);border-left:4px solid {r["rec_color"]};'
                f'border-radius:8px;padding:12px 16px;margin-bottom:10px;">'
                f'<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;margin-bottom:8px;">'
                f'<div><span style="font-size:15px;font-weight:700;color:#e8f0f8">{r["player"]}</span>'
                f'<span style="color:{tier_color};margin-left:8px;font-size:16px">{r["side"]} {r["line"]} {r["stat"]}</span>'
                f'<span style="background:{tier_color};color:#000;font-size:9px;font-weight:700;padding:2px 7px;border-radius:8px;margin-left:8px">{r["tier"]}</span></div>'
                f'<div style="background:{r["rec_color"]}22;border:1px solid {r["rec_color"]}44;border-radius:8px;'
                f'padding:5px 12px;font-size:18px;font-weight:700;color:{r["rec_color"]}">{r["rec"]}</div>'
                f'</div>'
                f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-bottom:8px;">'
                f'<div style="background:#060c14;border-radius:5px;padding:6px;text-align:center;">'
                f'<div style="font-size:8px;color:var(--bc-dim);text-transform:uppercase">Edge</div>'
                f'<div style="font-size:17px;font-weight:700;color:{r["rec_color"]}">{r["edge"]:+.1%}</div></div>'
                f'<div style="background:#060c14;border-radius:5px;padding:6px;text-align:center;">'
                f'<div style="font-size:8px;color:var(--bc-dim);text-transform:uppercase">Hit Prob</div>'
                f'<div style="font-size:17px;font-weight:700;color:#e8f0f8">{r["prob"]:.1%}</div></div>'
                f'<div style="background:#060c14;border-radius:5px;padding:6px;text-align:center;">'
                f'<div style="font-size:8px;color:var(--bc-dim);text-transform:uppercase">Avg vs Line</div>'
                f'<div style="font-size:17px;font-weight:700;color:#e8f0f8">{avg_display}</div></div>'
                f'<div style="background:#060c14;border-radius:5px;padding:6px;text-align:center;">'
                f'<div style="font-size:8px;color:var(--bc-dim);text-transform:uppercase">2-pick EV</div>'
                f'<div style="font-size:17px;font-weight:700;color:#22c55e">{r["ev_2"]}</div></div>'
                f'</div>'
                f'<div style="font-size:14px;color:{"#e8a020" if not r.get("board_matched") else "#6a7a8a"}>'  
                f'{"⚠️ NO BOARD DATA — load the board for real scores | " if not r.get("board_matched") else "📡 "}'  
                f'{r["data_source"]} | Confidence: {r["confidence"]}'
                f'{" | " + r["sharp_flag"] if r["sharp_flag"] else ""}'
                f'{" | " + r["dk_note"] if r["dk_note"] else ""}</div>'
                f'{_fp_html}'
                f'{_better_html}'
                f'{_note_html}'
                f'</div>',
                unsafe_allow_html=True
            )

        # Lock all good picks button
        good_picks = [r for r in results if r["edge"] >= 0.04 or r.get("smart_signal_data", {}).get("smart_signal")]
        if good_picks and board:
            st.markdown("---")
            if st.button(f"🔒 Lock all {len(good_picks)} good picks from this slip", key="lock_slip_picks"):
                locked = 0
                for r in good_picks:
                    norm = normalize_name(r["player"])
                    board_match = next((b for b in board if normalize_name(b.get("Player","")) == norm and b.get("Prop","").lower() == r["stat"].lower()), None)
                    if board_match:
                        already = any(l.get("player") == r["player"] and l.get("prop") == r["stat"] for l in st.session_state.get("locks", []))
                        if not already:
                            st.session_state["locks"].append({
                                "player": r["player"], "prop": r["stat"],
                                "line": r["line"], "side": r["side"],
                                "wager": active_unit(), "prob": r["prob"],
                                "edge": r["edge"], "tier": r["tier"],
                                "status": "PENDING",
                                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                "sport": r["sport"],
                                "smart_signal": r.get("smart_signal_data", {}).get("smart_signal", False),
                                "team": board_match.get("Team",""),
                                "signal_values": _board_prop_signal_values(board_match),
                                "clv_capture": _capture_clv_placement(r["player"], r["stat"], r.get("prob", 0.5)),
                            })
                            try:
                                record_pinnacle_line(st.session_state["locks"][-1], board)
                            except Exception:
                                pass
                            locked += 1
                if locked:
                    save_json_data(LOCKS_PATH, st.session_state.locks)
                    save_to_gist("locks", st.session_state.locks)  # persists across restarts
                    st.success(f"✅ Locked {locked} picks")
                    _slip_teams = sorted(set(
                        next((b for b in board if normalize_name(b.get("Player","")) == normalize_name(r["player"])), {}).get("Team","")
                        for r in good_picks
                    ) - {""})
                    for _slip_team in _slip_teams:
                        _show_team_exposure_warning(_slip_team, good_picks[0]["sport"] if good_picks else "")
                    st.rerun()

        # ── Log this slip as a placed bet (merged with Log Bet → Bulk Entry) ──
        # Previously the only way to record an already-placed slip was to
        # re-paste/re-type the same picks a second time in the Log Bet tab's
        # Bulk Entry sub-tab. This reuses the exact same log_manual_bet()
        # pipeline directly from the already-analyzed results — one parse,
        # one place to enter the wager, done.
        st.markdown("---")
        with st.expander(f"📝 Log this slip as a placed bet ({len(results)} picks)", expanded=False):
            st.caption("Already placed this slip for real? Log it here — no need to re-enter it in Log Bet → Bulk Entry, this writes to the same history.")
            _ls_col1, _ls_col2, _ls_col3 = st.columns(3)
            with _ls_col1:
                _ls_wager = st.number_input("Total stake ($)", min_value=0.0, value=float(active_unit()) if callable(active_unit) else 10.0, step=1.0, key="log_slip_wager")
            with _ls_col2:
                _ls_outcome = st.selectbox("Outcome", ["PENDING", "WIN", "LOSS", "PUSH"], key="log_slip_outcome")
            with _ls_col3:
                _ls_source = st.text_input("Placed on (book/app)", value="PrizePicks", key="log_slip_source")

            if st.button(f"✅ Log all {len(results)} picks as one parlay", key="log_slip_as_bet"):
                _ls_slip_id = st.session_state.get("current_slip_id") or datetime.now().strftime("%Y-%m-%d %H:%M")
                for _lsi, r in enumerate(results):
                    log_manual_bet(
                        player=r["player"], prop=r["stat"], line=r["line"], side=r["side"],
                        sport=r["sport"], outcome=_ls_outcome,
                        # Real fix (2026-08-15): only the first leg carries the
                        # real wager -- same fix as Pick For You and Locks &
                        # Ledger, same real bug (N-pick parlay's profit/loss
                        # was being recorded N times).
                        wager=(_ls_wager if _lsi == 0 else 0.0),
                        pick_count=len(results), bet_type="prop", source=f"{_ls_source} (via Slip Analyzer)",
                        bet_date=_ls_slip_id, tier=r["tier"], edge=r["edge"], prob=r["prob"],
                        signals=r.get("signal_values"),
                        notes="Logged from Slip Analyzer",
                    )
                st.success(f"✅ Logged {len(results)} picks as one parlay — see Log Bet → Recent Activity")
                st.rerun()

        # Generate slip summary report
        st.markdown("---")
        st.markdown("## 📋 Slip Analysis Report")
        st.caption("Same format as your daily Gem brief — copy and paste into your Gemini Gem for deeper analysis.")
        slip_summary = generate_slip_summary(st.session_state["analyzer_picks"], results)
        st.text_area(
            "Copy this into your Gem:",
            value=slip_summary,
            height=400,
            key="slip_summary_output"
        )
        st.caption("💡 Ctrl+A to select all, Ctrl+C to copy.")


@st.cache_data(ttl=1800)
def search_players_by_name(query, sport):
    """
    Search for players by (partial) name, using whichever source actually
    covers that sport — the old approach always hit BallsDontLie's NBA
    endpoint (v1/players) regardless of selected sport, so an MLB search for
    "soto" silently returned nothing since BDL's free tier is NBA-only.

    Dispatches to the same live source each sport's game-log fetcher already
    uses, so results are guaranteed to also be lookupable afterward:
      MLB  -> statsapi.mlb.com (official, no auth)
      NHL  -> search.d3.nhle.com (official, no auth)
      NFL  -> local nfl_player_db.pkl (already built/cached — no live call)
      NBA/WNBA -> BallsDontLie v1/players (needs BDL_API_KEY)

    Returns a list of display-name strings (deduped, capped at 8).
    """
    sport = sport.upper()
    try:
        if sport == "MLB":
            r = _http.get(
                "https://statsapi.mlb.com/api/v1/people/search",
                params={"names": query, "sportId": 1}, timeout=6)
            if r.status_code != 200: return []
            return [p.get("fullName", "") for p in r.json().get("people", [])[:8] if p.get("fullName")]

        if sport == "NHL":
            r = _http.get(
                "https://search.d3.nhle.com/api/v1/search",
                params={"q": query, "type": "player", "active": "true"}, timeout=6)
            if r.status_code != 200: return []
            _results = r.json()
            if not isinstance(_results, list): return []
            out = []
            for p in _results[:8]:
                _nm = p.get("name") or f"{p.get('firstName','')} {p.get('lastName','')}".strip()
                if _nm: out.append(_nm)
            return out

        if sport == "NFL":
            db = _safe_load_pkl(os.path.join(CACHE_DIR, "nfl_player_db.pkl")) or {}
            q_norm = normalize_name(query)
            return sorted({p["name"] for p in db.values()
                           if q_norm in normalize_name(p.get("name",""))})[:8]

        # NBA / WNBA — BallsDontLie
        if not BDL_API_KEY:
            return []
        r = _http.get(
            "https://api.balldontlie.io/v1/players",
            headers={"Authorization": BDL_API_KEY},
            params={"search": query, "per_page": 8}, timeout=6)
        if r.status_code != 200: return []
        return [f"{p['first_name']} {p['last_name']}" for p in r.json().get("data", [])]
    except (requests.RequestException, ValueError, KeyError):
        return []


def get_goalie_for_team(team_abbr, goalies=None):
    """Return goalie name and confirmed status for a team."""
    if goalies is None:
        goalies = st.session_state.get("nhl_starting_goalies", {})
    g = goalies.get(team_abbr, {})
    name      = g.get("goalie","Unknown")
    confirmed = g.get("confirmed", False)
    return name, confirmed


with tabs[8]:
    st.markdown('<div class="bc-section-header">🔎 Player Lookup</div>', unsafe_allow_html=True)

    with st.expander("📊 Props Browser — browse all props, sort/filter (no name lookup needed)", expanded=False):
        _pbr_sport = st.selectbox("Sport", ["MLB", "NBA", "NFL", "NHL", "WNBA"], key="_pbr_sport")
        _pbr_raw = st.session_state.get("bettingpros_props", [])
        _pbr_raw = [p for p in _pbr_raw if str(p.get("sport", "")).upper() == _pbr_sport] if _pbr_raw else []
        if not _pbr_raw:
            st.caption("No BettingPros props loaded for this sport yet — load a board first.")
        else:
            _pbr_min_rating = st.slider("Min Bet Rating", 1, 5, 1, key="_pbr_min_rating")
            _pbr_rows = []
            for p in _pbr_raw:
                proj = p.get("projection", {}) or {}
                side = str(proj.get("recommended_side", "")).lower()
                if side not in ("over", "under"):
                    continue
                side_data = p.get(side, {}) or {}
                if (proj.get("bet_rating") or 0) < _pbr_min_rating:
                    continue
                perf = p.get("performance", {}) or {}
                def _pbr_fmt(window):
                    w = perf.get(window, {}) or {}
                    o, u = w.get("over", 0), w.get("under", 0)
                    hits = o if side == "over" else u
                    return f"{hits}/{o+u}" if (o + u) else "—"
                player = (p.get("participant", {}) or {}).get("player", {}) or {}
                stat_slug = p.get("links", {}).get("odds", "").rstrip("/").split("/")[-1]
                stat_name = stat_slug.replace("-", " ").title() if stat_slug else f"Market {p.get('market_id','?')}"
                _pbr_rows.append({
                    "Player": player.get("last_name") and f"{player.get('first_name','')} {player.get('last_name','')}".strip() or "—",
                    "Team": player.get("team", ""), "Pos": player.get("position", ""),
                    "Stat": stat_name, "Line": side_data.get("line"), "Side": side.upper(),
                    "L5": _pbr_fmt("last_5"), "L10": _pbr_fmt("last_10"), "L15": _pbr_fmt("last_15"), "Szn": _pbr_fmt("season"),
                    "Streak": f"{perf.get('streak','')} {str(perf.get('streak_type','')).upper()}" if perf.get("streak") else "",
                    "Proj": proj.get("value"), "Diff": proj.get("diff"),
                    "EV": f"{(proj.get('expected_value') or 0)*100:+.1f}%", "⭐": "⭐" * int(proj.get("bet_rating") or 0),
                })
            if _pbr_rows:
                import pandas as _pbr_pd
                _pbr_df = _pbr_pd.DataFrame(_pbr_rows)
                _pbr_sort = st.selectbox("Sort by", ["⭐", "EV", "Diff"], key="_pbr_sort")
                _pbr_df = _pbr_df.sort_values(_pbr_sort, ascending=False, key=lambda c: c.str.len() if _pbr_sort == "⭐" else c)
                st.dataframe(_pbr_df, use_container_width=True, hide_index=True)
                st.caption(f"{len(_pbr_df)} props · BettingPros")
            else:
                st.caption("No props meet the current filters.")

    st.caption("Deep dive on any player — game log, hit rates, H2H vs tonight's opponent, home/away splits. Powered by BallsDontLie.")

    if not BDL_API_KEY:
        st.warning("BallsDontLie API key required. Add BALLSDONTLIE_API_KEY to Streamlit Secrets.")
    else:
        # ── Auto-suggest: search BDL as user types, populate from board if matched ──
        # (player-name suggestion list is now built per-sport further below,
        # scoped to pl_sport_sel — see _board_names_this_sport)

        col_pl0, col_pl1, col_pl2 = st.columns([1,2,1])
        with col_pl0:
            pl_sport_sel = st.selectbox("Sport", ["NBA","MLB","NHL","WNBA","NFL"], key="pl_sport_sel")
            # Auto-clear stale opponent/line whenever sport changes — previously
            # "SAS" (an NBA team) could stick around after switching to MLB
            # because st.text_input's `value=` param is ignored on reruns once
            # a widget key already has session state. Track sport changes
            # explicitly and wipe the dependent fields when it flips.
            if st.session_state.get("_pl_last_sport") != pl_sport_sel:
                st.session_state["_pl_last_sport"] = pl_sport_sel
                st.session_state["pl_opp"] = "— select opponent —"
                st.session_state["pl_line"] = 0.0
        with col_pl1:
            pl_name_input = st.text_input("Player name", placeholder="Start typing a name…", key="pl_name")
            # Auto-suggest from loaded board — scoped to pl_sport_sel, not just
            # whatever sport the main board happens to be loaded for. Player
            # Lookup has its own independent sport selector, so "soto" typed
            # while the main board sits on NBA should still search MLB names.
            _board_names_this_sport = sorted(set(
                p["Player"] for p in st.session_state.get("board_data", [])
                if p.get("Sport", "").upper() == pl_sport_sel.upper()
            )) if st.session_state.get("board_data", []) else []
            if pl_name_input and len(pl_name_input) >= 3:
                _matches = [n for n in _board_names_this_sport if normalize_name(pl_name_input) in normalize_name(n)]
                if _matches:
                    _selected = st.selectbox("Suggestions from today's board", ["— type to search —"] + _matches[:8], key="pl_suggest")
                    if _selected and _selected != "— type to search —":
                        pl_name_input = _selected
                        # Auto-fill opponent from board data
                        _board_match = next((p for p in st.session_state.get("board_data", [])
                                             if p["Player"] == _selected and p.get("Sport","").upper() == pl_sport_sel.upper()), None)
                        if _board_match and not st.session_state.get("pl_opp"):
                            st.session_state["pl_opp_autofill"] = _board_match.get("Opponent", "")
                elif len(pl_name_input) >= 4:
                    # Fall back to a live search — dispatches to the correct
                    # source per sport (MLB Stats API, NHL search, local NFL
                    # DB, or BallsDontLie for NBA/WNBA). See
                    # search_players_by_name() for why this replaced a
                    # BDL-only call that silently returned nothing for
                    # non-NBA sports.
                    _suggest_cache_key = f"namesearch_{pl_sport_sel}_{pl_name_input[:6].lower()}"
                    if _suggest_cache_key not in st.session_state:
                        st.session_state[_suggest_cache_key] = search_players_by_name(pl_name_input, pl_sport_sel)
                    _bdl_matches = st.session_state.get(_suggest_cache_key, [])
                    if _bdl_matches:
                        _selected2 = st.selectbox("Players found", ["— select —"] + _bdl_matches, key="pl_bdl_suggest")
                        if _selected2 and _selected2 != "— select —":
                            pl_name_input = _selected2
            pl_name = pl_name_input

        with col_pl2:
            _pl_sport_for_stats = st.session_state.get("pl_sport_sel", "NBA")
            _stat_options_by_sport = {
                "NBA":  ["Points", "Rebounds", "Assists", "3-PT Made", "Steals", "Blocked Shots", "Turnovers", "Pts+Reb+Ast"],
                "WNBA": ["Points", "Rebounds", "Assists", "3-PT Made", "Steals", "Blocked Shots", "Turnovers", "Pts+Reb+Ast"],
                "MLB":  ["Hits", "Home Runs", "RBI", "Runs", "Strikeouts (Pitcher)", "Walks", "Total Bases", "Stolen Bases"],
                "NHL":  ["Goals", "Assists", "Points", "Shots on Goal", "Saves", "Goals+Assists"],
                "NFL":  ["Pass Yards", "Rush Yards", "Receiving Yards", "Touchdowns", "Receptions", "Pass Completions"],
            }
            _pl_stat_opts = _stat_options_by_sport.get(_pl_sport_for_stats, _stat_options_by_sport["NBA"])
            pl_stat = st.selectbox("Stat", _pl_stat_opts, key="pl_stat")

        # Line auto-defaults to the player's own average if left unset — this
        # only needs manual entry to check against a specific book's number,
        # so it's tucked away instead of taking up a full column every time.
        with st.expander("⚙️ Set a specific line to check (optional — defaults to player's average)", expanded=False):
            pl_line = st.number_input("Line", min_value=0.0, value=0.0, step=0.5, key="pl_line")

        col_pl4, col_pl5 = st.columns(2)
        with col_pl4:
            # Dropdown scoped to the selected sport — replaces free text so
            # there's no typo risk and no way for a stale cross-sport value
            # to display (each sport has its own fixed option list).
            _opp_options = ["— select opponent —"] + PLAYER_LOOKUP_OPPONENT_OPTIONS.get(pl_sport_sel, [])
            _opp_autofill = st.session_state.pop("pl_opp_autofill", "")
            if _opp_autofill and _opp_autofill in _opp_options:
                st.session_state["pl_opp"] = _opp_autofill
            elif st.session_state.get("pl_opp") not in _opp_options:
                st.session_state["pl_opp"] = "— select opponent —"
            _pl_opp_sel = st.selectbox("Opponent (abbr)", _opp_options, key="pl_opp")
            pl_opp = "" if _pl_opp_sel == "— select opponent —" else _pl_opp_sel
        with col_pl5:
            pl_games = st.slider("Last N games", 5, 30, 15, key="pl_games")

        if st.button("🔍 Look Up Player", key="pl_lookup_btn", type="primary"):
            if pl_name:
                with st.spinner(f"Loading {pl_name} data..."):
                    _sport_sel = st.session_state.get("pl_sport_sel", "NBA")
                    if _sport_sel == "MLB":
                        logs = fetch_mlb_player_game_logs(pl_name, last_n=pl_games)
                    elif _sport_sel == "NHL":
                        logs = fetch_nhl_player_game_logs(pl_name, last_n=pl_games)
                    elif _sport_sel == "WNBA":
                        logs = fetch_wnba_player_game_logs(pl_name, last_n=pl_games)
                    else:
                        logs = fetch_player_game_logs(pl_name, last_n=pl_games)
                    st.session_state["pl_logs"] = logs
                    st.session_state["pl_name_display"] = pl_name
                    st.session_state["pl_sport_used"] = _sport_sel
            else:
                st.error("Enter a player name.")

        if st.session_state.get("pl_logs"):
            logs = st.session_state["pl_logs"]
            pl_name_d = st.session_state.get("pl_name_display", pl_name)

            _pl_sport_used = st.session_state.get("pl_sport_used", "NBA")

            # TheScore per-start pitcher lines (K/BB/W-L) -- MLB only,
            # matching this source's real coverage. Was captured every
            # 30 min but never shown anywhere until now.
            if _pl_sport_used == "MLB":
                try:
                    _ts_starts = fetch_thescore_pitcher_starts(pl_name_d)
                except Exception:
                    _ts_starts = []
                if _ts_starts:
                    with st.expander(f"⚾ TheScore: last {min(len(_ts_starts), 10)} starts", expanded=False):
                        for _ts_s in _ts_starts[:10]:
                            st.caption(
                                f"{_ts_s['date'][:16]} vs {_ts_s.get('opponent','?')} — "
                                f"K: {_ts_s.get('strikeouts','?')}  BB: {_ts_s.get('walks','?')}  "
                                f"W-L: {_ts_s.get('wins',0)}-{_ts_s.get('losses',0)}"
                            )

            # GamblingForecast batter-vs-this-pitcher matchup history --
            # MLB only, matching this source's real coverage.
            if _pl_sport_used == "MLB":
                try:
                    _gf_matchup = fetch_gamblingforecast_matchup(pl_name_d)
                except Exception:
                    _gf_matchup = {}
                if _gf_matchup:
                    _gf_opp = _gf_matchup.get("opp", "?")
                    _gf_pitcher = _gf_matchup.get("pitcher", "?")
                    with st.expander(f"🎯 vs {_gf_pitcher} history ({_gf_opp})", expanded=False):
                        st.caption(
                            f"AB: {_gf_matchup.get('ab','?')}  H: {_gf_matchup.get('h','?')}  "
                            f"HR: {_gf_matchup.get('hr','?')}  RBI: {_gf_matchup.get('rbi','?')}  "
                            f"BB: {_gf_matchup.get('bb','?')}  K: {_gf_matchup.get('k','?')}"
                        )
                        st.caption(
                            f"AVG: {_gf_matchup.get('avg','?')}  OBP: {_gf_matchup.get('obp','?')}  "
                            f"SLG: {_gf_matchup.get('slg','?')}  OPS: {_gf_matchup.get('ops','?')}"
                        )

            # theoddsgap DFS Market Edge -- PrizePicks/Underdog/DK Pick6/Betr
            # pick'em line graded against the real sportsbook market line for
            # this exact player, if one exists. Not sport-restricted like the
            # MLB-only sources above.
            try:
                _og_all_players = fetch_theoddsgap_edges_from_gist()
                _og_pl_target = normalize_name(pl_name_d)
                _og_pl_match = next((e for e in _og_all_players if normalize_name(e.get("player","")) == _og_pl_target), None)
            except Exception:
                _og_pl_match = None
            if _og_pl_match:
                _og_pl_gap = (_og_pl_match.get("market_line", 0) or 0) - (_og_pl_match.get("app_line", 0) or 0)
                _og_pl_gob = "🎯 Goblin — " if _og_pl_match.get("kind") == "goblin" else ""
                with st.expander(f"🔭 theoddsgap Market Edge ({_og_pl_match.get('app','')})", expanded=False):
                    st.caption(
                        f"{_og_pl_gob}{_og_pl_match.get('market_label','')}: app set {_og_pl_match.get('app_line','')} "
                        f"{_og_pl_match.get('side','')}, market fair value {_og_pl_match.get('market_line','')} "
                        f"(gap {_og_pl_gap:+.1f}) · estimated {_og_pl_match.get('win_pct','?')}% win"
                    )
                    st.caption(f"{_og_pl_match.get('event','')} · {_og_pl_match.get('commence_time','')[:16]}")

            if sport == "NFL":
                try:
                    _ll_blurbs = fetch_leaguelogs_blurbs()
                    _ll_target_last = normalize_name(pl_name_d.split()[-1]) if pl_name_d else ""
                    _ll_match = next((b for b in _ll_blurbs if normalize_name(b.get("lastName","")) == _ll_target_last and normalize_name(b.get("firstName","")) in normalize_name(pl_name_d)), None)
                    if _ll_match and _ll_match.get("blurb"):
                        st.warning(f"⚠️ {pl_name_d} — Status Update\n\n{_ll_match['blurb']}")
                        st.caption("Powered by LeagueLogs API")
                except Exception:
                    pass

            if sport == "MLB":
                try:
                    _pf_form = fetch_pitcher_recent_form(pl_name_d)
                    if _pf_form:
                        _pf_icon = {"improving": "🟢", "regressing": "🔴", "stable": "⚪"}[_pf_form["trend"]]
                        st.caption(f"{_pf_icon} L5 ERA {_pf_form['l5_era']} vs Season ERA {_pf_form['season_era']} ({_pf_form['n_starts']} starts) — {_pf_form['trend']}")
                except Exception:
                    pass

            # BettingPros hit-rate/streak trend data -- covers all 5
            # sports this source has (MLB/NBA/NHL/WNBA/NFL).
            if _pl_sport_used in ("MLB", "NBA", "NHL", "WNBA", "NFL"):
                try:
                    _bp_props = fetch_bettingpros_hitrate(pl_name_d, _pl_sport_used)
                except Exception:
                    _bp_props = []
                if _bp_props:
                    _bp_player_info = (_bp_props[0].get("participant", {}) or {}).get("player", {}) or {}
                    _bp_headshot = _bp_player_info.get("image")
                    _bp_pos = _bp_player_info.get("position", "")
                    _bp_team = _bp_player_info.get("team", "")
                    if _bp_headshot:
                        _bp_col1, _bp_col2 = st.columns([1, 5])
                        with _bp_col1:
                            st.image(_bp_headshot, width=60)
                        with _bp_col2:
                            st.caption(f"{_bp_pos} — {_bp_team}" if _bp_pos or _bp_team else "")
                for _bp in _bp_props[:3]:
                    _bp_perf = _bp.get("performance", {})
                    _bp_over = _bp.get("over", {}) or {}
                    _bp_under = _bp.get("under", {}) or {}
                    _bp_proj = _bp.get("projection", {}) or {}
                    _bp_extra = _bp.get("extra", {}) or {}
                    _bp_stat = _bp.get("links", {}).get("odds", "").rstrip("/").rsplit("/", 1)[-1].replace("-", " ").title()
                    _bp_streak = _bp_perf.get("streak", 0)
                    _bp_streak_type = _bp_perf.get("streak_type", "")
                    with st.expander(f"📊 {_bp_stat or 'Prop'} — BettingPros", expanded=False):
                        # Line/odds/EV/rating -- best available side and consensus
                        _bp_rec = str(_bp_proj.get("recommended_side", "")).upper()
                        _bp_side_block = _bp_over if _bp_rec == "OVER" else _bp_under if _bp_rec == "UNDER" else None
                        if _bp_side_block:
                            _bp_stars = "⭐" * int(_bp_side_block.get("bet_rating", 0) or 0)
                            st.markdown(
                                f"**{_bp_rec}** best line **{_bp_side_block.get('line','?')}** "
                                f"({_bp_side_block.get('odds','?'):+} odds) {_bp_stars}"
                                if isinstance(_bp_side_block.get("odds"), (int, float)) else
                                f"**{_bp_rec}** best line **{_bp_side_block.get('line','?')}** {_bp_stars}"
                            )
                            _bp_ev = _bp_side_block.get("expected_value")
                            _bp_prob = _bp_side_block.get("probability")
                            if _bp_ev is not None:
                                st.caption(f"BettingPros model: {_bp_prob:.1%} win probability, {_bp_ev:+.1%} EV" if _bp_prob is not None else f"EV: {_bp_ev:+.1%}")
                        _bp_cons_line = _bp_over.get("consensus_line")
                        if _bp_cons_line is not None:
                            st.caption(f"Consensus line across books: {_bp_cons_line}")
                        if _bp_proj.get("value") is not None:
                            st.caption(f"BettingPros projection: {_bp_proj['value']} (diff vs line: {_bp_proj.get('diff', 0):+})")
                        # MLB-specific context
                        if _bp_extra.get("opposing_pitcher"):
                            st.caption(f"Opposing pitcher: {_bp_extra['opposing_pitcher']}")
                        if "in_lineup" in _bp_extra:
                            st.caption(f"Lineup status: {'✅ Confirmed' if _bp_extra['in_lineup'] else '⚠️ Not yet confirmed'}")
                        _bp_opp_rank = _bp_extra.get("opposition_rank")
                        if _bp_opp_rank and _bp_opp_rank.get("rank"):
                            st.caption(f"Opponent ranks #{_bp_opp_rank['rank']} vs this stat")
                        st.markdown("---")
                        if _bp_streak and _bp_streak_type:
                            st.caption(f"Current streak: {_bp_streak} games {_bp_streak_type}")
                        for window in ("last_5", "last_10", "last_20", "season"):
                            w = _bp_perf.get(window, {})
                            o, u, psh = w.get("over", 0), w.get("under", 0), w.get("push", 0)
                            total = o + u + psh
                            if total:
                                label = window.replace("last_", "Last ").replace("season", "Season").title()
                                st.caption(f"{label}: {o}-{u}" + (f"-{psh}" if psh else "") + f" O/U ({total} games)")

            # Bobby's Bets picks -- confirmed live 2026-08-01, no auth/CF.
            # Matches by exact player_name string against the real API
            # response (their own naming, not necessarily normalized the
            # same way as our board).
            try:
                _bb_picks = st.session_state.get("bobbys_bets_picks", [])
                _bb_matches = [p for p in _bb_picks
                               if normalize_name(str(p.get("player_name",""))) == normalize_name(pl_name_d)]
            except Exception:
                _bb_matches = []
            for _bb in _bb_matches[:3]:
                _bb_stat = str(_bb.get("stat_category","")).upper()
                _bb_label = _bb.get("label","")
                _bb_line = _bb.get("line","?")
                with st.expander(f"🎯 {_bb_stat} {_bb_label} {_bb_line} — Bobby's Bets", expanded=False):
                    _bb_odds = _bb.get("odds_american")
                    if _bb_odds is not None:
                        st.markdown(f"**{_bb_label} {_bb_line}** ({_bb_odds:+d} odds)" if isinstance(_bb_odds, int) else f"**{_bb_label} {_bb_line}** ({_bb_odds} odds)")
                    _bb_streak = _bb.get("current_streak")
                    if _bb_streak:
                        st.caption(f"Current streak: {_bb_streak} games {_bb_label.lower()}")
                    for hr_key, hr_label in (("hit_rate_l5","Last 5"), ("hit_rate_l10","Last 10"),
                                              ("hit_rate_l20","Last 20"), ("hit_rate_all","Season")):
                        v = _bb.get(hr_key)
                        if v is not None:
                            st.caption(f"{hr_label} hit rate: {v}%")
                    if _bb.get("hit_rate_home") is not None or _bb.get("hit_rate_away") is not None:
                        st.caption(f"Home: {_bb.get('hit_rate_home','?')}% · Away: {_bb.get('hit_rate_away','?')}%")

            # coverage fetch_numberfire_direct actually has. Matches by
            # normalized name against the raw scraped rows.
            if _pl_sport_used in ("NFL", "NBA"):
                try:
                    _nf_data = st.session_state.get(f"numberfire_data_{_pl_sport_used}", {}) or {}
                    _nf_players = _nf_data.get("players", [])
                    _nf_match = None
                    _pl_name_norm = normalize_name(pl_name_d)
                    for _nf_p in _nf_players:
                        if normalize_name(_nf_p.get("name", "")) == _pl_name_norm:
                            _nf_match = _nf_p
                            break
                    if _nf_match:
                        st.caption(f"📊 NumberFire: {_nf_match.get('raw_row', '')[:200]}")
                except Exception:
                    pass

            stat_key_map = {
                # NBA / WNBA
                "Points": "pts", "Rebounds": "reb", "Assists": "ast",
                "3-PT Made": "fg3m", "Steals": "stl",
                "Blocked Shots": "blk", "Turnovers": "turnover",
                "Pts+Reb+Ast": "pra",
                # MLB
                "Hits": "H", "Home Runs": "HR", "RBI": "RBI",
                "Runs": "R", "Strikeouts (Pitcher)": "K",
                "Walks": "BB", "Total Bases": "TB", "Stolen Bases": "SB",
                # NHL
                "Goals": "G", "Assists": "A",
                "Shots on Goal": "SOG", "Saves": "SV",
                "Goals+Assists": "pra",   # reuse pra slot for G+A
                # NFL
                "Pass Yards": "pass_yds", "Rush Yards": "rush_yds",
                "Receiving Yards": "rec_yds", "Touchdowns": "td",
                "Receptions": "rec", "Pass Completions": "cmp",
            }
            sk = stat_key_map.get(pl_stat, "pts")
            # For Goals+Assists (NHL), compute from G+A
            _use_ga_sum = (pl_stat == "Goals+Assists")
            if _use_ga_sum:
                vals = [float(g.get("G",0) or 0) + float(g.get("A",0) or 0) for g in logs]
            else:
                vals = [g.get(sk, 0) or 0 for g in logs]
            avg = sum(vals) / len(vals) if vals else 0

            # Hit rates
            # Auto-suggest line as avg if none entered
            _effective_line = pl_line if pl_line > 0 else round(avg * 2) / 2
            hits_l5 = sum(1 for v in vals[:5] if v > _effective_line) if len(vals) >= 5 else None
            hits_l10 = sum(1 for v in vals[:10] if v > _effective_line) if len(vals) >= 10 else None
            hits_l15 = sum(1 for v in vals[:15] if v > _effective_line) if len(vals) >= 15 else None
            if pl_line == 0 and avg > 0:
                st.info(f"💡 No line entered — using avg {_effective_line:.1f} as reference line. Enter a line above for exact hit rates.")

            # H2H
            h2h_rate, h2h_n, h2h_str = compute_h2h_hit_rate(logs, pl_opp, pl_stat, pl_line) if pl_opp else (None, 0, "")

            # Home/Away splits
            splits = compute_home_away_splits(logs, pl_stat, pl_line) if pl_line > 0 else None

            # Header stats -- command-card style, matching Summary/Full
            # Board's visual language instead of plain st.metric widgets.
            # Same real values as before, just consistent styling.
            st.markdown(f"### {pl_name_d} — {pl_stat}")
            _pl_cards = [("Season Avg", f"{avg:.1f}", None)]
            if pl_line > 0:
                _diff = avg - pl_line
                _pl_cards.append(("vs Line", f"{_diff:+.1f}", "#22c55e" if _diff >= 0 else "#e04040"))
            if hits_l5 is not None:
                _pl_cards.append(("L5 Hit Rate", f"{hits_l5}/5 ({hits_l5/5:.0%})", "#22c55e" if hits_l5/5 >= 0.6 else None))
            if hits_l10 is not None:
                _pl_cards.append(("L10 Hit Rate", f"{hits_l10}/10 ({hits_l10/10:.0%})", "#22c55e" if hits_l10/10 >= 0.6 else None))
            if h2h_rate is not None:
                _pl_cards.append((f"H2H vs {pl_opp}", f"{h2h_str} ({h2h_rate:.0%})", "#22c55e" if h2h_rate >= 0.6 else None))
            _pl_cards_html = "".join(
                f'<div class="command-card" style="flex:1;min-width:120px;padding:14px 16px;text-align:center;">'
                f'<div class="command-label">{label}</div>'
                f'<div class="command-value" style="font-size:1.4rem;{f"color:{color};" if color else ""}">{value}</div>'
                f'</div>'
                for label, value, color in _pl_cards
            )
            st.markdown(f'<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:14px;">{_pl_cards_html}</div>', unsafe_allow_html=True)

            # Always show last N game log
            st.markdown(f"#### 📋 Last {pl_games} Games")
            if logs:
                log_html = '<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:1.0rem;">'
                log_html += '<tr style="background:var(--bc-bg-card);color:var(--bc-dim);">'
                log_html += '<th style="padding:4px 8px;text-align:left;">Date</th><th style="padding:4px 8px;">Opp</th><th style="padding:4px 8px;">H/A</th>'
                log_html += f'<th style="padding:4px 8px;">{pl_stat}</th>'
                if pl_line > 0:
                    log_html += '<th style="padding:4px 8px;">Result</th>'
                log_html += '</tr>'
                for i, g in enumerate(logs[:pl_games]):
                    v = g.get(sk, 0) or 0
                    if sk == "pra" and not _use_ga_sum:
                        v = float(g.get("pts",0) or 0) + float(g.get("reb",0) or 0) + float(g.get("ast",0) or 0)
                    elif _use_ga_sum:
                        v = float(g.get("G",0) or 0) + float(g.get("A",0) or 0)
                    hit = v > _effective_line
                    row_bg = "#0a0e14" if i % 2 == 0 else "#080c12"
                    val_color = "#22c55e" if hit else "#e04040"
                    date_str = g.get("game",{}).get("date","")[:10] if isinstance(g.get("game"),dict) else ""
                    home_team = g.get("game",{}).get("home_team",{}).get("abbreviation","") if isinstance(g.get("game"),dict) else ""
                    visitor_team = g.get("game",{}).get("visitor_team",{}).get("abbreviation","") if isinstance(g.get("game"),dict) else ""
                    team = g.get("team",{}).get("abbreviation","") if isinstance(g.get("team"),dict) else ""
                    opp = home_team if team == visitor_team else visitor_team
                    ha = "H" if team == home_team else "A"
                    log_html += f'<tr style="background:{row_bg};">'
                    log_html += f'<td style="padding:3px 8px;color:var(--bc-muted);">{date_str}</td>'
                    log_html += f'<td style="padding:3px 8px;color:var(--bc-muted);text-align:center;">{opp}</td>'
                    log_html += f'<td style="padding:3px 8px;color:var(--bc-dim);text-align:center;">{ha}</td>'
                    log_html += f'<td style="padding:3px 8px;color:{val_color};font-weight:600;text-align:center;">{v}</td>'
                    if pl_line > 0:
                        log_html += f'<td style="padding:3px 8px;color:{val_color};text-align:center;">{"✅ O" if hit else "❌ U"} {_effective_line}</td>'
                    log_html += '</tr>'
                log_html += '</table></div>'
                st.markdown(log_html, unsafe_allow_html=True)

            # Home/Away splits
            if splits:
                st.markdown("#### 🏠 Home / Away Splits")
                _pl_split_cards = [
                    ("Home Avg", f"{splits['home_avg']}", None),
                    ("Away Avg", f"{splits['away_avg']}", None),
                ]
                if pl_line > 0:
                    _pl_split_cards.append(("Home Hit %", f"{splits['home_hit_rate']:.0%} ({splits['home_games']}g)",
                                             "#22c55e" if splits['home_hit_rate'] >= 0.6 else None))
                    _pl_split_cards.append(("Away Hit %", f"{splits['away_hit_rate']:.0%} ({splits['away_games']}g)",
                                             "#22c55e" if splits['away_hit_rate'] >= 0.6 else None))
                _pl_split_html = "".join(
                    f'<div class="command-card" style="flex:1;min-width:120px;padding:14px 16px;text-align:center;">'
                    f'<div class="command-label">{label}</div>'
                    f'<div class="command-value" style="font-size:1.4rem;{f"color:{color};" if color else ""}">{value}</div>'
                    f'</div>'
                    for label, value, color in _pl_split_cards
                )
                st.markdown(f'<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:14px;">{_pl_split_html}</div>', unsafe_allow_html=True)

            # Game log chart
            st.markdown("#### 📊 Last Games")
            if vals:
                # Visual bar chart using HTML
                max_val = max(vals) if vals else 1
                bars_html = '<div style="display:flex;gap:4px;align-items:flex-end;height:120px;padding:8px;background:var(--bc-bg-card);border-radius:8px;">'
                for i, v in enumerate(vals):
                    height_pct = int((v / max_val) * 100) if max_val > 0 else 0
                    over = v > pl_line if pl_line > 0 else True
                    color = "#22c55e" if over else "#e04040"
                    log = logs[i]
                    tip = f"{log['date']} {'HOME' if log['home'] else 'AWAY'}: {v}"
                    bars_html += f'<div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:2px;">'
                    bars_html += f'<div style="font-size:8px;color:#9aa8b8">{int(v)}</div>'
                    bars_html += f'<div style="width:100%;height:{height_pct}%;background:{color};border-radius:3px 3px 0 0;min-height:4px;" title="{tip}"></div>'
                    bars_html += f'<div style="font-size:7px;color:var(--bc-dim);transform:rotate(-45deg);margin-top:2px">{log["date"][5:]}</div>'
                    bars_html += '</div>'
                if pl_line > 0:
                    bars_html += f'</div>'
                    st.markdown(bars_html, unsafe_allow_html=True)
                    st.caption(f"🟢 = OVER {pl_line} | 🔴 = UNDER {pl_line}")
                else:
                    bars_html += '</div>'
                    st.markdown(bars_html, unsafe_allow_html=True)

            # Game log table
            st.markdown("#### 📋 Game Log")
            log_data = []
            for g in logs:
                log_data.append({
                    "Date": g["date"],
                    "H/A": "HOME" if g["home"] else "AWAY",
                    "PTS": g.get("pts",0),
                    "REB": g.get("reb",0),
                    "AST": g.get("ast",0),
                    "STL": g.get("stl",0),
                    "BLK": g.get("blk",0),
                    "3PM": g.get("fg3m",0),
                    "PRA": g.get("pra",0),
                    "MIN": g.get("min","—"),
                    f"vs {pl_line}": "✅" if (g.get(sk,0) or 0) > pl_line else "❌" if pl_line > 0 else "—"
                })
            if log_data:
# DUPLICATE REMOVED: import pandas as pd
                log_df = pd.DataFrame(log_data)
                st.markdown(_bc_df_html(log_df), unsafe_allow_html=True)

            # Find this player on today's board
            board = st.session_state.get("board_data", [])
            if board:
                norm_pl = normalize_name(pl_name_d)
                board_props = [p for p in board if normalize_name(p.get("Player","")) == norm_pl]
                if board_props:
                    st.markdown("#### 🔒 On Today's Board")
                    for bp in board_props:
                        tier_color = TIER_COLORS.get(bp.get("Tier",""), "#7a8a9a")
                        _pin_span = ('<span style="color:#22c55e;margin-left:12px">📌 Pinnacle confirms</span>' if bp.get("PinnacleConfirms") else "")
                        st.markdown(
                            f'<div style="background:var(--bc-bg-card);border:1px solid var(--bc-border);border-left:4px solid {tier_color};'
                            f'border-radius:8px;padding:10px 14px;margin:4px 0;">'
                            f'<span style="background:{tier_color};color:#000;font-size:9px;font-weight:700;padding:2px 7px;border-radius:8px;margin-right:8px">{bp.get("Tier","")}</span>'
                            f'<span style="color:var(--bc-text);font-weight:600">{bp.get("Side","")} {bp.get("Line","")} {bp.get("Prop","")}</span>'
                            f'<span style="color:#e8a020;margin-left:12px">Edge: {bp.get("EdgePct","")}</span>'
                            f'{_pin_span}'
                            f'</div>',
                            unsafe_allow_html=True
                        )

            # ── LineStar Projection (2026-07) ─────────────────────────────
            # GetSalariesV5 (Ceil/Floor/Conf/wOBA/ISO/wRC+) + GetPropBets
            # (cross-book lines), both harvested hourly server-side via
            # linestar_refresh.yml -- no browser/session needed. Silent no-op
            # if the sport isn't one LineStar covers today or the player
            # isn't found (e.g. not rostered / no salary today), rather than
            # showing an empty/broken section.
            #
            # Display-only, per 2026-07 scope decision: this data is not yet
            # wired into edge/Kelly calculation. LOJ hit-rate and the other
            # new fields need a backtest against BetCouncil's own outcome
            # history before they're trusted to influence recommendation
            # sizing, same standard as SEM/H2H Signal 7.
            _ls_sal_data, _ = fetch_linestar_salaries_from_gist(_pl_sport_used)
            _ls_row = get_linestar_player_salary_row(_ls_sal_data, pl_name_d) if _ls_sal_data else None
            _ls_props_data, _ = fetch_linestar_props_from_gist(_pl_sport_used)
            _ls_book_lines = get_linestar_prop_lines(_ls_props_data, pl_name_d) if _ls_props_data else {}
            _ls_chart = get_linestar_player_chartdata(_ls_props_data, pl_name_d) if _ls_props_data else None

            if _ls_row or _ls_book_lines:
                st.markdown("#### 🎯 LineStar Projection")
                st.caption("Display only — not yet a model input. Cross-book snapshot, hourly.")
                if _ls_row:
                    ls_cols = st.columns(5)
                    ls_cols[0].metric("Salary", f"${_ls_row['salary']:,}" if _ls_row.get("salary") else "—")
                    ls_cols[1].metric("Projection", _ls_row.get("proj", "—"))
                    ls_cols[2].metric("Ceiling", _ls_row.get("ceil", "—"))
                    ls_cols[3].metric("Floor", _ls_row.get("floor", "—"))
                    _conf = _ls_row.get("conf")
                    ls_cols[4].metric("Confidence", f"{_conf}%" if _conf is not None else "—")

                    _badge_bits = []
                    if _ls_row.get("stars") is not None:
                        _badge_bits.append(f"{'⭐' * int(_ls_row['stars'])} ({_ls_row['stars']}/5)")
                    if _ls_row.get("ppg") is not None:
                        _badge_bits.append(f"PPG: {_ls_row['ppg']}")
                    if _ls_row.get("opp_rank") is not None:
                        _badge_bits.append(f"Opp Rank: {_ls_row['opp_rank']}")
                    if _ls_row.get("alert_score"):
                        _badge_bits.append(f"⚠️ Alert Score: {_ls_row['alert_score']}")
                    if _badge_bits:
                        st.caption(" · ".join(_badge_bits))
                    if _ls_row.get("notes"):
                        st.caption(f"📋 {_ls_row['notes']}")

                    _sections = _ls_row.get("matchup_sections")
                    if _sections:
                        for _sec_name, _splits in _sections.items():
                            st.caption(
                                f"**{_sec_name}**: "
                                + " · ".join(f"{k} {v}" for k, v in _splits.items() if v is not None)
                            )

                if _ls_book_lines:
                    _ls_rows = []
                    for _book, _stats in _ls_book_lines.items():
                        for _stat, _sv in _stats.items():
                            _ls_rows.append({
                                "Book": _book, "Stat": _stat, "Line": _sv.get("line"),
                                "Over": _sv.get("over_odds"), "Under": _sv.get("under_odds"),
                                "LS Proj": _sv.get("ls_proj"),
                                "Last 10 (O/U)": _sv.get("loj_badge") or "—",
                            })
                    if _ls_rows:
                        st.markdown("###### Cross-book lines (LineStar)")
                        st.markdown(_bc_df_html(pd.DataFrame(_ls_rows)), unsafe_allow_html=True)

                if _ls_chart:
                    st.caption(f"📈 Recent game log (LineStar): {_ls_chart}")

            # ── Situational Usage (2026-07) ─────────────────────────────
            # Free equivalent of a paid situational-stats tool (Rotobot-
            # style): NFL red-zone/trailing-game usage from nflverse's
            # public play-by-play, NBA trailing-game usage from
            # stats.nba.com's own clutch/AheadBehind split.
            # Display-only, same standard as LineStar above — not wired
            # into edge/Kelly until backtested against BetCouncil's own
            # outcome history.
            _pl_team_for_situational = board_props[0].get("Team", "") if board else ""
            if _pl_sport_used == "NFL":
                try:
                    from nfl_features import get_player_situational_splits
                    _situational = get_player_situational_splits(pl_name_d, date.today().year)
                except Exception:
                    _situational = {}
                if _situational:
                    st.markdown("#### 🎯 Situational Usage (Red Zone / Trailing)")
                    st.caption("Display only — not yet a model input. Source: nflverse public play-by-play.")
                    sit_cols = st.columns(4)
                    sit_cols[0].metric("Red Zone Touches", _situational.get("red_zone_carries", 0) + _situational.get("red_zone_targets", 0))
                    sit_cols[1].metric("Red Zone Share", f"{_situational.get('red_zone_share', 0):.1%}")
                    sit_cols[2].metric("Trailing Touches", _situational.get("trailing_carries", 0) + _situational.get("trailing_targets", 0))
                    sit_cols[3].metric("Trailing Share", f"{_situational.get('trailing_share', 0):.1%}")
            elif _pl_sport_used == "NBA":
                try:
                    _nba_trailing = fetch_nba_trailing_splits(pl_name_d)
                except Exception:
                    _nba_trailing = {}
                if _nba_trailing:
                    st.markdown("#### 🎯 Situational Usage (Trailing by 5+)")
                    st.caption("Display only — not yet a model input. Source: stats.nba.com (AheadBehind split).")
                    sit_cols = st.columns(4)
                    sit_cols[0].metric("GP (trailing)", _nba_trailing.get("gp", "—"))
                    sit_cols[1].metric("PTS", _nba_trailing.get("pts", "—"))
                    sit_cols[2].metric("USG%", _nba_trailing.get("usg_pct", "—"))
                    sit_cols[3].metric("FGA", _nba_trailing.get("fga", "—"))

            # ── FavoredProps: hit rates + multi-book odds for this player ──
            # Public API (/api/dfs, /api/sportsbook), no login. Same
            # display-only standard as the panels above.
            _fp_player_rows = []
            for _fp_kind in ("sportsbook", "dfs"):
                try:
                    _fp_rows_all = fetch_favoredprops_from_gist(_fp_kind, _pl_sport_used)
                except Exception:
                    _fp_rows_all = []
                for _fpr in _fp_rows_all:
                    if str(_fpr.get("player", "")).lower().strip() == pl_name_d.lower().strip():
                        _fp_player_rows.append({**_fpr, "kind": _fp_kind})
            if _fp_player_rows:
                st.markdown("#### 📊 FavoredProps — Hit Rates & Multi-Book Odds")
                st.caption("Display only — not yet a model input. Source: favoredprops.com public API.")
                _fp_table_rows = []
                for _fpr in _fp_player_rows[:12]:
                    _fp_table_rows.append({
                        "Kind": "DFS (PP/UD)" if _fpr["kind"] == "dfs" else "Sportsbook",
                        "Stat": _fpr.get("stat_type", ""), "Bet": _fpr.get("bet", ""),
                        "Line": _fpr.get("line", ""), "Avg Odds": _fpr.get("avg_odds", ""),
                        "Books": _fpr.get("n_books", ""),
                        "L5": _fpr.get("l5_hit_rate", ""), "L10": _fpr.get("l10_hit_rate", ""),
                        "Season": _fpr.get("szn_hit_rate", ""), "H2H": _fpr.get("h2h_hit_rate", ""),
                    })
                st.markdown(_bc_df_html(pd.DataFrame(_fp_table_rows)), unsafe_allow_html=True)

            # ── DraftEdge: opposing pitcher matchup, weather, DFS salary,
            # hit rates for this player (MLB is richest — NBA/NFL/NHL
            # also covered when in-season). Public SSR JSON, no auth.
            # Display only — BetCouncil already has its own weather and
            # park-factor pipelines, so this is cross-check context,
            # not a new signal.
            try:
                _de_row = get_draftedge_player(pl_name_d, _pl_sport_used)
            except Exception:
                _de_row = {}
            if _de_row:
                st.markdown("#### 🌤️ DraftEdge — Matchup & Weather Context")
                st.caption("Display only — not a model input (you already have live weather/park-factor pipelines). Source: draftedge.com public API.")
                _de_cols = st.columns(4)
                _de_pitcher = _de_row.get("OppPitcher_PitcherName")
                if _de_pitcher:
                    _de_cols[0].metric("Opp Pitcher", _de_pitcher)
                    _de_cols[1].metric("ERA / WHIP", f'{_de_row.get("OppPitcher_ERA","—")} / {_de_row.get("OppPitcher_WHIP","—")}')
                    _de_cols[2].metric("K/9", _de_row.get("OppPitcher_K9", "—"))
                else:
                    _de_cols[0].metric("DFS Salary", _de_row.get("DFS_Salary", "—"))
                    _de_cols[1].metric("Position", _de_row.get("Pos", _de_row.get("position", "—")))
                    _de_cols[2].metric("Team", _de_row.get("Team Abbr.", _de_row.get("team", "—")))
                _de_weather = _de_row.get("Weather_Desc")
                if _de_weather:
                    _de_cols[3].metric("Weather", f'{_de_weather}, {_de_row.get("Temperature","—")}°F')
                elif _de_row.get("Injury_Designation"):
                    _de_cols[3].metric("Injury", _de_row.get("Injury_Designation"))

                _de_stat_sections = {
                    "Hits": _de_row.get("HitsSection", {}), "HR": _de_row.get("HRSection", {}),
                    "RBI": _de_row.get("RBISection", {}), "TB": _de_row.get("TBSection", {}),
                    "SB": _de_row.get("SBSection", {}),
                }
                _de_stat_rows = []
                for _stat_name, _sec in _de_stat_sections.items():
                    if isinstance(_sec, dict) and _sec.get("Proj") is not None:
                        _de_stat_rows.append({
                            "Stat": _stat_name, "Proj": _sec.get("Proj", ""),
                            "L5 Over%": _sec.get("OverL5", ""), "L15 Over%": _sec.get("OverL15", ""),
                            "L30 Over%": _sec.get("OverL30", ""),
                        })
                if _de_stat_rows:
                    st.markdown(_bc_df_html(pd.DataFrame(_de_stat_rows)), unsafe_allow_html=True)

            # ── RotoGrinders: lineup confirmation + DFS projected points ──
            # Public JSON, no login. Real prop-picks tools are fully
            # paywalled (checked, no free preview) -- this is just lineup
            # status + pfpts, same display-only standard as everything
            # else here.
            try:
                _rg_row = get_rotogrinders_player(pl_name_d, _pl_sport_used)
            except Exception:
                _rg_row = {}
            if _rg_row:
                st.markdown("#### 📋 RotoGrinders — Lineup & DFS Projection")
                st.caption("Display only — not a model input. Source: rotogrinders.com public lineups API.")
                _rg_cols = st.columns(4)
                _rg_status = "Confirmed" if _rg_row.get("status") == "C" else "Unconfirmed"
                _rg_cols[0].metric("Lineup Status", _rg_status)
                _rg_cols[1].metric("Batting Order", _rg_row.get("batting_order", "—"))
                _rg_cols[2].metric("DFS Salary", _rg_row.get("salary", "—"))
                _rg_cols[3].metric("Proj DFS Pts", _rg_row.get("pfpts", "—"))


with tabs[9]:
    st.markdown('<div class="bc-section-header">📝 Log A Bet</div>', unsafe_allow_html=True)

    st.caption("Log any bet placed outside of BetCouncil \u2014 from PrizePicks app, Bovada, MyBookie, or anywhere. Feeds into all tracking systems.")

    # ── UNIFIED RECENT ACTIVITY ────────────────────────────────────────
    # Every entry point (⚡ quick-track dialog on prop cards, Quick Single
    # Bet below, Bulk Entry, Screenshot/Text OCR) writes through the same
    # log_manual_bet() → st.session_state.history. This panel surfaces
    # that shared feed so all logging paths read as one connected system
    # instead of separate, disconnected tools.
    _recent_logs = [h for h in st.session_state.get("history", []) if h.get("manual_entry")]
    _recent_logs = sorted(_recent_logs, key=lambda h: h.get("timestamp",""), reverse=True)[:5]
    if _recent_logs:
        with st.expander(f"🕒 Recent Activity — last {len(_recent_logs)} logged (any entry point)", expanded=False):
            for _rl in _recent_logs:
                _rl_color = "#22c55e" if _rl.get("outcome") == "WIN" else ("#e04040" if _rl.get("outcome") == "LOSS" else "#8a9ab0")
                st.markdown(
                    f'<div style="display:flex;justify-content:space-between;align-items:center;'
                    f'padding:5px 10px;border-bottom:1px solid #1a2a3a;font-size:0.85rem;">'
                    f'<span style="color:#e6edf3;">{_rl.get("player","—")} {_rl.get("side","")} {_rl.get("line","")} '
                    f'<span style="color:var(--bc-dim);">{_rl.get("prop","")}</span></span>'
                    f'<span style="color:{_rl_color};font-weight:700;">{_rl.get("outcome","—")}</span>'
                    f'<span style="color:var(--bc-dim);font-size:0.75rem;">{_rl.get("source","")} · {_rl.get("timestamp","")}</span>'
                    f'</div>',
                    unsafe_allow_html=True
                )

    log_tab1, log_tab2 = st.tabs(["Screenshot / Text", "Bulk Entry"])
    with log_tab2:
        st.markdown("### 🎯 Log a PrizePicks Parlay as a Group")
        st.caption("Enter the parlay as a whole — stake is for the entire entry, not per player.")
        st.caption("💡 Already ran this slip through **🔍 Slip Analyzer**? Use its \"Log this slip as a placed bet\" button instead — it logs the same picks without re-typing them here.")
        _pk_col1, _pk_col2, _pk_col3 = st.columns(3)
        _pk_picks   = _pk_col1.selectbox("# of Picks", [2, 3, 4, 5, 6], index=0, key="pk_picks")
        _pk_stake   = _pk_col2.number_input("Stake ($)", min_value=1.0, step=5.0, value=10.0, key="pk_stake")
        _pk_outcome = _pk_col3.selectbox("Outcome", ["WIN", "LOSS", "PUSH", "PENDING"], key="pk_outcome")
        _pk_source  = st.selectbox("Platform", ["PrizePicks","Underdog","ParlayPlay","DraftKings","FanDuel","Other"], key="pk_source")
        _pk_sport   = st.selectbox("Sport", ["NBA","WNBA","MLB","NHL","NFL"], key="pk_sport")
        _pk_date    = st.date_input("Date", value=date.today(), key="pk_date")
        st.markdown("**Players in this parlay:**")
        _pk_players = []
        for _pki in range(int(_pk_picks)):
            _pkc1, _pkc2, _pkc3, _pkc4 = st.columns([2,1,1,1])
            _pk_pname = _pkc1.text_input(f"Player {_pki+1}", key=f"pk_player_{_pki}", placeholder="Player name")
            _pk_pstat = _pkc2.text_input(f"Stat", key=f"pk_stat_{_pki}", placeholder="Points")
            _pk_pline = _pkc3.number_input(f"Line", min_value=0.0, step=0.5, value=0.0, key=f"pk_line_{_pki}")
            _pk_pside = _pkc4.selectbox(f"Side", ["OVER","UNDER"], key=f"pk_side_{_pki}")
            if _pk_pname:
                _pk_players.append({
                    "player": _pk_pname, "prop": _pk_pstat or "Points",
                    "line": _pk_pline, "side": _pk_pside,
                })
        _mult = PRIZEPICKS_MULTIPLIERS.get(int(_pk_picks), 3.0)
        _payout = _pk_stake * _mult
        st.caption(f"Payout if win: ${_payout:.2f} ({_pk_picks}-pick {_mult}x)")
        if st.button("✅ Log This Parlay", type="primary", key="log_parlay_group_btn"):
            if _pk_players:
                _pk_date_str = datetime.combine(_pk_date, datetime.min.time()).strftime("%Y-%m-%d %H:%M")
                _logged_pk = 0
                _pk_snap_cache = load_from_gist("board_snapshots", None) or load_json_data(BOARD_SNAP_PATH, {})
                for _pki_leg, _pkl in enumerate(_pk_players):
                    try:
                        _bf_edge, _bf_tier, _bf_prob, _bf_signals = lookup_board_edge(
                            _pkl["player"], _pkl["prop"], _pk_sport, _pk_date_str,
                            _snapshots_cache=_pk_snap_cache
                        )
                        log_manual_bet(
                            player=_pkl["player"], prop=_pkl["prop"],
                            line=float(_pkl["line"]), side=_pkl["side"],
                            sport=_pk_sport, outcome=_pk_outcome,
                            # Real fix (2026-08-15): only the first leg carries
                            # the real stake -- was passing the FULL stake to
                            # every leg, so each leg's log_manual_bet call
                            # independently computed the full parlay profit,
                            # summing to pick_count x the real bankroll impact.
                            # Zero-wager legs still record player/prop/outcome
                            # for per-player tracking, just contribute nothing
                            # to bankroll totals.
                            wager=(_pk_stake if _pki_leg == 0 else 0.0),
                            pick_count=int(_pk_picks), bet_type="prop",
                            source=_pk_source, bet_date=_pk_date_str,
                            tier=_bf_tier, edge=_bf_edge, prob=_bf_prob, signals=_bf_signals,
                            defer_gist_flush=True,
                        )
                        _logged_pk += 1
                    except (ValueError, TypeError, ZeroDivisionError) as _e:
                        st.caption(f"⚠️ {_pkl['player']}: {str(_e)[:50]}")
                if _logged_pk:
                    _flush_batch_gist(st.session_state.get("gist_dirty", {}))
                    st.success(f"✅ Logged {_logged_pk}-pick parlay (${_pk_stake:.2f} stake) → {_pk_outcome}")
                    st.rerun()
            else:
                st.error("Enter at least one player.")
        st.markdown("---")
        st.markdown("### 📝 Quick Single Bet")
        st.caption("Log a single prop bet quickly.")
        _sb_c1, _sb_c2, _sb_c3 = st.columns(3)
        _sb_player  = _sb_c1.text_input("Player", key="sb_player")
        _sb_prop    = _sb_c1.text_input("Prop", value="Points", key="sb_prop")
        _sb_line    = _sb_c2.number_input("Line", min_value=0.0, step=0.5, key="sb_line")
        _sb_side    = _sb_c2.selectbox("Side", ["OVER","UNDER"], key="sb_side")
        _sb_outcome = _sb_c3.selectbox("Outcome", ["WIN","LOSS","PUSH","PENDING"], key="sb_outcome")
        _sb_stake   = _sb_c3.number_input("Stake ($)", min_value=1.0, step=5.0, value=10.0, key="sb_stake")
        _sb_sport   = st.selectbox("Sport", ["NBA","WNBA","MLB","NHL","NFL"], key="sb_sport")
        _sb_source  = st.selectbox("Book", ["PrizePicks","DraftKings","FanDuel","BetMGM","Caesars","Bovada","Other"], key="sb_source")
        if st.button("✅ Log Single Bet", key="log_single_btn", type="primary"):
            if _sb_player:
                _sb_date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                _bf_edge, _bf_tier, _bf_prob, _bf_signals = lookup_board_edge(_sb_player, _sb_prop, _sb_sport, _sb_date_str)
                log_manual_bet(
                    player=_sb_player, prop=_sb_prop, line=_sb_line,
                    side=_sb_side, sport=_sb_sport, outcome=_sb_outcome,
                    wager=_sb_stake, pick_count=1, bet_type="prop",
                    source=_sb_source, bet_date=_sb_date_str,
                    tier=_bf_tier, edge=_bf_edge, prob=_bf_prob, signals=_bf_signals,
                )
                st.success(f"✅ Logged {_sb_player} {_sb_side} {_sb_line} — {_sb_outcome}")
                st.rerun()
            else:
                st.error("Enter a player name.")
    with log_tab1:
        # Use a counter key so we can reset the uploader after submitting
        if "uploader_key" not in st.session_state:
            st.session_state["uploader_key"] = 0

        input_scr, input_txt = st.tabs(["📸 Upload Screenshot", "📋 Paste Slip Text"])

        with input_scr:
            st.caption("Upload one or more screenshots of your bet slip or result.")
            uploaded_imgs = st.file_uploader(
                "Upload bet screenshots (select multiple)",
                type=["jpg", "jpeg", "png", "heic", "webp"],
                key=f"bet_screenshot_{st.session_state['uploader_key']}",
                accept_multiple_files=True,
            )
            if uploaded_imgs:
                up_col1, up_col2 = st.columns([3, 1])
                up_col1.caption(f"{len(uploaded_imgs)} screenshot(s) loaded")
                if up_col2.button("🗑️ Clear", key="clear_uploader_btn"):
                    st.session_state["uploader_key"] += 1
                    st.session_state["parsed_bets"] = []
                    st.session_state["ocr_raw_text"] = ""
                    st.rerun()
                if st.button("🔍 Parse All Screenshots", key="parse_screenshot_btn"):
                    all_parsed = []
                    with st.spinner("Reading screenshots..."):
                        for img_file in uploaded_imgs:
                            img_bytes = img_file.read()
                            result = parse_bet_screenshot_ocr(img_bytes)
                            if result:
                                all_parsed.extend(result)
                    if all_parsed:
                        st.session_state["parsed_bets"] = all_parsed
                        st.success(f"✅ Found {len(all_parsed)} bet(s) across {len(uploaded_imgs)} screenshots")
                    else:
                        st.error("Could not read screenshots. Try the Paste Slip Text tab.")
                        _vd = st.session_state.get("vision_debug", {})
                        if _vd:
                            st.warning(f"Vision API: status={_vd.get('status_code','?')} | key={_vd.get('api_key_truncated','?')} | {str(_vd.get('response_body_truncated',''))[:200]}")
                        else:
                            st.warning("Vision API was never called. Check ANTHROPIC_API_KEY in Streamlit secrets.")
            with st.expander("🔍 OCR Debug — Raw Text Extracted"):
                raw_ocr = st.session_state.get("ocr_raw_text", "")
                if raw_ocr:
                    st.markdown(f'<pre style="color:#e0e0e0;background:#1a1a2e;padding:10px;border-radius:6px;font-size:12px;white-space:pre-wrap;word-break:break-word;">{raw_ocr[:1200]}</pre>', unsafe_allow_html=True)
                else:
                    st.caption("No OCR text yet — upload a screenshot above.")

        with input_txt:
            st.caption(
                "Paste any slip text — PrizePicks (single slip or full multi-day "
                "history), Bovada, or MyBookie. The format is auto-detected, no "
                "need to pick a source."
            )
            pasted_slip = st.text_area(
                "Paste slip text",
                height=220,
                placeholder="Paste your PrizePicks, Bovada, or MyBookie slip text here — single slip or your full history at once.",
                key="pasted_slip_text"
            )
            if st.button("🔍 Parse Text Slip", key="parse_text_slip_btn"):
                if pasted_slip and pasted_slip.strip():
                    _parsed = []
                    _detected_src = ""

                    # 1. PrizePicks bulk history export (multiple slips,
                    #    date headers, "N-Pick $X.XX" per slip).
                    _pp_hist_slips = parse_prizepicks_history_text(pasted_slip)
                    if _pp_hist_slips:
                        for _slip in _pp_hist_slips:
                            if _slip["outcome"] is None:
                                continue  # unresolved, skip
                            _slip_date_str = ""
                            try:
                                _slip_date_str = datetime.strptime(_slip["date"], "%b %d, %Y").strftime("%Y-%m-%d")
                            except (ValueError, TypeError):
                                pass
                            for _player in _slip["players"]:
                                _parsed.append({
                                    # The bulk-history export has no per-player
                                    # sport tag in the text (unlike a single
                                    # expanded slip), and slips often mix
                                    # sports (e.g. MLB + World Cup in one
                                    # parlay) -- marking MULTI rather than
                                    # guessing MLB, which would silently
                                    # miscategorize every non-MLB pick.
                                    "player": _player, "prop": "Combo", "line": 0.0,
                                    "side": "OVER", "sport": "MULTI",
                                    "outcome": _slip["outcome"], "wager": _slip["stake"],
                                    "pick_count": _slip["n_picks"], "bet_type": "prop",
                                    "source": "PrizePicks", "date": _slip_date_str,
                                })
                        _detected_src = "PrizePicks (bulk history)"

                    # 2. PrizePicks single expanded slip ("Show details" view).
                    if not _parsed:
                        _pp_single = _parse_pp_ocr_inline(pasted_slip)
                        if _pp_single:
                            _parsed = _pp_single
                            _detected_src = "PrizePicks"

                    # 3. Bovada.
                    if not _parsed:
                        _bov = parse_bovada_slip_text(pasted_slip)
                        if _bov:
                            _parsed = _bov
                            _detected_src = "Bovada"

                    # 4. MyBookie.
                    if not _parsed:
                        _mb = parse_mybookie_slip_text(pasted_slip)
                        if _mb:
                            _parsed = _mb
                            _detected_src = "MyBookie"

                    # 5. DraftKings.
                    if not _parsed:
                        _dk = parse_draftkings_slip_text(pasted_slip)
                        if _dk:
                            _parsed = _dk
                            _detected_src = "DraftKings"

                    # 6. FanDuel.
                    if not _parsed:
                        _fd = parse_fanduel_slip_text(pasted_slip)
                        if _fd:
                            _parsed = _fd
                            _detected_src = "FanDuel"

                    if _parsed:
                        st.session_state["parsed_bets"] = _parsed
                        st.success(f"✅ Found {len(_parsed)} bet(s) — detected as {_detected_src} — review below")
                        st.rerun()
                    else:
                        st.warning("Could not parse this slip. Check the format and try again, or use the screenshot upload instead.")
                else:
                    st.warning("Please paste your slip text first.")

        # ── Shared review + submit — shown below both input tabs ──────────────
        parsed_bets = st.session_state.get("parsed_bets", [])
        if parsed_bets:
            st.markdown("---")
            top_c1, top_c2 = st.columns([3, 1])
            top_c1.markdown("### ✅ Confirm Parsed Bets")
            if top_c2.button("❌ Clear All", key="clear_parsed_bets_top"):
                st.session_state["parsed_bets"] = []
                st.session_state["ocr_raw_text"] = ""
                st.rerun()
            for idx, bet in enumerate(parsed_bets):
                if bet.get("outcome") == "PENDING":
                    st.caption(f"⏳ {bet['player']} — PENDING, skipping")
                    continue
                with st.expander(f"{bet.get('player','?')} — {bet.get('outcome','?')}", expanded=True):
                    c1, c2, c3 = st.columns(3)
                    c1.write(f"**Prop:** {bet.get('prop','?')}")
                    c1.write(f"**Line:** {bet.get('line','?')}")
                    c2.write(f"**Side:** {bet.get('side','?')}")
                    c2.write(f"**Sport:** {bet.get('sport','?')}")
                    c3.write(f"**Outcome:** {bet.get('outcome','?')}")
                    c3.write(f"**Wager:** ${bet.get('wager',0):.2f}")
            col_confirm1, col_confirm2 = st.columns(2)
            parsed_date = col_confirm1.date_input("Date of these bets", value=date.today(), key="parsed_bet_date")
            if col_confirm1.button("✅ Submit All Parsed Bets", key="submit_parsed_bets"):
                submitted = 0
                _skipped_pending = 0
                _submit_errors = []
                _snap_cache = load_from_gist("board_snapshots", None) or load_json_data(BOARD_SNAP_PATH, {})
                for bet in parsed_bets:
                    if bet.get("outcome") not in ("WIN","LOSS","PUSH"):
                        _skipped_pending += 1
                        continue
                    bet_date_str = datetime.combine(parsed_date, datetime.min.time()).strftime("%Y-%m-%d %H:%M")
                    _raw_date = str(bet.get("date","")).strip()
                    if _raw_date:
                        for _fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%b %d, %Y", "%B %d, %Y"):
                            try:
                                bet_date_str = datetime.strptime(_raw_date, _fmt).strftime("%Y-%m-%d %H:%M")
                                break
                            except ValueError:
                                continue
                    try:
                        _bf_edge, _bf_tier, _bf_prob, _bf_signals = lookup_board_edge(
                            bet.get("player",""), bet.get("prop",""), bet.get("sport","NBA"), bet_date_str,
                            _snapshots_cache=_snap_cache
                        )
                        log_manual_bet(player=bet.get("player",""), prop=bet.get("prop",""), line=float(bet.get("line",0) or 0), side=bet.get("side","OVER"), sport=bet.get("sport") or "OTHER", outcome=bet.get("outcome","LOSS"), wager=float(bet.get("wager",0) or 0), pick_count=int(bet.get("pick_count",2) or 2), bet_type=bet.get("bet_type","prop"), source=bet.get("source","Screenshot Import"), bet_date=bet_date_str, tier=_bf_tier, edge=_bf_edge, prob=_bf_prob, signals=_bf_signals, defer_gist_flush=True)
                        submitted += 1
                    except (ValueError, TypeError) as _sbe:
                        _submit_errors.append(f"{bet.get('player','?')} ({bet.get('prop','?')}): {type(_sbe).__name__} — {_sbe}")
                        continue
                if submitted > 0:
                    _flush_batch_gist(st.session_state.get("gist_dirty", {}))
                    _skip_note = f" ({_skipped_pending} pending bet(s) skipped — outcome unknown)" if _skipped_pending else ""
                    st.success(f"✅ Submitted {submitted} bets{_skip_note} — Bankroll: ${st.session_state.get("bankroll", DEFAULT_BANKROLL):.2f}")
                    st.session_state["parsed_bets"] = []
                    st.session_state["uploader_key"] = st.session_state.get("uploader_key", 0) + 1
                    st.session_state["ocr_raw_text"] = ""
                    st.rerun()
                elif _skipped_pending:
                    st.warning(f"All {_skipped_pending} parsed bet(s) are still PENDING — nothing to log yet.")
                if _submit_errors:
                    st.error("⚠️ " + str(len(_submit_errors)) + " parsed bet(s) failed to log (bad line/wager value most likely from a misread screenshot) — fix these in the review section above and re-submit:\n\n" + "\n".join(f"- {e}" for e in _submit_errors))
            if col_confirm2.button("❌ Clear Parsed Bets", key="clear_parsed_bets"):
                st.session_state["parsed_bets"] = []
                st.session_state["ocr_raw_text"] = ""
                st.session_state["uploader_key"] = st.session_state.get("uploader_key", 0) + 1
                st.rerun()



with tabs[5]:
    st.markdown('<div class="bc-section-header">🛒 Line Shopping</div>', unsafe_allow_html=True)
    st.caption("Compares lines across all loaded sources — DFS platforms + sportsbooks. Load the board first to populate.")
    board_ls = st.session_state.get("board_data", [])
    if not board_ls:
        st.markdown(empty_state_html("🛒", "No board loaded yet",
                                      "Pick a sport and load the board to compare lines across books."),
                    unsafe_allow_html=True)
    else:
        # ── Build multi-source lookup from everything already in session (zero new API calls) ──
        ls_sources = {}

        def _ls_add(props_list, source_name):
            for p in (props_list or []):
                k = normalize_name(p.get("Player", ""))
                prop = p.get("Prop", "")
                line = p.get("Line")
                if not k or not prop or line is None:
                    continue
                ls_sources.setdefault(k, {}).setdefault(prop, {})[source_name] = float(line)

        _ls_add(st.session_state.get("ud_props_compare", []), "Underdog")
        # ── BettingPros (public props API, best line + cross-book consensus) ──
        _bp_ls_props, _bp_ls_consensus = [], []
        for _bp_lp in st.session_state.get("bettingpros_props", []):
            _bp_lp_player = (_bp_lp.get("participant", {}) or {}).get("player", {}) or {}
            _bp_lp_name = f"{_bp_lp_player.get('first_name','')} {_bp_lp_player.get('last_name','')}".strip()
            _bp_lp_stat = _bp_lp.get("links", {}).get("odds", "").rstrip("/").rsplit("/", 1)[-1].replace("-", " ").title()
            if not _bp_lp_name or not _bp_lp_stat:
                continue
            _bp_lp_proj = _bp_lp.get("projection", {}) or {}
            _bp_lp_side = "over" if str(_bp_lp_proj.get("recommended_side","")).lower() != "under" else "under"
            _bp_lp_line = _bp_lp.get(_bp_lp_side, {}).get("line")
            _bp_lp_cons = _bp_lp.get("over", {}).get("consensus_line")
            if _bp_lp_line is not None:
                _bp_ls_props.append({"Player": _bp_lp_name, "Prop": _bp_lp_stat, "Line": _bp_lp_line})
            if _bp_lp_cons is not None:
                _bp_ls_consensus.append({"Player": _bp_lp_name, "Prop": _bp_lp_stat, "Line": _bp_lp_cons})
        _ls_add(_bp_ls_props, "BettingPros (best)")
        _ls_add(_bp_ls_consensus, "BettingPros (consensus)")
        # ── Bobby's Bets best-prices (real cross-book comparison, confirmed live) ──
        _bb_ls_props = []
        for _bb_key, _bb_val in st.session_state.get("bobbys_bets_best_prices", {}).items():
            _bb_parts = _bb_key.split("|")
            if len(_bb_parts) != 4:
                continue
            _bb_player, _bb_stat, _bb_line, _bb_side = _bb_parts
            try:
                _bb_line_f = float(_bb_line)
            except (TypeError, ValueError):
                continue
            _bb_ls_props.append({"Player": _bb_player.title(), "Prop": f"{_bb_stat} ({_bb_side})", "Line": _bb_line_f})
        _ls_add(_bb_ls_props, "Bobby's Bets (best)")
        # ── Unabated (data.unabated.com, 15-min cron, no auth/WAF dependency) ──
        # Independent of the token-gated scrapers below — still fresh even
        # when Caesars/Bovada/DK Pick6 tokens have expired since last capture.
        _unab_ls_platform_label = {"prizepicks": "Unabated (PrizePicks)", "underdog": "Unabated (Underdog)", "pick6": "Unabated (Pick6)"}
        for _ul in (st.session_state.get(f"unabated_props_{st.session_state.get('last_sport', 'NBA')}", []) or []):
            _ul_plat = str(_ul.get("platform", "")).lower()
            _ul_label = _unab_ls_platform_label.get(_ul_plat)
            if not _ul_label or _ul.get("line") is None:
                continue
            _ls_add([{"Player": _ul.get("player_name", ""), "Prop": _ul.get("stat_type", ""),
                      "Line": _ul.get("line")}], _ul_label)
        # ── New book sources added today ────────────────────────────────────
        _ls_add(st.session_state.get("bovada_props", []), "Bovada")
        _ls_add(st.session_state.get("caesars_props", []), "Caesars")
        # BetOnline/BetMGM/Bovada game lines → convert to prop format for line shop
        for _bol in (st.session_state.get("betonline_offering", []) or []):
            if _bol.get("market","") == "Total":
                _ls_add([{"Player": _bol.get("game",""), "Prop": "Total",
                          "Line": str(_bol.get("selection","")).split()[-1],
                          "source": "BetOnline"}], "BetOnline")
        for _bmg in (st.session_state.get("betmgm_game_lines", []) or []):
            if "Total" in _bmg.get("market","") or "total" in _bmg.get("market","").lower():
                _ls_add([{"Player": _bmg.get("game",""), "Prop": "Total",
                          "Line": _bmg.get("odds",""), "source": "BetMGM"}], "BetMGM")
        for _ts in (st.session_state.get("thescore_game_lines", []) or []):
            _ts_market = _ts.get("market", _ts.get("Prop", ""))
            _ts_game   = _ts.get("game",   _ts.get("Matchup", ""))
            if "Total" in _ts_market or "total" in _ts_market.lower():
                _ls_add([{"Player": _ts_game, "Prop": "Total",
                          "Line": _ts.get("Total", _ts.get("odds", "")),
                          "source": "theScore Bet"}], "theScore Bet")
            elif any(k in _ts_market.lower() for k in ("moneyline","money line","spread","run line")):
                _ls_add([{**_ts, "source": "theScore Bet"}], "theScore Bet")
        _ls_add(st.session_state.get("dk_pick6_props", []), "DK Pick6")
        _pa_all = st.session_state.get("parlayapi_props_cache", [])
        _ls_add([p for p in _pa_all if p.get("source","").lower() in ("parlayplay","parlay play")], "ParlayPlay")
        # OddsWrap prop name → PrizePicks format mapping
        OW_PROP_MAP = {
            "player points": "Points", "points": "Points",
            "player rebounds": "Rebounds", "rebounds": "Rebounds",
            "player assists": "Assists", "assists": "Assists",
            "player points rebounds assists": "PRA", "pra": "PRA",
            "player steals": "Steals", "steals": "Steals",
            "player blocks": "Blocks", "blocks": "Blocks",
            "player threes": "Threes", "threes": "Threes",
            "player turnovers": "Turnovers", "turnovers": "Turnovers",
            "pitcher strikeouts": "Pitcher Strikeouts", "strikeouts": "Strikeouts",
            "batter hits": "Hits", "hits": "Hits",
            "batter home runs": "Home Runs", "home runs": "Home Runs",
            "batter rbis": "RBI", "rbis": "RBI",
            "batter runs scored": "Runs", "runs scored": "Runs",
            "player pass yards": "Pass Yards", "pass yards": "Pass Yards",
            "player rush yards": "Rush Yards", "rush yards": "Rush Yards",
            "player receiving yards": "Rec Yards", "receiving yards": "Rec Yards",
            "player receptions": "Receptions", "receptions": "Receptions",
            "player shots on goal": "Shots", "shots on goal": "Shots",
            "goalie saves": "Saves", "saves": "Saves",
        }
        for ow_p in (st.session_state.get("oddswrap_props", []) or []):
            _bk = ow_p.get("Book", ow_p.get("source", "")).replace("oddswrap_","").title()
            _bk = {"Draftkings":"DraftKings","Fanduel":"FanDuel","Betmgm":"BetMGM",
                   "Caesars":"Caesars","Betrivers":"BetRivers","Bovada":"Bovada"}.get(_bk, _bk)
            if not _bk:
                continue
            # Normalize prop name to match PrizePicks format
            _raw_prop = str(ow_p.get("Prop","")).lower().strip()
            _norm_prop = OW_PROP_MAP.get(_raw_prop, ow_p.get("Prop",""))
            _ow_normalized = {**ow_p, "Prop": _norm_prop}
            _ls_add([_ow_normalized], _bk)
        _sport_ls = st.session_state.get("last_sport", "NBA")

        # Source-availability debug info moved to the System tab's Fetch
        # Health panel — a bettor comparing lines doesn't need to see
        # "OddsAPI=✅/❌" internals, and showing it here made an otherwise-
        # normal night look broken. Booleans below are still needed for the
        # System tab writeup — see that section for where they're read.
        st.session_state["_ls_source_flags"] = {
            "sport": _sport_ls,
            "OddsAPI": bool(st.session_state.get(f"oddsapi_props_{_sport_ls}", [])),
            "OddsPapi": bool(st.session_state.get(f"oddspapi_props_{_sport_ls}", [])),
            "OddsWrap": bool(st.session_state.get("oddswrap_props", [])),
            "AutoScraper": bool(st.session_state.get(f"auto_scraped_props_{_sport_ls}", [])),
            "EV API": bool(st.session_state.get("ev_api_props")),
        }

        # Try session_state first (faster, no disk read)
        _odds_props_ss = st.session_state.get(f"oddsapi_props_{_sport_ls}", [])
        if _odds_props_ss:
            for _op in _odds_props_ss:
                # OddsAPI stores bookmaker in "source" as "OddsAPI_{bookname}"
                _src = str(_op.get("source","") or _op.get("Book","") or _op.get("bookmaker",""))
                _bk2 = ""
                if "draftkings" in _src.lower():   _bk2 = "DraftKings"
                elif "fanduel"  in _src.lower():   _bk2 = "FanDuel"
                elif "betmgm"   in _src.lower():   _bk2 = "BetMGM"
                elif "caesars"  in _src.lower():   _bk2 = "Caesars"
                elif "bovada"   in _src.lower():   _bk2 = "Bovada"
                elif "bet365"   in _src.lower():   _bk2 = "Bet365"
                elif "pinnacle" in _src.lower():   _bk2 = "Pinnacle"
                elif "betonline" in _src.lower():  _bk2 = "BetOnline"
                if _bk2:
                    _ls_add([_op], _bk2)
        else:
            # Fallback: read from pkl cache
            _odds_cache = os.path.join(CACHE_DIR, f"odds_api_props_{_sport_ls}.pkl")
            if os.path.exists(_odds_cache):
                try:
                    with open(_odds_cache, "rb") as _f:
                        _odds_props = pickle.load(_f)
                    for _op in (_odds_props or []):
                        _bk2 = {"fanduel":"FanDuel","draftkings":"DraftKings","betmgm":"BetMGM",
                                "caesars":"Caesars","bovada":"Bovada","bet365":"Bet365",
                                "circa_sports":"Circa","betonlineag":"BetOnline",
                                "pinnacle":"Pinnacle"}.get(
                            (_op.get("Book","") or _op.get("bookmaker","")).lower(), "")
                        if _bk2:
                            _ls_add([_op], _bk2)
                except (ValueError, KeyError, TypeError, AttributeError):
                    pass

        # Auto scraper props (MyBookie/BetOnline from local machine)
        _auto_ss = st.session_state.get(f"auto_scraped_props_{_sport_ls}", [])
        for _ap in (_auto_ss or []):
            _src_a = str(_ap.get("Book","") or _ap.get("source",""))
            _bk_a  = ""
            if "mybookie"   in _src_a.lower(): _bk_a = "MyBookie"
            elif "betonline"  in _src_a.lower(): _bk_a = "BetOnline"
            elif "prizepicks" in _src_a.lower(): _bk_a = "PrizePicks"
            elif "pick6"      in _src_a.lower(): _bk_a = "DK Pick6"
            elif "draftkings" in _src_a.lower(): _bk_a = "DraftKings"
            elif "fanduel"    in _src_a.lower(): _bk_a = "FanDuel"
            elif "betmgm"     in _src_a.lower(): _bk_a = "BetMGM"
            elif "caesars"    in _src_a.lower(): _bk_a = "Caesars"
            elif "underdog"   in _src_a.lower(): _bk_a = "Underdog"
            elif "sleeper"    in _src_a.lower(): _bk_a = "Sleeper"
            if _bk_a:
                _norm_ap = {**_ap, "Prop": OW_PROP_MAP.get(
                    str(_ap.get("Prop","")).lower().strip(), _ap.get("Prop","")
                )}
                _ls_add([_norm_ap], _bk_a)

        # Also add OddsPapi props.
        # NOTE (fixed 2026-07-12): fetch_oddspapi_props() deliberately only
        # requests caesars/circa/mybookie/betfair-exchange (see its docstring
        # comment — draftkings/fanduel/betmgm/pinnacle/bet365 come from other
        # sources instead, on purpose). This matching list previously still
        # checked for bet365/pinnacle/draftkings/fanduel/betmgm/betrivers —
        # none of which OddsPapi will ever return — while never checking for
        # caesars/circa/mybookie, which it actually does fetch. Real,
        # successfully-fetched Caesars/Circa data was being silently dropped
        # here every load regardless of "OddsPapi=✅" showing fresh data.
        _oddspapi_ss = st.session_state.get(f"oddspapi_props_{_sport_ls}", [])
        for _op2 in (_oddspapi_ss or []):
            # OddsPapi stores bookmaker in "source" as "OddsPapi_{bookname}"
            _src2 = str(_op2.get("source","") or _op2.get("bookmaker","") or _op2.get("Book",""))
            _bk3 = ""
            if "caesars" in _src2.lower():
                _bk3 = "Caesars"
            elif "circa" in _src2.lower():
                _bk3 = "Circa"
            elif "mybookie" in _src2.lower():
                _bk3 = "MyBookie"
            elif "betfair" in _src2.lower() or "exchange" in _src2.lower():
                _bk3 = "Betfair Exchange"
            if _bk3:
                _ls_add([_op2], _bk3)
        _ls_add(st.session_state.get("sleeper_props_cache", []), "Sleeper")

        # ── LineStar GetPropBets — cross-book snapshot, all books it covers ──
        # Labeled "<Book> (LineStar)" rather than merged into the existing
        # book column: this is a lower-frequency snapshot (hourly, from the
        # browser harvester) than the dedicated per-book sources above, and
        # using the same column name would let it silently overwrite a
        # fresher direct-from-book line depending on call order. Keeping it
        # as its own column makes it a genuine second opinion instead.
        _ls_raw_props = st.session_state.get("linestar_props_data", {})
        if _ls_raw_props:
            try:
                from fetchers import parse_linestar_props_all_books as _parse_ls_books
                _ls_by_book = _parse_ls_books(_ls_raw_props, _sport_ls)
                for _ls_book, _ls_plist in _ls_by_book.items():
                    _ls_add(_ls_plist, f"{_ls_book} (LineStar)")
            except Exception:
                pass

        # ── EV Sharps API — Hard Rock + 20 books live data ──────────────────
        _ev_raw = fetch_ev_api_live()
        _ev_all_props = []
        if _ev_raw and _ev_raw.get("data"):
            _ev_all_props, _ev_sig_ls = extract_ev_props_for_app(_ev_raw, sport_filter=_sport_ls)
            # Feed each book's lines into the line shop lookup
            for _evp in _ev_all_props:
                _ev_bk = _evp.get("Book", "")
                _ev_prop_name = _evp.get("Prop", "")
                _ev_player = normalize_name(_evp.get("Player", ""))
                _ev_line = _evp.get("Line")
                if _ev_player and _ev_prop_name and _ev_line is not None:
                    ls_sources.setdefault(_ev_player, {}).setdefault(_ev_prop_name, {})[_ev_bk] = float(_ev_line)
            # Cache for StatsHub section below
            st.session_state["ev_api_props"] = _ev_all_props
            st.session_state["ev_api_updated"] = _ev_raw.get("updated", {})
        else:
            _ev_all_props = st.session_state.get("ev_api_props", [])


        # Pinnacle, Bet365, MyBookie, BetOnline, Sleeper removed from this list —
        # investigated 2026-07-08, each confirmed structurally blocked (not
        # just data-sparse). Re-add ONLY if one of these changes:
        #   Pinnacle:  guest API returns HTTP 204 (no content) on the props
        #              endpoint — route exists but props are gated behind an
        #              authenticated account API the guest key can't reach.
        #              Game-level markets (spreads/totals) work fine on guest.
        #              Nothing to build without a real Pinnacle account.
        #   Bet365:    harvester only captures moneyline/spread; the total-line
        #              value and any props are simply not in the harvested
        #              payload. This is a Tampermonkey JS fix, not a Python
        #              fix — needs someone with a live Bet365 account + open
        #              DevTools to audit the real network calls. Cannot be
        #              done from a server-side coding environment.
        #   MyBookie:  BOTH known paths dead, not just stale. Action Network
        #              book_id=8 (the fallback) returns HTTP 400/404 on every
        #              props route — it's not a working fallback at all. The
        #              CF-clearance cookie path needs a real browser to solve
        #              the Cloudflare challenge (residential proxy or full
        #              browser automation), not a plain HTTP client.
        #   BetOnline:  api-offering-ext.betonline.ag returns HTTP 401 on all
        #              routes (auth-gated). Confirmed via page config that
        #              player props route exclusively through the Diffusion
        #              WebSocket (DIFFUSION_HOST) with no static JSON
        #              pre-load to scrape instead. Game-level totals via
        #              api-offering.betonline.ag are already wired above —
        #              that's the ceiling without building the full
        #              WebSocket client (previously assessed as too costly
        #              relative to payoff; that assessment still stands).
        #   Sleeper:   api.sleeper.app/graphql is PUBLIC (introspection works,
        #              no token needed) — real fields exist: my_picks_init,
        #              get_pickem_picks_for_league. But my_picks_init needs a
        #              logged-in session ("my" = current user), and
        #              get_pickem_picks_for_league needs leg_id (an internal
        #              picks-league ID only visible inside the app, not
        #              discoverable via the public API). The public
        #              api.sleeper.app/v1 only has fantasy roster/stat data,
        #              no prop lines anywhere. The public API is the fantasy
        #              layer, not the picks layer — not buildable without auth.
        BOOK_ORDER = ["PrizePicks","Underdog","DK Pick6","ParlayPlay","DraftKings","FanDuel","BetMGM","Caesars","BetRivers","Hard Rock","ESPN Bet","Circa","Bovada","NoVig","Kalshi","Fliff"]
        all_books_ls = sorted({bk for pd_ in ls_sources.values() for pd2 in pd_.values() for bk in pd2
                                if not bk.startswith("Unabated (")})
        all_books_ls = BOOK_ORDER + [b for b in all_books_ls if b not in BOOK_ORDER]

        rows_ls = []
        for prop in board_ls[:50]:
            player_ls, pn_ls, pp_line_ls, side_ls = prop["Player"], prop["Prop"], prop["Line"], prop["Side"]
            norm_ls = normalize_name(player_ls)
            row = {"Player": player_ls, "Prop": pn_ls, "Side": side_ls, "Tier": prop.get("Tier","—"), "PrizePicks": pp_line_ls}
            other_lines = {}
            prop_sources = ls_sources.get(norm_ls, {}).get(pn_ls, {})
            for bk in all_books_ls:
                if bk == "PrizePicks":
                    # PrizePicks is the board's own baseline line (pp_line_ls,
                    # already set above) — NOT a comparison-book entry in
                    # ls_sources. Overwriting it here was the bug: it stomped
                    # the real price with "—" on every row since ls_sources
                    # is essentially never populated under the "PrizePicks"
                    # key, making the Line Shop always report 0 PrizePicks
                    # props regardless of actual board data. (Fixed 2026-07-11.)
                    continue
                lv = prop_sources.get(bk)
                row[bk] = lv if lv is not None else "—"
                if lv is not None:
                    other_lines[bk] = lv
            all_cands = {"PrizePicks": pp_line_ls, **other_lines}
            best_bk = min(all_cands, key=all_cands.get) if side_ls == "OVER" else max(all_cands, key=all_cands.get)
            best_ln = all_cands[best_bk]
            row["Best Book"] = best_bk
            row["Best Line"] = best_ln
            row["Edge Gain"] = round(abs(best_ln - pp_line_ls), 1) if best_ln != pp_line_ls else 0
            rows_ls.append(row)

        if rows_ls:
            # Only show columns that actually have at least one price loaded
            # this session — a column that's structurally always empty
            # (missing credentials, source not wired for this sport, etc.)
            # made the whole page look broken even on a normal night. Real
            # gaps are now visible in the System tab's Fetch Health panel
            # instead of as permanent "0 ❌" tiles here.
            # BUG FIX (2026-07): active_sources was hardcoded to BOOK_ORDER only,
            # so any book discovered dynamically at runtime -- EV Sharps' 20+
            # books, and now LineStar's "<Book> (LineStar)" columns -- got
            # computed into row[bk] above but was never actually rendered,
            # since _visible_books filtered strictly to BOOK_ORDER. all_books_ls
            # already contains BOOK_ORDER plus every book actually seen this
            # session, so use that instead.
            active_sources = [b for b in all_books_ls if b != "ParlayPlay"]
            _book_counts = {b: sum(1 for r in rows_ls if r.get(b) not in ("—", None, "")) for b in active_sources}
            _visible_books = [b for b in active_sources if _book_counts[b] > 0]

            def _line_shop_table_html(rows, book_cols):
                head_cols = ["Player","Prop","Side"] + book_cols + ["Best Book","Best Line"]
                head = "".join(
                    f'<th style="text-align:left;padding:6px 10px;color:var(--bc-dim);font-size:11px;'
                    f'text-transform:uppercase;border-bottom:1px solid var(--bc-border);white-space:nowrap;">{c}</th>'
                    for c in head_cols
                )
                body = ""
                for r in rows:
                    cells = []
                    for c in ["Player","Prop","Side"]:
                        cells.append(f'<td style="padding:6px 10px;font-size:13px;color:var(--bc-text);border-bottom:1px solid #16232f;white-space:nowrap;">{r.get(c,"")}</td>')
                    for c in book_cols:
                        v = r.get(c, "—")
                        is_best = (c == r.get("Best Book"))
                        style = ("padding:6px 10px;font-size:13px;border-bottom:1px solid #16232f;text-align:center;"
                                 + ("color:#22c55e;font-weight:700;background:#22c55e14;" if is_best else "color:var(--bc-dim);"))
                        cells.append(f'<td style="{style}">{v}</td>')
                    cells.append(f'<td style="padding:6px 10px;font-size:13px;color:#22c55e;font-weight:700;border-bottom:1px solid #16232f;white-space:nowrap;">{r.get("Best Book","")}</td>')
                    cells.append(f'<td style="padding:6px 10px;font-size:13px;color:#22c55e;font-weight:700;border-bottom:1px solid #16232f;">{r.get("Best Line","")}</td>')
                    body += f"<tr>{''.join(cells)}</tr>"
                return (
                    '<div style="background:var(--bc-bg-card);border:1px solid var(--bc-border);'
                    'border-radius:8px;overflow:auto;max-height:600px;margin-bottom:0.5rem;">'
                    f'<table style="width:100%;border-collapse:collapse;"><thead><tr>{head}</tr></thead>'
                    f'<tbody>{body}</tbody></table></div>'
                )

            st.markdown(_line_shop_table_html(rows_ls, _visible_books), unsafe_allow_html=True)
            _hidden = [b for b in active_sources if b not in _visible_books]
            if _hidden:
                # Most of these 16 book names (Hard Rock, DraftKings, FanDuel,
                # BetMGM, Caesars, ESPN Bet, Circa, Bovada, BetRivers,
                # BetOnline, NoVig, Kalshi, Fliff) all come through ONE feed
                # -- EV Sharps API (EV_BOOK_LABELS) -- not 16 separate
                # scrapers. If that one feed is stale/down, all of them go
                # dark at once, which looks like "16 sites are broken" but
                # is really "one shared source needs attention." Check that
                # specific source before assuming anything else is wrong.
                try:
                    from fetchers import get_harvester_alerts, harvester_display_name
                    _ls_alerts = get_harvester_alerts(_sport_ls)
                    _ls_ev_dark = [harvester_display_name(a["name"]) for a in _ls_alerts if a["name"] in ("evsharps", "evsharps_ev")]
                except Exception:
                    _ls_ev_dark = []
                if _ls_ev_dark:
                    st.warning(f"⚠️ {len(_hidden)} of tonight's book columns aren't showing prices — but this isn't 16 separate outages. "
                               f"Almost all of them (Hard Rock, DraftKings, FanDuel, BetMGM, Caesars, ESPN Bet, Circa, Bovada, BetRivers, BetOnline, "
                               f"NoVig, Kalshi, Fliff) come from one shared feed, **{', '.join(_ls_ev_dark)}**, which hasn't updated recently. "
                               f"That's the one thing worth checking (System tab → Harvester Health) — not each book individually.")
                else:
                    st.caption(f"Not showing {len(_hidden)} source(s) with no prices for tonight's props: {', '.join(_hidden)}. "
                               f"Most of these share one data feed (EV Sharps) rather than being scraped individually — if it looks "
                               f"like everything's dark at once, that's usually one feed, not sixteen. Check System → Fetch Health if it persists.")

            better_ls = [r for r in rows_ls if r["Best Book"] != "PrizePicks" and r["Edge Gain"] >= 0.5]
            if better_ls:
                st.markdown("### \U0001f525 Better Lines Available Elsewhere")
                st.caption(f"{len(better_ls)} props where another platform has a more favorable line (≥0.5)")
                for _bl in better_ls:
                    _bl_tier_c = TIER_COLORS.get(_bl.get("Tier", ""), "#6a7a8a")
                    st.markdown(
                        f'<div style="background:var(--bc-bg-card);border:1px solid var(--bc-border);'
                        f'border-left:3px solid {_bl_tier_c};border-radius:8px;padding:10px 14px;margin-bottom:6px;">'
                        f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                        f'<span style="font-weight:600;">{_bl.get("Player","")} · {_bl.get("Prop","")} '
                        f'({_bl.get("Side","")})</span>'
                        f'<span style="background:{_bl_tier_c}22;color:{_bl_tier_c};border:0.5px solid {_bl_tier_c}44;'
                        f'border-radius:10px;padding:2px 8px;font-size:11px;font-weight:700;">{_bl.get("Tier","")}</span>'
                        f'</div>'
                        f'<div style="color:#8ab4d4;font-size:12px;margin-top:4px;">'
                        f'PrizePicks {_bl.get("PrizePicks","")} → <b style="color:#22c55e;">{_bl.get("Best Book","")} '
                        f'{_bl.get("Best Line","")}</b> · edge gain +{_bl.get("Edge Gain","")}</div>'
                        f'</div>', unsafe_allow_html=True,
                    )
            else:
                st.success("✅ PrizePicks has the best available line on all loaded props.")
        disc_ls = st.session_state.get("multibook_discrepancies", [])
        if disc_ls:
            st.markdown("### \U0001f4ca Cross-Book Discrepancies")
            st.caption("Large gaps between books signal sharp money or line errors")
            for _dl in disc_ls[:10]:
                st.markdown(
                    f'<div style="background:var(--bc-bg-card);border:1px solid var(--bc-border);'
                    f'border-radius:8px;padding:10px 14px;margin-bottom:6px;">'
                    f'<span style="font-weight:600;">{_dl.get("Player","")} · {_dl.get("Prop","")}</span>'
                    f'<div style="color:#8ab4d4;font-size:12px;margin-top:4px;">'
                    f'PrizePicks {_dl.get("PrizePicks","")} vs {_dl.get("Book","")} {_dl.get("BookLine","")} '
                    f'· diff {_dl.get("Diff","")} · favors {_dl.get("Favor","")}</div>'
                    f'</div>', unsafe_allow_html=True,
                )
        arb_ls = st.session_state.get("arb_opportunities", [])
        if arb_ls:
            st.markdown("### \u26a1 Arbitrage Opportunities")
            for _al in arb_ls[:10]:
                st.markdown(
                    f'<div style="background:var(--bc-bg-card);border:1px solid #a855f744;'
                    f'border-radius:8px;padding:10px 14px;margin-bottom:6px;">'
                    f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                    f'<span style="font-weight:600;">{_al.get("Player","")} · {_al.get("Stat","")} {_al.get("Line","")}</span>'
                    f'<span style="color:#a855f7;font-weight:700;">{_al.get("Arb Profit","")}</span>'
                    f'</div>'
                    f'<div style="color:#8ab4d4;font-size:12px;margin-top:4px;">'
                    f'OVER {_al.get("OVER Book","")} {_al.get("OVER Odds","")} ({_al.get("OVER Stake","")}) · '
                    f'UNDER {_al.get("UNDER Book","")} {_al.get("UNDER Odds","")} ({_al.get("UNDER Stake","")})</div>'
                    f'</div>', unsafe_allow_html=True,
                )

        # ── StatsHub — Statcast + Hit Rates from EV API ──────────────────────
        st.markdown("---")
        st.markdown("### 📊 StatsHub — Player Analytics")
        _sh_props = [p for p in _ev_all_props if p.get("_savant") or p.get("_hit_rates")]
        if not _sh_props:
            st.info("EV API not loaded or no Statcast data available. Open Line Shop to trigger a fetch.")
        else:
            _seen_sh = set()
            _sh_unique = []
            for _p in _sh_props:
                _k = (normalize_name(_p.get("Player","")), _p.get("Prop",""))
                if _k not in _seen_sh:
                    _seen_sh.add(_k)
                    _sh_unique.append(_p)

            _c_filt1, _c_filt2 = st.columns(2)
            _sh_sport_filter = _c_filt1.selectbox("Sport", ["All","MLB","NBA","NFL","NHL"], key="sh_sport_filter")
            _sh_prop_filter  = _c_filt2.selectbox("Prop Type", ["All"] + sorted({p.get("Prop","") for p in _sh_unique if p.get("Prop")}), key="sh_prop_filter")
            if _sh_sport_filter != "All":
                _sh_unique = [p for p in _sh_unique if p.get("Sport","") == _sh_sport_filter]
            if _sh_prop_filter != "All":
                _sh_unique = [p for p in _sh_unique if p.get("Prop","") == _sh_prop_filter]

            _updated = st.session_state.get("ev_api_updated", {})
            _last_upd = _updated.get("dk","") or _updated.get("hr","")
            st.caption(f"{len(_sh_unique)} players with Statcast data" + (f" | Last updated: {_last_upd}" if _last_upd else ""))

            for _sp in _sh_unique[:30]:
                _savant    = _sp.get("_savant", {}) or {}
                _hit_rates = _sp.get("_hit_rates", {}) or {}
                _percs     = _sp.get("_batter_percs", {}) or {}
                _pitcher   = _sp.get("_pitcher", {}) or {}
                _player    = _sp.get("Player","")
                _prop      = _sp.get("Prop","")
                _game      = _sp.get("Game","")
                _odds_over = _sp.get("OddsOver","")
                _ev_val    = _sp.get("EV")
                _fv        = _sp.get("FairValue")
                _link      = _sp.get("_bet_link","")
                _stadium   = _sp.get("_stadium_rank")

                with st.expander(f"**{_player}** — {_prop} | {_game}"):
                    _c1, _c2, _c3 = st.columns(3)
                    with _c1:
                        st.markdown("**⚾ Statcast**")
                        ev_avg  = _savant.get("exit_velocity_avg","—")
                        brl_pct = _savant.get("barrels_per_bip","—")
                        hh_pct  = _savant.get("hard_hit_percent","—")
                        la_avg  = _savant.get("launch_angle_avg","—")
                        xwoba   = _savant.get("est_woba","—")
                        st.markdown(f"Exit Velo: **{ev_avg}** mph")
                        st.markdown(f"Barrel%: **{brl_pct}%**")
                        st.markdown(f"Hard Hit%: **{hh_pct}%**")
                        st.markdown(f"Launch Angle: **{la_avg}°**")
                        st.markdown(f"xwOBA: **{xwoba}**")
                        if _percs:
                            hr_pct = _percs.get("home_run_percentile")
                            if hr_pct:
                                pct_color = "#00d4aa" if float(hr_pct) >= 75 else ("#ffd700" if float(hr_pct) >= 50 else "#aaa")
                                st.markdown(f'HR Percentile: <span style="color:{pct_color};font-weight:700">{float(hr_pct):.1f}th</span>', unsafe_allow_html=True)
                    with _c2:
                        st.markdown("**📈 Hit Rates**")
                        for _period, _label in [("szn","Season"),("lyr","Last Yr"),("L5","L5"),("L10","L10"),("L20","L20")]:
                            _hr_data = _hit_rates.get(_period, {})
                            if _hr_data:
                                w,t,p = _hr_data.get("w",0),_hr_data.get("t",0),_hr_data.get("p",0)
                                _hr_color = "#00d4aa" if int(p) >= 30 else ("#ffd700" if int(p) >= 20 else "#aaa")
                                st.markdown(f'{_label}: <span style="color:{_hr_color}"><b>{w}/{t}</b> ({p}%)</span>', unsafe_allow_html=True)
                        if _stadium is not None:
                            st.markdown(f"Stadium HR Rank: **#{_stadium}**")
                    with _c3:
                        st.markdown("**💰 Edge**")
                        if _odds_over:
                            st.markdown(f"Odds (Over): **{_odds_over}**")
                        if _ev_val is not None:
                            try:
                                ev_color = "#00d4aa" if float(_ev_val) > 0 else "#e05c5c"
                                st.markdown(f'EV: <span style="color:{ev_color}"><b>{float(_ev_val):+.1%}</b></span>', unsafe_allow_html=True)
                            except (ValueError, TypeError):
                                st.markdown(f"EV: **{_ev_val}**")
                        if _fv:
                            st.markdown(f"Fair Value: **{_fv}**")
                        if _pitcher:
                            st.markdown("**🎯 Pitcher**")
                            st.markdown(f"ERA: {_pitcher.get('era','—')} | xwOBA: {_pitcher.get('xwoba','—')}")
                            st.markdown(f"Barrel% allowed: {_pitcher.get('barrels_per_bip','—')}%")
                        if _link:
                            st.markdown(f"[🎰 Bet Hard Rock]({_link})")

# ----- TAB 7: SYSTEM -----
with tabs[12]:
    # PREVIEW BOARD (2026-07): raw next-day game lines only. No tier
    # classification, no Kelly staking — starters/injuries aren't locked
    # this far out, so nothing here should be treated as a recommendation.
    # Separate session-state/cache path from the live board; cannot collide
    # with today's board_loaded / last_good_props state.
    st.markdown('<div class="bc-section-header">📅 Preview <span style="opacity:0.6;font-weight:400;">— Tomorrow\'s Lines (Provisional)</span></div>', unsafe_allow_html=True)
    st.warning(
        "⚠️ **Provisional data only.** Starting pitchers, injury reports, and lineups "
        "are not finalized this far out — these lines are raw and unscored. No tier "
        "ratings, no Kelly stake sizing. Use for line-shopping context only, not as a "
        "recommendation. Re-check the live board once it becomes today's board."
    )
    _preview_sport = st.selectbox("Sport", SPORTS, key="preview_sport_sel")
    if st.button("🔄 Load Preview", key="preview_load_btn"):
        with st.spinner(f"Fetching tomorrow's {_preview_sport} lines..."):
            st.session_state[f"preview_games_{_preview_sport}"] = fetch_preview_game_lines(_preview_sport)
    _preview_games = st.session_state.get(f"preview_games_{_preview_sport}", [])
    if _preview_games:
        st.caption(f"{len(_preview_games)} games found for tomorrow — {_preview_games[0].get('Game Time','')[:10]}")
        st.markdown(_bc_df_html(_preview_games, columns=["Matchup", "Spread", "Total", "Home ML", "Away ML", "Odds Source", "Game Time"]), unsafe_allow_html=True)
    else:
        st.markdown(empty_state_html("📅", "No preview data loaded yet",
                     "Click Load Preview above. If it's still empty afterward, tomorrow's lines may not be posted yet for this sport."),
                     unsafe_allow_html=True)

with tabs[14]:
    st.markdown('<div class="bc-section-header">⚙️ System Info</div>', unsafe_allow_html=True)

    # ── System Health Gauge (top fold) ──────────────────────────────────
    # "Is the system ready to fire, or is it broken" at a glance, instead
    # of scrolling past ~25 sections to piece it together. Reuses the same
    # data every section below already computes (fetch_timings, circuit_
    # status, harvester alerts) -- this doesn't run anything new, it just
    # surfaces the 3 things that actually matter first: is anything
    # tripped, how fresh is the data, how long did the last load take.
    _shg_cb = circuit_status()
    _shg_tripped = [p for p, s in _shg_cb.items() if s["tripped"]]
    _shg_timings = st.session_state.get("fetch_timings", {})
    _shg_wall_time = max((t.get("time", 0) for t in _shg_timings.values()), default=0)
    try:
        _shg_sport = st.session_state.get("last_sport", "NBA")
        _shg_alerts = get_harvester_alerts(_shg_sport)
        _shg_sharp_dark = [a for a in _shg_alerts if a["tier"] == "sharp"]
    except Exception:
        _shg_alerts, _shg_sharp_dark = [], []
    _shg_health_pct = max(0, 100 - len(_shg_alerts) * 5 - len(_shg_tripped) * 15)

    if _shg_tripped or _shg_sharp_dark:
        st.error(f"🛑 **Not ready to fire** — " +
                 (f"{len(_shg_tripped)} circuit breaker(s) tripped ({', '.join(_shg_tripped)}). " if _shg_tripped else "") +
                 (f"{len(_shg_sharp_dark)} sharp-tier source(s) dark ({', '.join(harvester_display_name(a['name']) for a in _shg_sharp_dark)})." if _shg_sharp_dark else ""))
    elif _shg_wall_time > 20:
        st.warning(f"🟡 **Ready, but slow** — last board load took {_shg_wall_time:.0f}s (target: under 20s). See Network Health below for what's dragging.")
    elif _shg_timings:
        st.success("🟢 **Ready to fire** — no tripped circuits, no dark sharp sources, load time normal.")
    else:
        st.info("⚪ **Not checked yet** — load a board to populate health data.")

    _shg_c1, _shg_c2, _shg_c3 = st.columns(3)
    _shg_c1.metric("Data Freshness", f"{_shg_health_pct}%",
                   help="100% minus a penalty per degraded/dark source and per tripped circuit breaker.")
    _shg_c2.metric("Last Load Time", f"{_shg_wall_time:.0f}s" if _shg_timings else "—",
                   delta="🔴 slow" if _shg_wall_time > 20 else None, delta_color="inverse")
    _shg_c3.metric("Circuit Breakers", f"{len(_shg_tripped)} tripped" if _shg_tripped else "0 tripped",
                   delta="🔴 action needed" if _shg_tripped else "🟢 clear", delta_color="inverse" if _shg_tripped else "off")
    st.markdown("---")


    # ── EV Auto-Refresh Control ───────────────────────────────
    _col_tog1, _col_tog2, _col_tog3 = st.columns([2, 2, 3])
    with _col_tog1:
        _auto_refresh_toggle = st.toggle(
            "🔄 EV Auto-Refresh (2min)",
            value=st.session_state.get("ev_auto_refresh_enabled", True),
            help="Fetches fresh EV API odds every 2 minutes and detects line movement automatically."
        )
        st.session_state["ev_auto_refresh_enabled"] = _auto_refresh_toggle
    with _col_tog2:
        _last_ts = st.session_state.get("ev_auto_refresh_ts", 0)
        if _last_ts:
            _mins = int((time.time() - _last_ts) / 60)
            _secs = int((time.time() - _last_ts) % 60)
            st.metric("Last EV Snapshot", f"{_mins}m {_secs}s ago")
        else:
            st.metric("Last EV Snapshot", "Not yet")
    with _col_tog3:
        _alerts_count = len(st.session_state.get("sharp_alerts", []))
        _mv_count     = len(st.session_state.get("ev_movement_lookup", {}))
        st.metric("Sharp Alerts", _alerts_count, delta=f"{_mv_count} props tracked")
    st.markdown("---")

    # ── GEM Brief Generator ──────────────────────────────────
    st.markdown("### 🤖 GEM Brief Generator")
    st.caption("Generates a full MODE A brief — paste directly into Gemini, ChatGPT, or Claude to run the BetCouncil AI model away from the dashboard.")
    _gem_col1, _gem_col2 = st.columns([1, 3])
    with _gem_col1:
        if st.button("📋 Generate GEM Brief", type="primary", use_container_width=True):
            _brief = generate_gem_summary()
            st.session_state["gem_brief_output"] = _brief
    if st.session_state.get("gem_brief_output"):
        st.text_area(
            "Copy this entire block → paste into AI chatbox as your first message:",
            value=st.session_state["gem_brief_output"],
            height=400,
            key="gem_brief_textarea",
            help="Select all (Ctrl+A / Cmd+A) then copy. Paste into Gemini/ChatGPT/Claude. The model will auto-detect MODE A and run full analysis."
        )
        st.success("✅ Brief ready — select all text above and copy.")
    st.markdown("---")

    # ── Real Model Health (focused, plain-language summary) ──────────
    # Built 2026-08-18 in direct response to real user feedback: the full
    # Data Source Status section below lists 40+ sources, most of which
    # are comparison/context data that never touches actual scoring --
    # a wall of yellow warnings that looks alarming regardless of whether
    # anything that matters is actually wrong. This surfaces only the
    # handful of things that genuinely feed your board's real numbers.
    st.markdown("### ✅ Model Health — What Actually Matters")
    _mh_board = st.session_state.get("board_data", []) or []
    _mh_games = st.session_state.get("games", []) or []
    _mh_issues = []
    _mh_good = []

    if _mh_board:
        _mh_good.append(f"**Props loaded:** {len(_mh_board)} real props on your board")
    else:
        _mh_issues.append("**No props loaded yet** — load a board to check")

    if _mh_games:
        _mh_good.append(f"**Game lines loaded:** {len(_mh_games)} real games")
    else:
        _mh_issues.append("**No game lines loaded** — real games may not have posted yet, or check the Game Lines tab directly")

    if _mh_good:
        for _g in _mh_good:
            st.success(f"✅ {_g}")
    for _i in _mh_issues:
        st.warning(f"⚠️ {_i}")
    st.caption(
        "This checks only what actually feeds your model's real numbers — props and game "
        "lines. Everything in the detailed section below (FavoredProps, DraftEdge, Kalshi, "
        "Polymarket, and 30+ others) is comparison/context data shown for reference — none "
        "of it being 'stale' changes what your board actually scores. For audit results and "
        "calibration detail, see the Board Audit Engine and Confidence Calibration sections below."
    )
    st.markdown("---")

    # ── Data Source Status (from last board load) ────────────
    st.markdown("### 📊 Data Source Status")
    st.caption("Based on last board load — no API calls used. Load a board to update.")

    _src_statuses = []
    _pp_src = st.session_state.get("pp_source", "")
    _pp_st  = st.session_state.get("pp_status", "")
    _errors = st.session_state.get("errors", [])
    _error_sources = {e.get("source","") for e in _errors if e.get("type","") != "info"}

    # PrizePicks
    _pp_board = st.session_state.get("board", [])
    _pp_count = len([p for p in _pp_board if "prizepicks" in str(p.get("source","")).lower() or "pp" in str(p.get("book","")).lower()]) if _pp_board else 0
    _pp_count_str = f" ({_pp_count} props)" if _pp_count else ""
    if _pp_src == "gist_scraper":
        _src_statuses.append({"Source": "PrizePicks", "Status": f"🟢 Loaded via GitHub Actions{_pp_count_str}", "Action": "None"})
    elif _pp_src == "prizepicks_direct":
        _src_statuses.append({"Source": "PrizePicks", "Status": f"🟢 Connected via direct scrape{_pp_count_str}", "Action": "None"})
    elif _pp_st == "ok" and _pp_count:
        _src_statuses.append({"Source": "PrizePicks", "Status": f"🟢 Loaded{_pp_count_str}", "Action": "None"})
    elif _pp_st == "unavailable":
        _src_statuses.append({"Source": "PrizePicks", "Status": "🔴 All sources unavailable (Gist + direct scrape)", "Action": "Check GitHub Actions workflow run"})
    else:
        _src_statuses.append({"Source": "PrizePicks", "Status": "⚪ Not loaded yet", "Action": "Load a board"})

    # Underdog
    _ud = st.session_state.get("ud_props_compare", [])
    if _ud:
        _src_statuses.append({"Source": "Underdog", "Status": f"🟢 {len(_ud)} props (auto via GitHub Actions)", "Action": "None"})
    else:
        _src_statuses.append({"Source": "Underdog", "Status": "⚪ Not loaded yet", "Action": "Load a board"})

    # ParlayPlay
    _pp_play = st.session_state.get("parlayapi_props_cache", [])
    _pp_play_count = len([p for p in _pp_play if "parlayplay" in str(p.get("source","")).lower()]) if _pp_play else 0
    if _pp_play_count > 0:
        _src_statuses.append({"Source": "ParlayPlay", "Status": f"🟢 {_pp_play_count} props", "Action": "None"})
    elif "parlayplay" in str(_error_sources).lower():
        _src_statuses.append({"Source": "ParlayPlay", "Status": "🔴 403 Blocked from cloud", "Action": "Add to local scraper OR refresh PARLAYPLAY_SESSION"})
    else:
        _src_statuses.append({"Source": "ParlayPlay", "Status": "⚪ Not loaded yet", "Action": "Load a board"})

    # OddsPAPI
    _oddspapi = st.session_state.get(f"oddspapi_props_{st.session_state.get('last_sport','NBA')}", [])
    if _oddspapi:
        _src_statuses.append({"Source": "OddsPAPI (DK/FD/BetMGM/Pin/365)", "Status": f"🟢 {len(_oddspapi)} props", "Action": "None"})
    elif "oddspapi" in str(_error_sources).lower():
        _src_statuses.append({"Source": "OddsPAPI (DK/FD/BetMGM/Pin/365)", "Status": "🟡 Rate limited or quota hit", "Action": "Wait for daily reset (100/day, 1000/month)"})
    elif not ODDSPAPI_KEY:
        _src_statuses.append({"Source": "OddsPAPI (DK/FD/BetMGM/Pin/365)", "Status": "🟡 Add ODDSPAPI_KEY to secrets", "Action": "None"})
    else:
        _src_statuses.append({"Source": "OddsPAPI (DK/FD/BetMGM/Pin/365)", "Status": "⚪ Not loaded yet", "Action": "Load a board"})

    # OddsAPI
    _oddsapi = st.session_state.get(f"oddsapi_props_{st.session_state.get('last_sport','NBA')}", [])
    if _oddsapi:
        _src_statuses.append({"Source": "OddsAPI (game lines)", "Status": f"🟢 {len(_oddsapi)} lines", "Action": "None"})
    else:
        _src_statuses.append({"Source": "OddsAPI (game lines)", "Status": "⚪ Not loaded yet", "Action": "Load a board"})

    # Bovada
    _bov = st.session_state.get("bovada_lines", [])
    if _bov:
        _src_statuses.append({"Source": "Bovada (game lines)", "Status": f"🟢 {len(_bov)} lines", "Action": "None"})
    else:
        _src_statuses.append({"Source": "Bovada (game lines)", "Status": "⚪ Not loaded yet", "Action": "Load a board"})

    # Action Network (live public API, no auth needed)
    _an = st.session_state.get("action_network_data", {})
    if _an:
        _src_statuses.append({"Source": "Action Network", "Status": "🟢 Loaded (live public API)", "Action": "None"})
    else:
        _src_statuses.append({"Source": "Action Network", "Status": "⚪ Not loaded yet", "Action": "Load a board"})

    # OddsShark (direct fetch fallback, no auth needed)
    _osh = st.session_state.get("oddsshark_data", {})
    if _osh:
        _src_statuses.append({"Source": "OddsShark", "Status": "🟢 Loaded (auto, no Tampermonkey needed)", "Action": "None"})
    else:
        _src_statuses.append({"Source": "OddsShark", "Status": "⚪ Not loaded yet", "Action": "Load a board"})

    # Pinnacle
    _pin = st.session_state.get(f"pinnacle_{st.session_state.get('last_sport','NBA')}", {})
    if _pin:
        _src_statuses.append({"Source": "Pinnacle (sharp lines)", "Status": "🟢 Connected", "Action": "None"})
    else:
        _src_statuses.append({"Source": "Pinnacle (sharp lines)", "Status": "⚪ Not loaded yet", "Action": "Load a board"})

    # Auto Scraper Gist
    _auto = st.session_state.get(f"auto_scraped_props_{st.session_state.get('last_sport','NBA')}", [])
    if _auto:
        _books = list({p.get("Book","") for p in _auto})
        _src_statuses.append({"Source": "Auto Scraper (Gist)", "Status": f"🟢 {len(_auto)} props from {', '.join(_books)}", "Action": "Run scraper daily"})
    else:
        _src_statuses.append({"Source": "Auto Scraper (Gist)", "Status": "⚪ No data — run scraper", "Action": "python betcouncil_auto_scraper.py --all"})

    # Injuries
    _inj = st.session_state.get("injuries_combined", {})
    if _inj:
        _src_statuses.append({"Source": "Injuries (ESPN/RotoWire/CBS)", "Status": f"🟢 {len(_inj)} players tracked", "Action": "None"})
    else:
        _src_statuses.append({"Source": "Injuries (ESPN/RotoWire/CBS)", "Status": "⚪ Not loaded yet", "Action": "Load a board"})

    # Action Network
    _an = st.session_state.get("an_props_data", [])
    if _an:
        _src_statuses.append({"Source": "Action Network (public %)", "Status": f"🟢 {len(_an)} signals", "Action": "None"})
    else:
        _src_statuses.append({"Source": "Action Network (public %)", "Status": "⚪ Not loaded yet", "Action": "Load a board"})

    # Kalshi
    _kal = st.session_state.get("kalshi_markets", [])
    if _kal:
        _src_statuses.append({"Source": "Kalshi (prediction markets)", "Status": f"🟢 {len(_kal)} markets", "Action": "None"})
    else:
        _src_statuses.append({"Source": "Kalshi (prediction markets)", "Status": "⚪ Not loaded yet", "Action": "Load a board"})

    # Polymarket
    _poly = st.session_state.get("polymarket_markets", [])
    if _poly:
        _src_statuses.append({"Source": "Polymarket", "Status": f"🟢 {len(_poly)} markets", "Action": "None"})
    else:
        _src_statuses.append({"Source": "Polymarket", "Status": "⚪ Not loaded yet", "Action": "Load a board"})

    # Covers
    _cov = st.session_state.get("covers_consensus", [])
    if _cov:
        _src_statuses.append({"Source": "Covers (consensus)", "Status": f"🟢 {len(_cov)} games", "Action": "None"})
    else:
        _src_statuses.append({"Source": "Covers (consensus)", "Status": "⚪ Not loaded yet", "Action": "Load a board"})

    # EV Sharps API
    _ev_sys = st.session_state.get("ev_api_props", [])
    if _ev_sys:
        _ev_books_seen = len({p.get("Book","") for p in _ev_sys})
        _src_statuses.append({"Source": "EV Sharps API (20+ books)", "Status": f"🟢 {len(_ev_sys)} props | {_ev_books_seen} books", "Action": "Open Line Shop to refresh"})
    else:
        _src_statuses.append({"Source": "EV Sharps API (20+ books)", "Status": "⚪ Not loaded — open Line Shop tab", "Action": "Open Line Shop"})

    # EV Movement — snapshot engine + JWT fallback
    _ev_jwt_present  = bool(_get_ev_jwt())
    _mv_alerts       = st.session_state.get("sharp_alerts", [])
    _last_refresh_ts = st.session_state.get("ev_auto_refresh_ts", 0)
    _auto_on         = st.session_state.get("ev_auto_refresh_enabled", True)
    _mins_ago        = int((time.time() - _last_refresh_ts) / 60) if _last_refresh_ts else None
    _refresh_status  = f"Last snapshot: {_mins_ago}m ago" if _mins_ago is not None else "Not yet refreshed"

    if _mv_alerts:
        _src_statuses.append({"Source": "EV Line Movement (S8/S9)", "Status": f"🟢 {len(_mv_alerts)} alerts | {_refresh_status}", "Action": "Auto-refreshes every 2min"})
    elif _auto_on and st.session_state.get("board_loaded"):
        _src_statuses.append({"Source": "EV Line Movement (S8/S9)", "Status": f"🟡 Watching — {_refresh_status}", "Action": "Auto-refreshes every 2min"})
    else:
        _src_statuses.append({"Source": "EV Line Movement (S8/S9)", "Status": "⚪ Load board to activate", "Action": "Snapshot engine ready"})


    # FanDuel props (SharpAPI) status row removed Aug 1 2026 along with the
    # feature itself -- see fetch_sharpapi_lines comment in fetchers.py

    # Scanbet Pinnacle drops (GraphQL via bookmarklet)
    try:
        _sbd = fetch_scanbet_drops_from_gist()
    except Exception: _sbd = []
    st.session_state["scanbet_drops"] = _sbd
    _sbd_steam = [d for d in _sbd if d.get("is_steam") and abs(d.get("drop_pct",0)) > 0.03]
    _src_statuses.append({"Source": "Scanbet (Pinnacle line movement)",
        "Status": (f"🟢 {len(_sbd)} moves | {len(_sbd_steam)} steam" if _sbd
                   else "⚪ Run Scanbet bookmarklet to populate"),
        "Action": "None"})

    # Unified sharp score board — combines Scanbet CLV/steam + Action Network RLM
    try:
        from unified_sharp_score import build_unified_sharp_board as _build_usb
        _usb_sport = st.session_state.get("active_sport", "MLB")
        st.session_state["unified_sharp_board"] = _build_usb(_usb_sport)
    except Exception as _usb_err:
        st.session_state["unified_sharp_board"] = []
        print(f"[WARN] unified_sharp_score: {_usb_err}")

    # SharpAPI line movement + EV status row removed Aug 1 2026 along with
    # the feature itself -- redundant with EVSharps (free) + ODDS_API_IO_KEY

    # Signal Odds
    _so_ev   = st.session_state.get("signalodds_events", [])
    _so_bl   = st.session_state.get("betslib_predictions", [])
    _so_live = st.session_state.get("betslib_live_events", [])
    _so_sb   = sum(1 for e in _so_ev if e.get("has_sure_bet"))
    _so_sb  += sum(1 for e in _so_live if e.get("has_sure_bet"))
    _src_statuses.append({"Source": "Signal Odds (AI picks + live odds)",
        "Status": (f"🟢 {len(_so_bl)} AI picks | {len(_so_live)} live | {_so_sb} sure bets"
                   if _so_bl or _so_live else "🟡 Add SIGNAL_ODDS_JWT to Streamlit secrets"),
        "Action": "None"})

    # ── Browser Harvester Status Panel ─────────────────────────────────────
    try:
        from fetchers import get_harvester_status as _get_hs
        _hs       = _get_hs(st.session_state.get("last_sport", "NBA"))
        _h_active = sum(1 for v in _hs.values() if v.get("active"))
        _h_total  = len(_hs)
        _h_stale  = {k:v for k,v in _hs.items() if not v.get("active")}
        # Summary row
        _src_statuses.append({
            "Source": f"🌐 Auto-Harvester ({_h_active}/{_h_total} live)",
            "Status": (f"🟢 All {_h_total} sources active"
                       if _h_active == _h_total
                       else f"🟡 {_h_active}/{_h_total} live | {len(_h_stale)} stale/pending"),
            "Action": "None"
        })
        # Detail rows for each source
        for _sname, _sv in _hs.items():
            _age_str = f"{_sv['age_minutes']}min" if _sv.get("age_minutes") else "no data"
            _src_str = _sv.get("source","?")
            _cnt = _sv.get("count")
            _cnt_str = f" | {_cnt} lines" if _cnt is not None else ""
            if _sv.get("active"):
                _icon = "🟢"
                _stat = f"Live ({_age_str} | {_src_str}{_cnt_str})"
            elif _sv.get("age_minutes") is None:
                _icon = "⚪"
                _stat = "Pending — load a board to activate"
            else:
                _icon = "🟡"
                _stat = f"Stale ({_age_str}) — auto-refreshes on board load"
            _src_statuses.append({
                "Source": f"  {_icon} {_sname}",
                "Status": _stat,
                "Action": "None"
            })
    except Exception as _he:
        _src_statuses.append({"Source": "Auto-Harvester", "Status": f"⚠️ {str(_he)[:60]}", "Action": "None"})

    # StatMuse (on-demand player trends)
    try:
        _sm_n = len([f for f in os.listdir(CACHE_DIR) if f.startswith("statmuse_")])
    except Exception:
        _sm_n = 0
    _src_statuses.append({"Source": "StatMuse (player trends)",
        "Status": f"🟢 {_sm_n} cached" if _sm_n else "⚪ On-demand per prop",
        "Action": "None"})

    # Bookmaker.eu
    _bkr = st.session_state.get("bookmaker_game_lines", [])
    _src_statuses.append({"Source": "Bookmaker.eu (sharp lines)",
        "Status": f"🟢 {len(_bkr)} lines" if _bkr else "🟡 Add BOOKMAKER_CF + BOOKMAKER_SESSID",
        "Action": "None"})

    # Heritage Sports: removed Aug 2 2026 -- confirmed dead end by two
    # independent investigations (this session + Replit's). Cloudflare
    # blocks every datacenter IP regardless of credentials; the only real
    # path is a paid aggregator subscription (SportsGameOdds/The Odds
    # API), a payment decision not made. Not a missing-secret issue.



    _green  = sum(1 for s in _src_statuses if "🟢" in s["Status"])
    _red    = sum(1 for s in _src_statuses if "🔴" in s["Status"])
    _yellow = sum(1 for s in _src_statuses if "🟡" in s["Status"])
    _grey   = sum(1 for s in _src_statuses if "⚪" in s["Status"])

    st.markdown(f"**{_green} connected** | {_red} failing | {_yellow} degraded | {_grey} not loaded")

    # Grouped-by-role display, healthy sources collapsed by default --
    # a flat 80-row table (all of it, every load) is the "noise" a
    # bettor doesn't need; what to actually look at is whatever isn't
    # green. Keyword match against a small explicit map first, falls
    # back to "Prop & Book Feeds" (the largest, lowest-stakes bucket)
    # for anything not explicitly classified rather than dropping it.
    _SRC_ROLE_MAP = {
        "pinnacle": "Core Lines & Sharp Signals", "circa": "Core Lines & Sharp Signals",
        "scanbet": "Core Lines & Sharp Signals",
        "ev sharps": "Core Lines & Sharp Signals", "oddsapi": "Core Lines & Sharp Signals",
        "oddspapi": "Core Lines & Sharp Signals", "bookmaker.eu": "Core Lines & Sharp Signals",
        "heritage sports": "Core Lines & Sharp Signals", "ev line movement": "Core Lines & Sharp Signals",
        "prizepicks": "Prop & Book Feeds", "underdog": "Prop & Book Feeds",
        "parlayplay": "Prop & Book Feeds", "pick6": "Prop & Book Feeds",
        "bovada": "Prop & Book Feeds", "fanduel": "Prop & Book Feeds",
        "injuries": "Context & Public Signals", "covers": "Context & Public Signals",
        "kalshi": "Context & Public Signals", "polymarket": "Context & Public Signals",
        "action network": "Context & Public Signals", "statmuse": "Context & Public Signals",
        "oddsshark": "Context & Public Signals", "signal odds": "Context & Public Signals",
        "auto scraper": "Context & Public Signals", "auto-harvester": "Context & Public Signals",
    }
    def _src_role(name: str) -> str:
        nl = name.lower()
        for kw, role in _SRC_ROLE_MAP.items():
            if kw in nl:
                return role
        return "Prop & Book Feeds"

    _grouped = {"Core Lines & Sharp Signals": [], "Prop & Book Feeds": [], "Context & Public Signals": []}
    for s in _src_statuses:
        _grouped[_src_role(s["Source"])].append(s)

    for _role, _rows in _grouped.items():
        _pending   = [r for r in _rows if "⚪" in r["Status"]]
        _attempted = [r for r in _rows if "⚪" not in r["Status"]]
        _unhealthy = [r for r in _attempted if "🟢" not in r["Status"]]
        _healthy   = [r for r in _attempted if "🟢" in r["Status"]]
        if not _rows:
            continue
        if _attempted:
            st.markdown(f"**{_role}** ({len(_healthy)}/{len(_attempted)} healthy" +
                        (f" · {len(_pending)} not yet tried" if _pending else "") + ")")
        else:
            st.markdown(f"**{_role}** (all {len(_pending)} not yet tried — load a board first)")
        if _unhealthy:
            st.markdown(_bc_df_html(pd.DataFrame([{k: str(v) for k, v in r.items()} for r in _unhealthy])), unsafe_allow_html=True)
        elif _attempted:
            st.caption("✅ All healthy")
        if _healthy:
            with st.expander(f"Show {len(_healthy)} healthy source(s) in this group"):
                st.markdown(_bc_df_html(pd.DataFrame([{k: str(v) for k, v in r.items()} for r in _healthy])), unsafe_allow_html=True)

    # ── Confidence Calibration Engine ─────────────────────────────────
    # Real self-diagnostic: are the model's stated probabilities matching
    # actual outcomes? Built from actual resolved history + the real
    # signal_performance log, nothing invented. Every number below is
    # gated on a minimum sample size (15) -- shows "not enough data yet"
    # instead of a real-looking number built on too few bets, the exact
    # trap flagged in the earlier one-off calibration review (Elite tier's
    # -13.3pp gap was real but only n=14, too small to fully trust yet).
    st.markdown("### 🎯 Confidence Calibration Engine")
    _cal_min_n = 15
    _cal_hist = [
        h for h in st.session_state.get("history", [])
        if h.get("outcome") in ("WIN", "LOSS") and h.get("prob") is not None
    ]
    if not _cal_hist:
        st.caption("No resolved bets with a real stated probability yet — calibration needs actual settled history.")
    else:
        _cal_last_ts = max((h.get("timestamp", "") for h in _cal_hist), default="")
        st.caption(f"Based on {len(_cal_hist)} resolved bets with a real stated probability (of {len(st.session_state.get('history', []))} total logged). Most recent resolved bet: {_cal_last_ts or 'unknown'}.")

        # 1. Tier calibration table
        with st.expander("Tier Calibration", expanded=True):
            _cal_tier_rows = []
            for _tier_name in ("SOVEREIGN", "ELITE", "APPROVED", "LEAN"):
                _tier_bets = [h for h in _cal_hist if h.get("tier") == _tier_name]
                _n = len(_tier_bets)
                if _n < _cal_min_n:
                    _cal_tier_rows.append({"Tier": _tier_name, "N": _n, "Actual Win%": "—", "Stated Prob%": "—", "Gap": f"not enough data yet (n={_n}, needs {_cal_min_n}+)"})
                    continue
                _actual_wr = sum(1 for h in _tier_bets if h["outcome"] == "WIN") / _n * 100
                _stated_avg = sum(float(h.get("prob", 0) or 0) for h in _tier_bets) / _n * 100
                _gap = _actual_wr - _stated_avg
                _cal_tier_rows.append({
                    "Tier": _tier_name, "N": _n,
                    "Actual Win%": f"{_actual_wr:.1f}%", "Stated Prob%": f"{_stated_avg:.1f}%",
                    "Gap": f"{_gap:+.1f}pp" + (" ⚠️ overconfident" if _gap < -5 else " ⚠️ underconfident" if _gap > 10 else ""),
                })
            st.markdown(_bc_df_html(pd.DataFrame(_cal_tier_rows)), unsafe_allow_html=True)

        # 2. Probability-bucket calibration curve
        with st.expander("Probability-Bucket Calibration", expanded=True):
            _cal_buckets = [(0.0, 0.50), (0.50, 0.55), (0.55, 0.60), (0.60, 0.65), (0.65, 0.70), (0.70, 1.01)]
            _cal_bucket_rows = []
            for _lo, _hi in _cal_buckets:
                _b_bets = [h for h in _cal_hist if _lo <= float(h.get("prob", 0) or 0) < _hi]
                _n = len(_b_bets)
                _label = f"{_lo*100:.0f}–{min(_hi,1.0)*100:.0f}%"
                if _n < _cal_min_n:
                    _cal_bucket_rows.append({"Stated Range": _label, "N": _n, "Actual Win%": "—", "Note": f"not enough data yet (n={_n})"})
                    continue
                _actual_wr = sum(1 for h in _b_bets if h["outcome"] == "WIN") / _n * 100
                _mid = (_lo + min(_hi, 1.0)) / 2 * 100
                _diff = _actual_wr - _mid
                _cal_bucket_rows.append({
                    "Stated Range": _label, "N": _n, "Actual Win%": f"{_actual_wr:.1f}%",
                    "Note": f"{_diff:+.1f}pp vs bucket midpoint",
                })
            st.markdown(_bc_df_html(pd.DataFrame(_cal_bucket_rows)), unsafe_allow_html=True)

        # 3. Brier score -- overall + last-20 rolling, so a real
        # improving/degrading trend is visible without inventing a
        # smoother time series than the data actually supports.
        with st.expander("Brier Score", expanded=True):
            def _cal_brier(bets):
                if not bets:
                    return None
                return sum((float(h.get("prob", 0) or 0) - (1.0 if h["outcome"] == "WIN" else 0.0)) ** 2 for h in bets) / len(bets)
            _brier_all = _cal_brier(_cal_hist)
            _brier_recent = _cal_brier(_cal_hist[-20:]) if len(_cal_hist) >= _cal_min_n else None
            _cal_b1, _cal_b2 = st.columns(2)
            with _cal_b1:
                st.metric(f"Overall (n={len(_cal_hist)})", f"{_brier_all:.4f}" if _brier_all is not None else "—",
                          help="0.25 = coin-flip-equivalent, 0 = perfect, lower is better")
            with _cal_b2:
                st.metric(f"Last 20 resolved", f"{_brier_recent:.4f}" if _brier_recent is not None else "not enough data yet",
                          delta=(f"{_brier_recent - _brier_all:+.4f} vs overall" if _brier_recent is not None else None),
                          delta_color="inverse")

        # 4. Signal activation audit -- from the real signal_performance
        # log (separate Gist key from history), not invented. Confirms
        # whether each tracked signal is genuinely contributing to
        # tracked outcomes or structurally dead in the current pipeline.
        with st.expander("Signal Activation Audit", expanded=False):
            try:
                _cal_sigperf = load_from_gist("signal_performance", None) or []
                if not _cal_sigperf:
                    st.caption("No signal_performance log found yet.")
                else:
                    _cal_sig_keys = sorted({k for r in _cal_sigperf for k in r.keys() if k.startswith(("base_", "defense_", "location_", "back_to_back", "sharp_", "weather_", "blowout_", "usage_", "pace_"))})
                    _sig_rows = []
                    for _sk in _cal_sig_keys:
                        _active = [r for r in _cal_sigperf if r.get(_sk) is True or r.get(_sk) == 1]
                        _inactive = [r for r in _cal_sigperf if not (r.get(_sk) is True or r.get(_sk) == 1)]
                        _n_active = len(_active)
                        if _n_active < _cal_min_n:
                            _sig_rows.append({"Signal": _sk, "N Active": _n_active, "Win% Active": "—", "Win% Inactive": "—", "Lift": f"not enough activations yet (n={_n_active})"})
                            continue
                        _wr_active = sum(r.get("win", 0) for r in _active) / _n_active * 100
                        _wr_inactive = sum(r.get("win", 0) for r in _inactive) / len(_inactive) * 100 if _inactive else 0
                        _sig_rows.append({
                            "Signal": _sk, "N Active": _n_active,
                            "Win% Active": f"{_wr_active:.1f}%", "Win% Inactive": f"{_wr_inactive:.1f}%",
                            "Lift": f"{_wr_active - _wr_inactive:+.1f}pp",
                        })
                    st.markdown(_bc_df_html(pd.DataFrame(_sig_rows)), unsafe_allow_html=True)
            except Exception:
                _logger.debug("Signal activation audit failed silently")

    # ── System Metrics Mini-Dashboard -- real values only, recomputed
    # fresh here rather than reusing variables from the Calibration Engine
    # above (which may not exist if that section took its "not enough
    # data" early-exit branch). Every number traces to something already
    # tracked elsewhere in the app -- nothing new invented.
    st.markdown("### 📟 System Metrics")
    try:
        _sm_cal_hist = [
            h for h in st.session_state.get("history", [])
            if h.get("outcome") in ("WIN", "LOSS") and h.get("prob") is not None
        ]
        _sm_sigperf = load_from_gist("signal_performance", None) or []
        _sm_active_signals = 0
        if _sm_sigperf:
            _sm_sig_keys = {k for r in _sm_sigperf for k in r.keys() if k.startswith(("base_", "defense_", "location_", "back_to_back", "sharp_", "weather_", "blowout_", "usage_", "pace_"))}
            for _sk in _sm_sig_keys:
                if sum(1 for r in _sm_sigperf if r.get(_sk) is True or r.get(_sk) == 1) >= 15:
                    _sm_active_signals += 1
        _sm_timings = st.session_state.get("fetch_timings", {})
        _sm_avg_refresh = (sum(t.get("time", 0) for t in _sm_timings.values()) / len(_sm_timings)) if _sm_timings else None
        _sm_gist_writes = st.session_state.get("gist_last_write", {})
        _sm_last_sync = max(_sm_gist_writes.values()) if _sm_gist_writes else None
        _sm_last_sync_str = datetime.fromtimestamp(_sm_last_sync).strftime("%H:%M:%S") if _sm_last_sync else "no sync yet"

        _sm_c1, _sm_c2, _sm_c3, _sm_c4 = st.columns(4)
        with _sm_c1:
            # Trend cue: real delta vs the last time this ran this session,
            # not a fabricated direction. Sample count only ever grows or
            # holds steady within a session, so no color inversion needed.
            _sm_prev_samples = st.session_state.get("_sm_prev_cal_samples")
            _sm_samples_delta = (len(_sm_cal_hist) - _sm_prev_samples) if _sm_prev_samples is not None else None
            st.session_state["_sm_prev_cal_samples"] = len(_sm_cal_hist)
            st.metric("Calibration Samples", len(_sm_cal_hist),
                      delta=(f"+{_sm_samples_delta}" if _sm_samples_delta else None),
                      help="Resolved bets with a real stated probability")
        with _sm_c2:
            _sm_prev_active = st.session_state.get("_sm_prev_active_signals")
            _sm_active_delta = (_sm_active_signals - _sm_prev_active) if _sm_prev_active is not None else None
            st.session_state["_sm_prev_active_signals"] = _sm_active_signals
            st.metric("Active Signals", f"{_sm_active_signals}/{len(_sm_sig_keys) if _sm_sigperf else 0}" if _sm_sigperf else "—",
                      delta=(_sm_active_delta if _sm_active_delta else None),
                      help="Signals with 15+ real activations in the signal_performance log")
        with _sm_c3:
            # Threshold alert: flags an average fetch time above 3s. The
            # 20s total-wall-time "slow" threshold already exists elsewhere
            # in this file (System Health Gauge) for the combined load --
            # 3s per-source average is a new, separate threshold chosen for
            # this per-source metric, not copied from that existing one.
            _sm_prev_refresh = st.session_state.get("_sm_prev_avg_refresh")
            _sm_refresh_delta = (round(_sm_avg_refresh - _sm_prev_refresh, 1) if (_sm_prev_refresh is not None and _sm_avg_refresh is not None) else None)
            if _sm_avg_refresh is not None:
                st.session_state["_sm_prev_avg_refresh"] = _sm_avg_refresh
            _sm_refresh_slow = _sm_avg_refresh is not None and _sm_avg_refresh > 3.0
            st.metric("Avg Refresh Time", (f"⚠️ {_sm_avg_refresh:.1f}s" if _sm_refresh_slow else f"{_sm_avg_refresh:.1f}s") if _sm_avg_refresh is not None else "—",
                      delta=(f"{_sm_refresh_delta:+.1f}s" if _sm_refresh_delta is not None else None),
                      delta_color="inverse",
                      help="Average across all sources in this session's fetch_timings. Alert thresholds: >3s average here, >20s total wall-time in the System Health Gauge above.")
        with _sm_c4:
            st.metric("Last Gist Sync", _sm_last_sync_str, help="Most recent successful write across all tracked data types this session")
    except Exception:
        _logger.debug("System Metrics Mini-Dashboard failed silently")

    # ── Slowest Fetch Slots (real per-slot timing, not just the average) ──
    # fetch_timings has captured per-slot elapsed time on every board load
    # this whole session (see _fetch_parallel's _timed() wrapper) but it
    # was never actually displayed anywhere -- only ever rolled up into an
    # average. Total board-load wall time is bounded by the SLOWEST slot in
    # a wave, not the average, so this is the real, direct answer to "what
    # to speed up next" instead of guessing at which sources might be slow.
    try:
        _sf_timings = st.session_state.get("fetch_timings", {})
        if _sf_timings:
            _sf_sorted = sorted(_sf_timings.items(), key=lambda kv: kv[1].get("time", 0), reverse=True)[:15]
            with st.expander(f"🐢 Slowest Fetch Slots ({len(_sf_timings)} tracked this session)", expanded=False):
                for _sf_name, _sf_info in _sf_sorted:
                    _sf_t = _sf_info.get("time", 0)
                    _sf_status = _sf_info.get("status", "")
                    _sf_color = "#e04040" if _sf_t > 15 else ("#f5a623" if _sf_t > 5 else "#6a7a8a")
                    st.markdown(
                        f'<div style="display:flex;justify-content:space-between;padding:3px 0;font-size:0.85rem;">'
                        f'<span>{_sf_name}</span>'
                        f'<span style="color:{_sf_color};font-weight:600;">{_sf_t:.1f}s</span>'
                        f'</div>',
                        unsafe_allow_html=True
                    )
                    if _sf_status.startswith("❌"):
                        st.caption(f"　{_sf_status}")
    except Exception:
        _logger.debug("Slowest Fetch Slots table failed silently")

    # ── Model Self-Learning (plain-language) ──────────────────────────
    # Surfaces the same weekly_audit.py weight-adjustment run that used
    # to only be visible in a GitHub Issue -- written for a non-technical
    # reader, not a statistics audience. No jargon (no "Wilson CI", no
    # "clamped to +/-30%") -- just what changed and why, in plain terms.
    st.markdown("### 🧠 Model Self-Learning")
    try:
        _sl_plain_names = {
            "base": "how the player's average compares to the betting line",
            "defense": "how weak the opponent's defense is",
            "location": "whether the player is at home",
            "rest": "back-to-back game fatigue",
            "pace": "game pace",
            "usage": "recent usage boost",
            "blowout": "blowout risk",
            "sharp": "sharp money movement",
        }
        _sl_audit = load_from_gist("weekly_audit", None) or {}
        _sl_wt = _sl_audit.get("weight_adjustments", {})
        _sl_log = load_from_gist("weight_adjustment_log", None) or []

        if not _sl_wt and not _sl_log:
            st.caption("This runs automatically every Monday and hasn't checked in yet.")
        else:
            _sl_checked = _sl_wt.get("sports_checked", [])
            _sl_eligible = {e["sport"]: e["n"] for e in _sl_wt.get("sports_eligible", [])}
            _sl_run_date = _sl_audit.get("run_date", "unknown date")
            st.caption(f"Last checked: {_sl_run_date}. This looks at your settled bets every week and only "
                       f"changes anything when a pattern is clear and consistent — not from a lucky or unlucky streak.")

            for sport in _sl_checked:
                if sport not in _sl_eligible:
                    st.caption(f"**{sport}**: still collecting bets — needs 100 settled bets before it can check for patterns.")
                else:
                    _n = _sl_eligible[sport]
                    _sport_changes = [e for e in _sl_log if e.get("sport") == sport]
                    if not _sport_changes:
                        st.caption(f"**{sport}**: has enough bets ({_n}) to check, but hasn't found a clear enough pattern yet to change anything.")
                    else:
                        with st.expander(f"**{sport}**: adjusted {len(_sport_changes)} time(s) — {_n} bets checked"):
                            for e in sorted(_sport_changes, key=lambda x: x.get("timestamp",""), reverse=True)[:10]:
                                _plain_sig = _sl_plain_names.get(str(e.get("signal","")).lower(), e.get("signal","this signal"))
                                _direction = "trusted **more**" if e.get("action") == "INCREASE" else "trusted **less**"
                                st.markdown(
                                    f"- **{_plain_sig.capitalize()}** is now {_direction} — it's been right "
                                    f"{e.get('win_rate', 0):.0%} of the time over {e.get('n', '?')} bets "
                                    f"(normal luck alone would rarely produce that)."
                                )
    except Exception:
        st.caption("Model self-learning status unavailable right now.")

    # ── Third-Party Model Comparison (plain-language) ─────────────────
    # Surfaces betcouncil_third_party_calibration.json, which was being
    # computed daily (real grading against the same ground-truth resolvers
    # BetCouncil's own board uses) but never shown anywhere. Real names,
    # real sample-size caveats -- not editorializing about whether any
    # number is "good," just showing what's actually there honestly.
    st.markdown("### 📡 Third-Party Model Comparison")
    try:
        _tpc = load_from_gist("third_party_calibration", None) or {}
        _tpc_display_names = {
            "favoredprops": "FavoredProps", "draftedge": "DraftEdge", "dimers": "Dimers",
            "covers": "Covers",
            "dk_most_bet": "DK Most Bet",
        }
        if not _tpc:
            st.caption("No comparison data yet.")
        else:
            st.caption("Same real games, same grading logic BetCouncil uses on its own board — "
                       "not a different methodology, so these are directly comparable. Sources with "
                       "few graded picks so far are marked as too small to read into yet.")
            for _key, _label in _tpc_display_names.items():
                _stats = _tpc.get(_key, {})
                _gradable = _stats.get("gradable", 0)
                _wins = _stats.get("wins", 0)
                _losses = _stats.get("losses", 0)
                if _gradable < 30:
                    st.caption(f"**{_label}**: only {_gradable} graded picks so far — too small to read into yet.")
                else:
                    _wr = _wins / _gradable if _gradable else 0
                    st.markdown(f"**{_label}**: {_wr:.1%} hit rate over {_gradable:,} graded picks "
                                f"({_wins:,}-{_losses:,})")
    except Exception:
        st.caption("Third-party comparison data unavailable right now.")

    # ── Harvester Health Monitor ─────────────────────────────────────
    # Checks actual Gist captured_at ages against each source's expected
    # refresh interval (pulled from the harvester JS's own throttle values),
    # so a silently-dead harvester (e.g. Covers 404ing since its site
    # restructured) surfaces the same day instead of weeks later.
    st.markdown("### 🌐 Harvester Health Monitor")
    try:
        from fetchers import check_harvester_health, get_harvester_alerts
        _hh_sport = st.session_state.get("last_sport", "NBA")
        _hh_results = check_harvester_health(_hh_sport)
        _hh_alerts = get_harvester_alerts(_hh_sport)
        if _hh_alerts:
            _sharp_dead = [a["name"] for a in _hh_alerts if a["tier"] == "sharp"]
            _other_dead = [a["name"] for a in _hh_alerts if a["tier"] != "sharp"]
            if _sharp_dead:
                st.error(f"🔴 Sharp-tier harvester(s) dead: {', '.join(_sharp_dead)} — check the browser tab / Gist push for these.")
            if _other_dead:
                st.warning(f"🟡 Harvester(s) newly dead: {', '.join(_other_dead)}")
        else:
            st.success("No harvester newly went dark since last check.")
        _hh_green  = sum(1 for r in _hh_results if r["status"] == "🟢")
        _hh_yellow = sum(1 for r in _hh_results if r["status"] == "🟡")
        _hh_red    = sum(1 for r in _hh_results if r["status"] == "🔴")
        _hh_grey   = sum(1 for r in _hh_results if r["status"] == "⚫")
        st.caption(f"{_hh_green} fresh | {_hh_yellow} stale | {_hh_red} dead | {_hh_grey} never seen — out of {len(_hh_results)} tracked harvesters for {_hh_sport}")
        with st.expander("Full harvester health detail"):
            st.markdown(_bc_df_html(pd.DataFrame(_hh_results)), unsafe_allow_html=True)
    except Exception as _hh_err:
        st.caption(f"Harvester health check unavailable this load: {str(_hh_err)[:100]}")

    # ── Full-Board Accuracy (daily grading, separate from personal bets) ──
    # Runs automatically every day via GitHub Actions (daily_board_grading.py),
    # grading the model's FULL recommendation set -- 30-50+ picks/day -- against
    # real final scores, regardless of what you actually bet. Kept completely
    # separate from your bankroll/ROI ledger. Surfaced here because it answers
    # a real question that wasn't visible anywhere before: is the model's
    # accuracy being checked on picks you didn't place, not just the ones you did.
    st.markdown("### 📅 Full-Board Accuracy (daily, all picks — not just bets placed)")
    try:
        _fba_props = load_from_gist("board_grading_history", None) or {}
        _fba_games = load_from_gist("game_board_grading_history", None) or {}

        def _fba_summarize(daily_dict):
            all_picks = []
            for _d, _p in daily_dict.items():
                if isinstance(_p, list):
                    all_picks.extend(_p)
            graded = [p for p in all_picks if p.get("outcome") in ("WIN", "LOSS")]
            wins = sum(1 for p in graded if p.get("outcome") == "WIN")
            return len(all_picks), len(graded), (wins / len(graded) * 100) if graded else 0, graded

        _fba_p_total, _fba_p_graded, _fba_p_hr, _fba_p_recs = _fba_summarize(_fba_props)
        _fba_g_total, _fba_g_graded, _fba_g_hr, _fba_g_recs = _fba_summarize(_fba_games)

        _fba_col1, _fba_col2 = st.columns(2)
        with _fba_col1:
            st.metric("Props hit rate", f"{_fba_p_hr:.1f}%" if _fba_p_graded else "—",
                       help=f"{_fba_p_graded} graded picks across {len(_fba_props)} days")
        with _fba_col2:
            st.metric("Game lines hit rate", f"{_fba_g_hr:.1f}%" if _fba_g_graded else "—",
                       help=f"{_fba_g_graded} graded picks across {len(_fba_games)} days")

        with st.expander("Breakdown by tier"):
            for _label, _recs in [("Props", _fba_p_recs), ("Game Lines", _fba_g_recs)]:
                st.caption(f"**{_label}**")
                _tier_stats = {}
                for p in _recs:
                    t = p.get("tier", "?")
                    _tier_stats.setdefault(t, {"w": 0, "n": 0})
                    _tier_stats[t]["n"] += 1
                    if p.get("outcome") == "WIN":
                        _tier_stats[t]["w"] += 1
                for t, s in sorted(_tier_stats.items(), key=lambda x: -x[1]["n"]):
                    st.caption(f"　{t}: {s['w']}/{s['n']} = {s['w']/s['n']*100:.1f}%")
    except Exception as _fba_err:
        st.caption(f"Full-board accuracy unavailable this load: {str(_fba_err)[:100]}")

    # ── Line Shop source availability (moved here 2026-07-12 — was a
    # developer-facing debug caption on the Line Shop tab itself, which
    # made a normal night look broken to a bettor just comparing prices) ──
    _ls_flags = st.session_state.get("_ls_source_flags")
    if _ls_flags:
        st.markdown(f"### 🛒 Line Shop Data Sources ({_ls_flags['sport']})")
        _ls_flag_items = [(k, v) for k, v in _ls_flags.items() if k != "sport"]
        _ls_flag_cols = st.columns(len(_ls_flag_items))
        for _i, (_k, _v) in enumerate(_ls_flag_items):
            _ls_flag_cols[_i].metric(_k, "✅" if _v else "❌")

    # ── Fetch Function Health (all 240+ fetch_* functions, not just the
    # 45 tracked in HARVESTER_REGISTRY) ─────────────────────────────────
    # Auto-instrumented in fetchers.py — every fetch_* call is tracked with
    # zero per-function wiring. Catches: silent failures (bare except
    # swallowing an error with nothing surfacing it), sources that only
    # ever return empty, and functions that are defined but never called
    # this session (which may be off-season/feature-gated, not broken —
    # shown for visibility, not as an automatic delete list).
    st.markdown("### 🩺 Fetch Function Health (all sources)")
    try:
        from fetchers import get_fetch_health_report
        _fh_report = get_fetch_health_report()
        _fh_counts = {}
        for _r in _fh_report:
            _fh_counts[_r["status"]] = _fh_counts.get(_r["status"], 0) + 1
        st.caption(
            f"{_fh_counts.get('OK',0)} OK | "
            f"{_fh_counts.get('DEAD',0)} dead (100% error rate) | "
            f"{_fh_counts.get('ERRORING',0)} erroring | "
            f"{_fh_counts.get('EMPTY_ONLY',0)} empty-only | "
            f"{_fh_counts.get('NEVER_CALLED',0)} never called this session "
            f"— out of {len(_fh_report)} total fetch functions"
        )
        _fh_dead_or_erroring = [r for r in _fh_report if r["status"] in ("DEAD", "ERRORING")]
        if _fh_dead_or_erroring:
            st.error(
                "🔴 Actively failing this session: "
                + ", ".join(f'{r["name"]} ({r["error_rate"]:.0%} errors)' for r in _fh_dead_or_erroring)
            )
        with st.expander(f"Full fetch health detail ({len(_fh_report)} functions)"):
            st.markdown(_bc_df_html(pd.DataFrame(_fh_report)), unsafe_allow_html=True)
    except Exception as _fh_err:
        st.caption(f"Fetch health check unavailable this load: {str(_fh_err)[:100]}")


    # ── API Health Check ─────────────────────────────────────
    st.markdown("### 🔑 API Keys & Token Status")
    _hc_data = []
    _secrets_check = [
        ("ODDS_API_KEY",        "OddsAPI",       "Game lines + props"),
        ("ODDSPAPI_KEY",        "OddsPAPI",      "DK/FD/BetMGM/Pinnacle/Bet365"),
        ("PARLAY_API_KEY",      "ParlayAPI",     "Underdog/ParlayPlay props"),
        ("BALLSDONTLIE_API_KEY","BallsDontLie",  "NBA player stats"),
        ("SCRAPEOPS_KEY",       "ScrapeOps",     "PrizePicks proxy"),
        ("SCRAPERAPI_KEY",      "ScraperAPI",    "Backup proxy"),
        ("SCRAPEDO_KEY",        "Scrape.do",     "Backup proxy #2"),
        ("FIRECRAWL_KEY",       "Firecrawl",     "Covers consensus"),
        ("GITHUB_TOKEN",        "GitHub",        "Gist read/write"),
        ("GITHUB_GIST_ID",      "GitHub Gist",   "Auto scraper data"),
    ]
    for _hc_key, _hc_display, _hc_purpose in _secrets_check:
        _hc_val = st.secrets.get(_hc_key, "")
        _hc_status = "🟢 Set" if _hc_val else "🔴 Missing"
        _hc_data.append({"Service": _hc_display, "Status": _hc_status, "Purpose": _hc_purpose})
    st.markdown(_bc_df_html(_hc_data, ["Service", "Status", "Purpose"]), unsafe_allow_html=True)

    st.markdown("### 🍪 Session & Cookie Status")
    _ck_data = [
        {"Service": "ParlayPlay", "Secret": "PARLAYPLAY_SESSION",
         "Status": "🟢 Set" if st.secrets.get("PARLAYPLAY_SESSION","") else "🔴 Expired — refresh in Secrets",
         "Refresh Interval": "Every ~2 weeks"},
        {"Service": "Auto Scraper (Gist)", "Secret": "auto_scraped_props.json",
         "Status": "🟢 Loaded" if st.session_state.get("pp_source","") == "gist_scraper" else "🟡 Run scraper on PC",
         "Refresh Interval": "Daily — run betcouncil_auto_scraper.py"},
        {"Service": "ScrapeOps Proxy", "Secret": "SCRAPEOPS_KEY",
         "Status": "🔴 Exhausted" if st.session_state.get("scrapeops_exhausted") else "🟢 Available",
         "Refresh Interval": "Monthly reset"},
    ]
    st.markdown(_bc_df_html(_ck_data, ["Service", "Secret", "Status", "Refresh Interval"]), unsafe_allow_html=True)

    # ── Performance Telemetry ─────────────────────────────
    _telem = st.session_state.get("bc_telemetry", {})
    if _telem:
        st.markdown("### ⏱️ Performance")
        _rows = []
        for _s, _d in sorted(_telem.items(), key=lambda x: -x[1].get("last",0)):
            _avg = round(_d["total"] / max(_d["runs"],1), 2)
            _rows.append({"Stage":_s,"Last":f'{_d["last"]:.2f}s',"Avg":f'{_avg:.2f}s',"Max":f'{_d["max"]:.2f}s',"Runs":_d["runs"],"Status":"🔴 SLOW" if _d["last"]>5 else "🟡 OK" if _d["last"]>2 else "🟢 FAST"})
        st.markdown(_bc_df_html(pd.DataFrame(_rows)), unsafe_allow_html=True)
        _slow=[r["Stage"] for r in _rows if "SLOW" in r["Status"]]
        if _slow: st.warning(f"🐌 Slow: {chr(44).join(_slow)}")
    else:
        st.caption("⏱️ Performance telemetry activates after first board load.")
    st.markdown("---")

    # ── MLB ML Divisor Diagnostic (real, 2026-08-18) ──────────────────
    # Flags every MLB game this board load where the sigmoid formula
    # produced an extreme win probability (>80% or <20%), with the real
    # power_diff and divisor that produced it -- concrete evidence for
    # whether _ml_divisor=1.5 needs real recalibration, not a guess.
    _ml_diag = st.session_state.get("_ml_divisor_diag", [])
    if _ml_diag:
        with st.expander(f"🔬 MLB ML Divisor Diagnostic — {len(_ml_diag)} extreme probability(s) this session", expanded=False):
            st.caption("Real power_diff/h_fair values behind any MLB moneyline edge flagged as extreme. Use this to judge whether the 1.5 divisor is producing realistic probabilities for the actual power-rating gaps seen today.")
            for _d in reversed(_ml_diag):
                st.caption(f"**{_d['matchup']}** — power_diff={_d['power_diff']:.1f} (÷{_d['divisor']}) → h_fair={_d['h_fair']:.1%}")

    # ── VSiN Intelligence Panel ───────────────────────────────
    st.markdown("### 🎯 VSiN Intelligence")
    _sport_vsin = st.session_state.get("last_sport", "MLB")
    _vsin = fetch_vsin_intelligence(_sport_vsin)
    _vsin_ts = _vsin.get("timestamp")

    if not _vsin.get("merged") and not _vsin.get("power_ratings"):
        st.caption("No VSiN data yet for this sport — the automated VSiN Splits workflow runs on its own schedule; check back after its next run.")
    else:
        _v1, _v2, _v3, _v4 = st.columns(4)
        with _v1:
            st.metric("Games w/ Lines", len(_vsin.get("merged", [])))
        with _v2:
            st.metric("⚡ RLM Alerts", len(_vsin.get("rlm_alerts", [])))
        with _v3:
            st.metric("Teams Rated", len(_vsin.get("power_ratings", [])))
        with _v4:
            if _vsin_ts:
                st.metric("Last Updated", _vsin_ts[11:16] + " UTC")
            else:
                st.metric("Last Updated", "—")

        # RLM Alerts
        if _vsin.get("rlm_alerts"):
            st.markdown("**⚡ Reverse Line Movement Alerts**")
            _rlm_rows = []
            for _g in _vsin["rlm_alerts"]:
                _r = _g.get("rlm", {})
                _rlm_rows.append({
                    "Game": f"{_g.get('away_team','?')} @ {_g.get('home_team','?')}",
                    "Time": _g.get("game_time", ""),
                    "Direction": _r.get("rlm_direction", ""),
                    "Strength": _r.get("rlm_strength", ""),
                    "Public %": f"{_r.get('public_pct_vs_line',0):.0f}%",
                })
            import pandas as pd
            st.markdown(_bc_df_html(pd.DataFrame(_rlm_rows)), unsafe_allow_html=True)

        # ATS Signals
        _ats = _vsin.get("ats_signals", {})
        if _ats.get("ats_hot") or _ats.get("ats_cold"):
            _ac1, _ac2 = st.columns(2)
            with _ac1:
                if _ats.get("ats_hot"):
                    st.success("ATS Hot (>=8% ROI): " + ", ".join(_ats["ats_hot"]))
                if _ats.get("over_lean"):
                    st.info("**Over Lean** (58%+): " + ", ".join(_ats["over_lean"]))
            with _ac2:
                if _ats.get("ats_cold"):
                    st.error("ATS Cold (<=-12% ROI): " + ", ".join(_ats["ats_cold"]))
                if _ats.get("under_lean"):
                    st.info("Under Lean (<=42%): " + ", ".join(_ats.get("under_lean", [])))

        # Top Power Ratings
        if _vsin.get("power_ratings"):
            with st.expander("📊 Makinen Power Rankings (Top 10)"):
                _pr_rows = []
                for _t in _vsin["power_ratings"][:10]:
                    _pr_rows.append({
                        "Rank": _t.get("composite_rank"),
                        "Team": _t.get("team"),
                        "PR": _t.get("power_rating"),
                        "Eff Runs": _t.get("eff_runs"),
                        "Starter": _t.get("starter_rating"),
                        "Bullpen": _t.get("bullpen_rating"),
                    })
                import pandas as pd
                st.markdown(_bc_df_html(pd.DataFrame(_pr_rows)), unsafe_allow_html=True)

        # Makinen Game Projections
        if _vsin.get("makinen"):
            with st.expander(f"📈 Makinen Game Projections ({len(_vsin['makinen'])} games)"):
                _mak_rows = []
                for _g in _vsin["makinen"]:
                    _mak_rows.append({
                        "Game": f"{_g.get('away_team','?')} @ {_g.get('home_team','?')}",
                        "Time": _g.get("game_time", ""),
                        "Away Proj": _g.get("away_score_proj"),
                        "Home Proj": _g.get("home_score_proj"),
                        "Proj Total": _g.get("projected_total"),
                        "Eff Line": f"{_g.get('eff_line','')} {_g.get('eff_line_dir','')}",
                        "Favorite": _g.get("makinen_favorite", ""),
                        "Starter Δ": f"{_g.get('away_starter_rtg','?')} vs {_g.get('home_starter_rtg','?')}",
                    })
                import pandas as pd
                st.markdown(_bc_df_html(pd.DataFrame(_mak_rows)), unsafe_allow_html=True)

    st.markdown("---")

    st.markdown("### 🛡️ Daily Risk Controls")
    st.write(f"Max locks/day: {DAILY_RISK_CONTROLS['max_locks_per_day']}")
    st.write(f"Stop-loss: -{DAILY_RISK_CONTROLS['max_daily_loss_pct']:.0%}")
    st.write(f"Stop-win: +{DAILY_RISK_CONTROLS['stop_win_pct']:.0%}")
    can_bet_s, risk_msg_s = check_daily_risk_limits()
    if can_bet_s:
        st.success("\u2705 All risk controls green")
    else:
        st.error(f"\U0001f6d1 {risk_msg_s}")
    st.markdown("---")

    # ══════════════════════════════════════════════════════════
    # 🔍 BOARD AUDIT ENGINE — 6 automated output audits
    # Runs after every board load. Catches routing bugs,
    # coverage gaps, tier mismatches, and consistency failures
    # BEFORE you place a bet.
    # ══════════════════════════════════════════════════════════
    st.markdown("### 🔍 Board Audit Engine")
    st.caption("Automated output validation — audits routing, coverage, consistency, and tier integrity every board load.")

    _audit_board   = st.session_state.get("board_data", [])
    _audit_games   = st.session_state.get("game_analysis", [])
    _audit_locks   = st.session_state.get("locks", [])
    _audit_sport   = st.session_state.get("last_sport", "NBA")
    _audit_results = []  # list of {name, status, detail, severity}

    def _audit_pass(name, detail=""):
        return {"name": name, "status": "PASS", "detail": detail, "severity": "green"}
    def _audit_warn(name, detail=""):
        return {"name": name, "status": "WARN", "detail": detail, "severity": "yellow"}
    def _audit_fail(name, detail=""):
        return {"name": name, "status": "FAIL", "detail": detail, "severity": "red"}

    if not _audit_board:
        st.info("Load the board first to run audits.")
    else:
        _audit_cache_key = (id(_audit_board), len(_audit_board), len(_audit_games), len(_audit_locks), _audit_sport)
        _audit_cached = st.session_state.get("_audit_results_cache")
        if _audit_cached and _audit_cached.get("key") == _audit_cache_key:
            # Real fix (Copilot recommendation, verified accurate): these 13
            # audits previously recomputed unconditionally on every rerun
            # (Streamlit executes every tab block every rerun, regardless of
            # which tab is visually active). Now only recompute when the
            # underlying board/game/lock data has actually changed.
            _audit_results = _audit_cached["results"]
        else:
            # ── AUDIT 1: Board Consistency ──────────────────────────
            # Checks that the same player+prop shows the same edge
            # across Full Board, Best Bet Queue, and Lock of Day.
            _consistency_failures = []
            _board_lookup = {}
            for p in _audit_board:
                _key = (normalize_name(p.get("Player","")), p.get("Prop",""), p.get("Side",""))
                _board_lookup[_key] = round(float(p.get("Edge",0) or 0), 3)

            # Check queue top picks against board
            _queue_top = [p for p in _audit_board if p.get("Tier") in ("SOVEREIGN","ELITE")][:6]
            for qp in _queue_top:
                _qk = (normalize_name(qp.get("Player","")), qp.get("Prop",""), qp.get("Side",""))
                _board_edge = _board_lookup.get(_qk, 0)
                _queue_edge = round(float(qp.get("Edge",0) or 0), 3)
                if abs(_board_edge - _queue_edge) > 0.005:
                    _consistency_failures.append(
                        f"{qp.get('Player','')} {qp.get('Prop','')}: Queue={_queue_edge:.1%} Board={_board_edge:.1%}"
                    )

            # Check today's locked picks against board
            _today_str = date.today().strftime("%Y-%m-%d")
            _today_locks_a = [l for l in _audit_locks if l.get("timestamp","").startswith(_today_str)]
            for lk in _today_locks_a:
                _lk = (normalize_name(lk.get("player","")), lk.get("prop",""), lk.get("side","OVER"))
                _board_edge = _board_lookup.get(_lk)
                _lock_edge  = round(float(lk.get("edge",0) or 0), 3)
                if _board_edge is not None and abs(_board_edge - _lock_edge) > 0.01:
                    _consistency_failures.append(
                        f"LOCK: {lk.get('player','')} {lk.get('prop','')}: Lock={_lock_edge:.1%} Board={_board_edge:.1%}"
                    )

            if _consistency_failures:
                _audit_results.append(_audit_fail(
                    "Audit 1 — Board Consistency",
                    f"{len(_consistency_failures)} mismatch(es): " + " | ".join(_consistency_failures[:3])
                ))
            else:
                _audit_results.append(_audit_pass(
                    "Audit 1 — Board Consistency",
                    f"All {len(_queue_top)} queue picks + {len(_today_locks_a)} locks match board edges"
                ))

            # ── AUDIT 2: Market Coverage ────────────────────────────
            # Checks spread/total/ML coverage % for today's games.
            # Uses all games (including those without edge) for accurate coverage.
            # Flags if ML < 80% (likely routing failure like WNBA bug).
            _all_games_raw = st.session_state.get("raw_games_today", _audit_games)
            _cov_base = _all_games_raw if _all_games_raw else _audit_games
            if _cov_base:
                _n_games    = len(_cov_base)
                def _has_market(g, mtype):
                    # Check recommendations array for this market type
                    for rec in g.get("recommendations", []):
                        rt = (rec.get("type","") or "").upper()
                        if mtype == "ML" and "MONEYLINE" in rt:
                            return True
                        if mtype == "SPREAD" and "SPREAD" in rt:
                            return True
                        if mtype == "TOTAL" and ("TOTAL" in rt or "OVER" in rt or "UNDER" in rt):
                            return True
                    # Fallback: check direct keys
                    if mtype == "ML" and g.get("HomeML", g.get("home_ml", g.get("MLEdge","N/A"))) not in ("N/A",None,"",0):
                        return True
                    if mtype == "SPREAD" and g.get("Spread", g.get("spread", g.get("SpreadEdge","N/A"))) not in ("N/A",None,"",0):
                        return True
                    if mtype == "TOTAL" and g.get("Total", g.get("total", g.get("TotalEdge","N/A"))) not in ("N/A",None,"",0):
                        return True
                    return False
                _cov_spread = sum(1 for g in _cov_base if _has_market(g, "SPREAD")) / _n_games
                _cov_total  = sum(1 for g in _cov_base if _has_market(g, "TOTAL")) / _n_games
                _cov_ml     = sum(1 for g in _cov_base if _has_market(g, "ML")) / _n_games
                # MLB and WNBA both have thinner odds coverage and fewer
                # games/day than NBA/NFL/NHL, and the ML "coverage" number
                # here is really an edge-qualification rate (a MONEYLINE
                # recommendation only gets built if best_ml_edge >= 0.02),
                # not a measure of missing raw odds data. Confirmed: a game
                # can have complete, real odds and legitimately not clear
                # that threshold. Lower thresholds for both, and relabeled
                # below so this doesn't read as a routing failure when it's
                # actually just normal edge-detection variance.
                _spread_threshold = 0.70 if _audit_sport in ("MLB","WNBA") else 0.80
                _total_threshold  = 0.70 if _audit_sport in ("MLB","WNBA") else 0.80
                _ml_threshold     = 0.55 if _audit_sport in ("MLB","WNBA") else 0.80
                _cov_issues = []
                if _cov_spread < _spread_threshold: _cov_issues.append(f"Spread {_cov_spread:.0%}")
                if _cov_total  < _total_threshold:  _cov_issues.append(f"Total {_cov_total:.0%}")
                if _cov_ml     < _ml_threshold:     _cov_issues.append(f"ML {_cov_ml:.0%} (few games clearing 2% edge threshold)")
                if _cov_issues:
                    _audit_results.append(_audit_fail(
                        "Audit 2 — Market Coverage",
                        f"{_n_games} games | Low: {', '.join(_cov_issues)} (threshold >80%)"
                    ))
                else:
                    _audit_results.append(_audit_pass(
                        "Audit 2 — Market Coverage",
                        f"{_n_games} games | Spread {_cov_spread:.0%} Total {_cov_total:.0%} ML {_cov_ml:.0%}"
                    ))
            else:
                _audit_results.append(_audit_warn("Audit 2 — Market Coverage", "No game analysis data"))

            # ── AUDIT 3: Source Health ──────────────────────────────
            # Checks records returned per source and flags low counts.
            _src_counts = {}
            for p in _audit_board:
                _src = p.get("Source") or p.get("source") or "Unknown"
                _src_counts[_src] = _src_counts.get(_src, 0) + 1
            _src_issues = []
            _timings = st.session_state.get("fetch_timings", {})
            _expected_failures = {"rw_injuries", "prizepicks"}  # blocked from cloud IPs
            for src, info in _timings.items():
                if info.get("status","").startswith("❌") and src not in _expected_failures:
                    _src_issues.append(f"{src}: {info['status'][:40]}")
            _errors = st.session_state.get("errors",[])
            _recent_errors = [e for e in _errors[-20:] if e.get("source") not in ("",None)]
            if _src_issues or len(_recent_errors) > 3:
                _audit_results.append(_audit_warn(
                    "Audit 3 — Source Health",
                    f"{len(_src_issues)} fetch failure(s) | {len(_recent_errors)} recent errors | Props by source: {dict(list(_src_counts.items())[:4])}"
                ))
            else:
                _audit_results.append(_audit_pass(
                    "Audit 3 — Source Health",
                    f"{len(_src_counts)} source(s) | {len(_audit_board)} total props | {len(_recent_errors)} errors"
                ))

            # ── AUDIT 4: Tier Integrity ─────────────────────────────
            # Verifies each prop's tier matches what get_game_tier/get_tier
            # would assign given its edge. Catches stale tier assignments.
            _tier_mismatches = []
            for p in _audit_board[:50]:
                _p_edge = abs(float(p.get("Edge",0) or 0))
                _p_sport = p.get("Sport", _audit_sport)
                _p_tier = p.get("Tier","LEAN")
                _expected = _get_cal_tier(_p_edge, _p_sport)
                # Allow confidence-based downgrades — not a real mismatch
                _conf = p.get("ProjConfidence", 100)
                _conf_downgrade = (
                    (_conf < 40 and _expected in ("SOVEREIGN","ELITE") and _p_tier == "APPROVED") or
                    (_conf < 60 and _expected == "SOVEREIGN" and _p_tier == "ELITE")
                )
                if _expected != _p_tier and abs(_p_edge) > 0.005 and not _conf_downgrade:
                    _tier_mismatches.append(
                        f"{p.get('Player','')} {p.get('Prop','')}: edge={_p_edge:.1%} tier={_p_tier} expected={_expected}"
                    )
            if _tier_mismatches:
                _audit_results.append(_audit_fail(
                    "Audit 4 — Tier Integrity",
                    f"{len(_tier_mismatches)} mismatch(es): " + " | ".join(_tier_mismatches[:2])
                ))
            else:
                _audit_results.append(_audit_pass(
                    "Audit 4 — Tier Integrity",
                    f"All {min(50,len(_audit_board))} props have correct tier assignments"
                ))

            # ── AUDIT 5: Lock Selection ─────────────────────────────
            # Verifies today's lock is the highest-edge available play.
            # Flags if a higher-edge play was available but not locked.
            if _today_locks_a and _audit_board:
                _best_board_edge = max((float(p.get("Edge",0) or 0) for p in _audit_board), default=0)
                _lock_edge_max   = max((float(l.get("edge",0) or 0) for l in _today_locks_a), default=0)
                _gap = _best_board_edge - _lock_edge_max
                if _gap > 0.05:
                    _better = next((p for p in _audit_board if abs(float(p.get("Edge",0) or 0) - _best_board_edge) < 0.001), None)
                    _audit_results.append(_audit_warn(
                        "Audit 5 — Lock Selection",
                        f"Lock edge {_lock_edge_max:.1%} vs best available {_best_board_edge:.1%} "
                        f"(gap {_gap:.1%})"
                        + (f" — {_better.get('Player','')} {_better.get('Prop','')} available" if _better else "")
                    ))
                else:
                    _audit_results.append(_audit_pass(
                        "Audit 5 — Lock Selection",
                        f"Lock edge {_lock_edge_max:.1%} | Best available {_best_board_edge:.1%} | Gap {_gap:.1%} ✅"
                    ))
            else:
                _audit_results.append(_audit_pass(
                    "Audit 5 — Lock Selection",
                    "No locks today yet" if not _today_locks_a else "No board data to compare"
                ))

            # ── AUDIT 6: Data Routing ───────────────────────────────
            # Compares OddsAPI raw data vs what the UI shows.
            # Catches cases where data was fetched but not displayed.
            _routing_failures = []
            if _audit_games:
                for g in _audit_games:
                    _oddsapi_ml  = g.get("OddsAPI ML Home","N/A")
                    _display_ml  = g.get("HomeML", g.get("Home ML","N/A"))
                    _oddsapi_sp  = g.get("OddsAPI Spread","N/A")
                    _display_sp  = g.get("Spread","N/A")
                    _matchup     = g.get("matchup","?")
                    # If OddsAPI has data but display shows N/A = routing failure
                    if _oddsapi_ml not in ("N/A",None,"") and _display_ml in ("N/A",None,""):
                        _routing_failures.append(
                            f"🚨 ML routing: {_matchup} OddsAPI={_oddsapi_ml} → UI=No Market"
                        )
                    if _oddsapi_sp not in ("N/A",None,"") and _display_sp in ("N/A",None,""):
                        _routing_failures.append(
                            f"🚨 Spread routing: {_matchup} OddsAPI={_oddsapi_sp} → UI=No Market"
                        )
            if _routing_failures:
                _audit_results.append(_audit_fail(
                    "Audit 6 — Data Routing",
                    " | ".join(_routing_failures[:3])
                ))
            else:
                _games_checked = len(_audit_games)
                _audit_results.append(_audit_pass(
                    "Audit 6 — Data Routing",
                    f"{_games_checked} game(s) — all OddsAPI fields routed to UI correctly"
                ))

            # ── AUDIT 7: Injury Consensus ───────────────────────────
            # Cross-checks all 4 injury sources for conflicts.
            # If ESPN says OUT but CBS says QUESTIONABLE — flag it.
            _inj_sources = {
                "ESPN":     {normalize_name(i["player"]): i["status"] for i in st.session_state.get("espn_injuries",[]) if i.get("status") in ("OUT","DOUBTFUL","QUESTIONABLE")},
                "CBS":      {normalize_name(i["player"]): i["status"] for i in st.session_state.get("cbs_injuries",[])  if i.get("status") in ("OUT","DOUBTFUL","QUESTIONABLE")},
                "RotoWire": {normalize_name(i["player"]): i["status"] for i in st.session_state.get("rw_injuries",[])   if i.get("status") in ("OUT","DOUBTFUL","QUESTIONABLE")},
                "Primary":  {normalize_name(p): v.get("status","") for p,v in (st.session_state.get("injuries_combined") or {}).items()},
            }
            _active_inj_sources = {k:v for k,v in _inj_sources.items() if v}
            _inj_conflicts = []
            if len(_active_inj_sources) >= 2:
                # Find players where sources disagree on severity
                _all_inj_players = set()
                for src_data in _active_inj_sources.values():
                    _all_inj_players.update(src_data.keys())
                for _player in _all_inj_players:
                    _statuses = {src: data.get(_player) for src, data in _active_inj_sources.items() if data.get(_player)}
                    if len(_statuses) >= 2:
                        _unique_statuses = set(_statuses.values())
                        # Conflict = sources disagree on OUT vs QUESTIONABLE (meaningful difference)
                        if "OUT" in _unique_statuses and "QUESTIONABLE" in _unique_statuses:
                            _inj_conflicts.append(f"{_player}: {dict(_statuses)}")
                _total_inj = len(_all_inj_players)
                _agree_pct = 1.0 - (len(_inj_conflicts) / max(1, _total_inj))
                if len(_inj_conflicts) >= 3:
                    _audit_results.append(_audit_fail(
                        "Audit 7 — Injury Consensus",
                        f"{len(_inj_conflicts)} status conflicts across {len(_active_inj_sources)} sources: {'; '.join(_inj_conflicts[:2])}"
                    ))
                elif _inj_conflicts:
                    _audit_results.append(_audit_warn(
                        "Audit 7 — Injury Consensus",
                        f"{len(_inj_conflicts)} disagreement(s): {'; '.join(_inj_conflicts[:2])}"
                    ))
                else:
                    _audit_results.append(_audit_pass(
                        "Audit 7 — Injury Consensus",
                        f"{len(_active_inj_sources)} source(s) agree on {_total_inj} injured player(s) — {_agree_pct:.0%} consensus"
                    ))
            else:
                _audit_results.append(_audit_warn(
                    "Audit 7 — Injury Consensus",
                    f"Only {len(_active_inj_sources)} injury source(s) active — need 2+ for consensus check"
                ))

            # ── AUDIT 9: Data Freshness ─────────────────────────────
            # Checks age of key data sources.
            # Stale weather or odds = wrong model inputs.
            _now_ts = time.time()
            _stale_items = []
            _fresh_items = []
            _freshness_checks = [
                ("Odds (game lines)",  f"espn_ids_{_audit_sport}.pkl",         35 * 60),   # 35 min (cache TTL 30min + 5min buffer)
                ("Props board",        f"pp_{_audit_sport.lower()}_props.pkl", 20 * 60),   # 20 min
                ("Injury data",        f"ud_injuries_{_audit_sport}.pkl",       30 * 60),  # 30 min
                ("Weather data",       None,                                    1440 * 60), # 24 hrs (daily refresh is fine for MLB)
                ("DK Salaries",        "dk_salaries.pkl",                        90 * 60),  # 90 min
            ]
            for label, fname, max_age_secs in _freshness_checks:
                if fname is None:
                    # Weather — check cache dir for any weather pkl
                    import glob as _glob
                    _weather_files = _glob.glob(os.path.join(CACHE_DIR, "*_weather.pkl"))
                    if _weather_files:
                        _age = _now_ts - os.path.getmtime(max(_weather_files, key=os.path.getmtime))
                        if _age > max_age_secs:
                            _stale_items.append(f"{label} ({_age/60:.0f}m old)")
                        else:
                            _fresh_items.append(f"{label} ({_age/60:.0f}m)")
                    continue
                _fpath = os.path.join(CACHE_DIR, fname)
                if os.path.exists(_fpath):
                    _age = _now_ts - os.path.getmtime(_fpath)
                    if _age > max_age_secs:
                        _stale_items.append(f"{label} ({_age/60:.0f}m old)")
                    else:
                        _fresh_items.append(f"{label} ({_age/60:.0f}m)")
            if len(_stale_items) >= 2:
                _audit_results.append(_audit_fail(
                    "Audit 9 — Data Freshness",
                    f"{len(_stale_items)} stale feed(s): {', '.join(_stale_items)}"
                ))
            elif _stale_items:
                _audit_results.append(_audit_warn(
                    "Audit 9 — Data Freshness",
                    f"Stale: {', '.join(_stale_items)} | Fresh: {len(_fresh_items)} feed(s)"
                ))
            else:
                _audit_results.append(_audit_pass(
                    "Audit 9 — Data Freshness",
                    f"All {len(_fresh_items)} feed(s) current"
                ))

            # ── AUDIT 10: Sharp Consensus ───────────────────────────
            # Deduplicate game_analysis by normalized matchup to prevent
            # same game appearing as both "NY @ SA" and full team names
            _seen_matchups = set()
            _deduped_games = []
            for _sg in _audit_games:
                _raw_m = _sg.get("matchup","").lower()
                # Normalize: strip spaces, sort teams
                _parts = sorted(_raw_m.replace(" @ "," vs ").split(" vs "))
                _norm_m = " vs ".join(_parts)
                if _norm_m not in _seen_matchups:
                    _seen_matchups.add(_norm_m)
                    _deduped_games.append(_sg)
            _audit_games_deduped = _deduped_games
            if _audit_games_deduped:
                _sharp_divergences = []
                _sharp_agreements  = []
                for _sg in _audit_games_deduped[:10]:
                    _matchup = _sg.get("matchup","?")
                    # Only use OddsAPI/Pinnacle edges — NOT Bovada
                    # Bovada is a soft book and should not drive sharp consensus
                    _ml_edge  = safe_float(_sg.get("MLEdge", 0) or 0)
                    _tot_edge = safe_float(_sg.get("TotalEdge", 0) or 0)
                    _pin_ml   = safe_float(_sg.get("HomeML","") or 0)
                    # Skip if edge came purely from Bovada (no Pinnacle/OddsAPI data)
                    _has_sharp_data = (
                        safe_float(_sg.get("PinnacleTotal", 0) or 0) != 0 or
                        safe_float(_sg.get("PinnacleML", 0) or 0) != 0 or
                        _sg.get("sharp_source","") not in ("bovada","Bovada","") or
                        (abs(_ml_edge) > 0 and _sg.get("odds_source","") != "bovada")
                    )
                    _has_data = (_pin_ml != 0 or abs(_ml_edge) > 0 or abs(_tot_edge) > 0)
                    if _has_data and _has_sharp_data:
                        if abs(_ml_edge) >= 0.05 or abs(_tot_edge) >= 0.05:
                            _sharp_divergences.append(
                                f"{_matchup}: ML edge {_ml_edge:+.1%} Total edge {_tot_edge:+.1%}"
                            )
                        else:
                            _sharp_agreements.append(_matchup)
                _clv_data = get_clv_summary(st.session_state.get("history", []))
                _consensus_edge = (_clv_data or {}).get("consensus_sharp_edge", 0)
                _n_books = (_clv_data or {}).get("n_sharp_books", 0)
                if _sharp_divergences:
                    _audit_results.append(_audit_warn(
                        "Audit 10 — Sharp Consensus",
                        f"{len(_sharp_divergences)} line divergence(s): {'; '.join(_sharp_divergences[:2])}"
                    ))
                elif _n_books >= 2:
                    _audit_results.append(_audit_pass(
                        "Audit 10 — Sharp Consensus",
                        f"{_n_books} sharp books tracked | Consensus edge {_consensus_edge:+.1%} | {len(_sharp_agreements)} games aligned"
                    ))
                else:
                    # Check if OddsAPI is returning data (proxy for sharp book availability)
                    _has_oddsapi = any(
                        safe_float(g.get("HomeML","") or 0) != 0 or
                        safe_float(g.get("MLEdge", 0) or 0) != 0 or
                        safe_float(g.get("TotalEdge", 0) or 0) != 0
                        for g in _audit_games_deduped[:5]
                    ) if _audit_games_deduped else False
                    if _has_oddsapi:
                        _audit_results.append(_audit_pass(
                            "Audit 10 — Sharp Consensus",
                            f"OddsAPI (Pinnacle/Circa/BetOnline) returning data | {len(_sharp_agreements)} games aligned | CLV history pending"
                        ))
                    else:
                        _audit_results.append(_audit_warn(
                            "Audit 10 — Sharp Consensus",
                            "Sharp books not returning odds data — check OddsAPI key"
                        ))
            else:
                _audit_results.append(_audit_warn("Audit 10 — Sharp Consensus", "No game analysis data"))

            # ── Audit 11: Prediction Stability ─────────────────────
            _unstable = check_prediction_stability(_audit_board, _audit_sport)
            if _unstable:
                _audit_results.append(_audit_warn(
                    "Audit 11 — Prediction Stability",
                    f"{len(_unstable)} prop(s) edge drifted >5% unexplained: " +
                    " | ".join(f"{u['player']} {u['prop']} {u['prev']:.1%}→{u['curr']:.1%}" for u in _unstable[:2])
                ))
            else:
                _snap_count = len(load_json_data(BOARD_SNAP_PATH, {}))
                _audit_results.append(_audit_pass(
                    "Audit 11 — Prediction Stability",
                    f"No unexplained edge drift detected ({_snap_count} snapshot(s) on file)"
                ))

            # ── Audit 12: Depth Chart Changes ───────────────────────
            _dc_changes = st.session_state.get("depth_chart_changes", [])
            if _dc_changes:
                _audit_results.append(_audit_warn(
                    "Audit 12 — Depth Chart Changes",
                    f"{len(_dc_changes)} starter change(s): " +
                    " | ".join(f"{c['team']} {c['position']}: {c['old']}→{c['new']}" for c in _dc_changes[:3])
                ))
            else:
                _snap_dates = len(load_json_data(NFL_DEPTH_SNAP_PATH, {}))
                _audit_results.append(_audit_pass(
                    "Audit 12 — Depth Chart Changes",
                    f"No depth chart starter changes detected ({_snap_dates} day(s) tracked)"
                ))

            # ── Audit 13: NFL Inactives Impact ──────────────────────
            if _audit_sport == "NFL":
                _inactives = st.session_state.get("nfl_inactives", {})
                if _inactives:
                    # Check if any inactive player has active props on board
                    _inactive_names = set()
                    for team_list in _inactives.values():
                        _inactive_names.update(normalize_name(n) for n in team_list)
                    _inactive_props = [p for p in _audit_board
                                       if normalize_name(p.get("Player","")) in _inactive_names]
                    if _inactive_props:
                        _audit_results.append(_audit_fail(
                            "Audit 13 — NFL Inactives Impact",
                            f"🚨 {len(_inactive_props)} active prop(s) for inactive player(s): " +
                            ", ".join(p.get("Player","") for p in _inactive_props[:3])
                        ))
                    else:
                        _audit_results.append(_audit_pass(
                            "Audit 13 — NFL Inactives Impact",
                            f"All {len(_inactive_names)} inactive player(s) cleared from board"
                        ))
                else:
                    _audit_results.append(_audit_pass(
                        "Audit 13 — NFL Inactives Impact",
                        "Inactives not yet posted (typically 90 min before kickoff)"
                    ))

            st.session_state["_audit_results_cache"] = {"key": _audit_cache_key, "results": _audit_results}
        # ── Display audit results ───────────────────────────────
        _fails  = [r for r in _audit_results if r["status"] == "FAIL"]
        _warns  = [r for r in _audit_results if r["status"] == "WARN"]
        _passes = [r for r in _audit_results if r["status"] == "PASS"]
        _score  = round((len(_passes) * 100 + len(_warns) * 60) / max(1, len(_audit_results)))

        # Score banner
        _score_color = "#22c55e" if _score >= 90 else "#e8a020" if _score >= 70 else "#e04040"
        _score_label = "PASS" if _score >= 90 else "WARNING" if _score >= 70 else "FAIL"
        st.markdown(
            f'<div style="background:{_score_color}11;border:1px solid {_score_color}33;'
            f'border-radius:8px;padding:0.8rem 1.2rem;margin-bottom:0.8rem;'
            f'display:flex;align-items:center;justify-content:space-between;">'
            f'<div>'
            f'<span style="color:{_score_color};font-size:1.2rem;font-weight:700;">MODEL HEALTH</span>'
            f'<span style="color:var(--bc-muted);font-size:0.9rem;margin-left:1rem;">'
            f'{len(_passes)} PASS · {len(_warns)} WARN · {len(_fails)} FAIL</span>'
            f'</div>'
            f'<div style="text-align:right;">'
            f'<span style="color:{_score_color};font-size:2rem;font-weight:700;">{_score}</span>'
            f'<span style="color:var(--bc-dim);font-size:0.9rem;">/100 {_score_label}</span>'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True
        )

        # Individual audit rows
        for r in _audit_results:
            _rc = "#22c55e" if r["status"]=="PASS" else "#e8a020" if r["status"]=="WARN" else "#e04040"
            _icon = "✅" if r["status"]=="PASS" else "⚠️" if r["status"]=="WARN" else "🚨"
            st.markdown(
                f'<div style="background:var(--bc-bg);border:1px solid var(--bc-border);border-left:3px solid {_rc};'
                f'border-radius:6px;padding:0.5rem 0.8rem;margin-bottom:0.3rem;">'
                f'<div style="display:flex;align-items:center;justify-content:space-between;">'
                f'<span style="color:var(--bc-text);font-size:0.95rem;">{_icon} {r["name"]}</span>'
                f'<span style="color:{_rc};font-size:0.85rem;font-weight:700;">{r["status"]}</span>'
                f'</div>'
                + (f'<div style="color:var(--bc-muted);font-size:0.8rem;margin-top:2px;">{r["detail"]}</div>' if r["detail"] else "")
                + '</div>',
                unsafe_allow_html=True
            )

        if _fails:
            st.warning(f"⚠️ {len(_fails)} audit failure(s) detected. Review before placing bets.")

    # ── FantasyLabs MLB Lineups ──────────────────────────────
    _fl_sys = st.session_state.get("fantasylabs_lineups", {})
    if _fl_sys or st.session_state.get("last_sport") == "MLB":
        st.markdown("---")
        st.markdown("### ⚾ FantasyLabs MLB Lineups")
        if _fl_sys:
            _fl_in_lineup   = [v for v in _fl_sys.values() if v.get("in_lineup") and v.get("active")]
            _fl_injured     = [v for v in _fl_sys.values() if not v.get("active")]
            _fl_scratched   = [v for v in _fl_sys.values() if v.get("active") and not v.get("in_lineup")]
            _fls1, _fls2, _fls3, _fls4 = st.columns(4)
            _fls1.metric("Total Players", len(_fl_sys))
            _fls2.metric("✅ In Lineup", len(_fl_in_lineup))
            _fls3.metric("⚠️ Injured", len(_fl_injured))
            _fls4.metric("❌ Scratched", len(_fl_scratched))
            # Show leadoff hitters
            _leadoffs = sorted([v for v in _fl_in_lineup if v.get("lineup_order") == 1],
                               key=lambda x: x.get("team",""))
            if _leadoffs:
                _leadoff_names = ", ".join(
                    f"{v.get('player','?')} ({v.get('team','?')})"
                    for v in _leadoffs[:6]
                )
                st.caption(f"Leadoff hitters: {_leadoff_names}")
            # Show injured
            if _fl_injured:
                st.warning(f"⚠️ Injured players: {', '.join(v.get('player','') for v in _fl_injured[:5])}")
            fetched = next((v.get("fetched_at","") for v in _fl_sys.values()), "")
            st.caption(f"Last refresh: {fetched}")
        else:
            st.info("FantasyLabs lineups load with the MLB board. Typically posted 3-4h before first pitch.")

    # ── Golf Leaderboard ─────────────────────────────────────
    _golf_lb_sys  = st.session_state.get("golf_leaderboard", [])
    _golf_odds_sys = st.session_state.get("golf_odds", {})
    if _golf_lb_sys or st.session_state.get("last_sport") == "GOLF":
        st.markdown("---")
        st.markdown("### ⛳ Golf Leaderboard")
        if _golf_lb_sys:
            _tournament = _golf_lb_sys[0].get("tournament","Current Tournament") if _golf_lb_sys else ""
            st.caption(f"**{_tournament}** | {len(_golf_lb_sys)} players")
            _golf_rows = [{"Pos": p["position"], "Player": p["name"],
                           "Total": p["total"], "Today": p["today"],
                           "Thru": p["thru"]} for p in _golf_lb_sys[:15]]
            st.markdown(_bc_df_html(pd.DataFrame(_golf_rows)), unsafe_allow_html=True)
            if _golf_odds_sys:
                st.markdown("**Tournament Win Odds:**")
                _odds_rows = sorted(_golf_odds_sys.values(),
                                    key=lambda x: -x.get("implied_prob",0))[:10]
                _odds_df = [{"Player": o["name"],
                             "Odds": f"+{o['odds']}" if o["odds"]>0 else str(o["odds"]),
                             "Implied": f"{o['implied_prob']:.1%}"} for o in _odds_rows]
                st.markdown(_bc_df_html(pd.DataFrame(_odds_df)), unsafe_allow_html=True)

    # ── NHL Starting Goalies ────────────────────────────────
    _nhl_goalies_sys = st.session_state.get("nhl_starting_goalies", {})
    if _nhl_goalies_sys:
        st.markdown("---")
        st.markdown("### 🥅 NHL Starting Goalies")
        st.caption("Confirmed starters from NHL official API. Goalie is the #1 factor in NHL props.")
        _goalie_rows = []
        for team, gdata in sorted(_nhl_goalies_sys.items()):
            _goalie_rows.append({
                "Team":      team,
                "Goalie":    gdata.get("goalie","TBD"),
                "Confirmed": "✅ Yes" if gdata.get("confirmed") else "⚠️ TBD",
                "Opponent":  gdata.get("opponent",""),
                "Home/Away": "Home" if gdata.get("home") else "Away",
            })
        if _goalie_rows:
            st.markdown(_bc_df_html(pd.DataFrame(_goalie_rows)), unsafe_allow_html=True)

    # ── Depth Chart Status ──────────────────────────────────
    _depth_charts = st.session_state.get("espn_depth_charts", {})
    if _depth_charts:
        st.markdown("---")
        st.markdown("### 🏈 Depth Chart Snapshot")
        st.caption(f"ESPN depth charts for {len(_depth_charts)} teams. Useful for injury impact on snap/usage share.")
        _dc_team = st.selectbox("Team", sorted(_depth_charts.keys()), key="dc_team_sel")
        if _dc_team and _dc_team in _depth_charts:
            _dc_data = _depth_charts[_dc_team]
            _dc_rows = []
            for pos, players in _dc_data.get("positions", {}).items():
                for pl in players[:3]:  # show top 3 per position
                    _dc_rows.append({"Position": pos, "Player": pl["name"], "Depth": pl["depth"]})
            if _dc_rows:
                st.markdown(_bc_df_html(pd.DataFrame(_dc_rows)), unsafe_allow_html=True)
    # ── Market Intelligence Dashboard ──────────────────────
    st.markdown("---")
    st.markdown("### 🌐 Market Intelligence")
    st.caption("Kalshi + Polymarket prediction market probabilities vs model. Public betting consensus from Covers.")
    _kal  = st.session_state.get("kalshi_markets", [])
    _poly = st.session_state.get("polymarket_markets", [])
    _cov  = st.session_state.get("covers_consensus", [])
    _mi_c1, _mi_c2, _mi_c3 = st.columns(3)
    _mi_c1.metric("Kalshi Markets", len(_kal), help="Open prediction markets with volume >100")
    _mi_c2.metric("Polymarket", len(_poly), help="Active markets volume >$1000")
    _mi_c3.metric("Covers Consensus", len(_cov), help="Public betting % by matchup (needs COVERS_COOKIE)")
    if _kal:
        st.markdown("**Kalshi Top Markets:**")
        _kal_sorted = sorted(_kal, key=lambda x: -x.get("volume",0))
        _kal_valid = [k for k in _kal_sorted if isinstance(k, dict) and "event" in k and "implied_prob" in k and "volume" in k]
        _kal_rows = [{"Event": k["event"][:50], "Implied %": f"{k['implied_prob']:.0%}", "Volume": f"{k['volume']:,}"} for k in _kal_valid[:5]]
        st.markdown(_bc_df_html(pd.DataFrame(_kal_rows)), unsafe_allow_html=True)
    if _poly:
        st.markdown("**Polymarket Top Markets:**")
        _poly_sorted = sorted(_poly, key=lambda x: -x.get("volume",0))
        _poly_valid = [p for p in _poly_sorted if isinstance(p, dict) and "question" in p and "implied_prob" in p and "volume" in p]
        _poly_rows = [{"Question": p["question"][:50], "Implied %": f"{p['implied_prob']:.0%}", "Volume": f"${p['volume']:,.0f}"} for p in _poly_valid[:5]]
        st.markdown(_bc_df_html(pd.DataFrame(_poly_rows)), unsafe_allow_html=True)
    if _cov and isinstance(_cov, dict):
        st.markdown("**Public Consensus (Covers):**")
        _cov_rows = []
        for _cm, _cv in list(_cov.items())[:8]:
            _cm_away, _, _cm_home = _cm.partition(" @ ")
            _cm_away_pct = _cv.get("away_pct", 50)
            _cm_home_pct = _cv.get("home_pct", 50)
            if _cm_home_pct >= _cm_away_pct:
                _cm_pct, _cm_side = _cm_home_pct, _cm_home
            else:
                _cm_pct, _cm_side = _cm_away_pct, _cm_away
            _cov_rows.append({"Matchup": _cm[:40], "Public %": f"{_cm_pct}%", "Side": _cm_side})
        st.markdown(_bc_df_html(pd.DataFrame(_cov_rows)), unsafe_allow_html=True)
    elif not st.secrets.get("FIRECRAWL_KEY",""):
        st.info("Add FIRECRAWL_KEY to Streamlit secrets to enable Covers public betting consensus data.")

    st.markdown("---")
    # ── Kill Switch Status ────────────────────────────────────────────────
    if not ENABLE_RECOMMENDATIONS:
        st.error("🔴 **KILL SWITCH ACTIVE** — Recommendations suppressed. Set `ENABLE_RECOMMENDATIONS = true` in Streamlit secrets to re-enable.", icon="🛑")
    else:
        st.success("🟢 **System Active** — Recommendations enabled. Set `ENABLE_RECOMMENDATIONS = false` in secrets for emergency stop.", icon="✅")

    st.markdown("### ⚡ Network Health — Circuit Breakers & Fetch Timings")
    st.caption("Tripped circuits are skipped instantly rather than burning the full timeout. Auto-reset after 60s.")

    _cb_status = circuit_status()
    _ft_timings = st.session_state.get("fetch_timings", {})

    _cb_col1, _cb_col2 = st.columns(2)
    with _cb_col1:
        st.markdown("**Circuit Breaker Status**")
        if not _cb_status:
            st.success("✅ All circuits healthy — no providers tripped")
        else:
            for _prov, _cs in sorted(_cb_status.items()):
                if _cs["tripped"]:
                    st.error(f"🔴 **{_prov}** — TRIPPED (resets in {_cs['reset_in']}s, {_cs['fail_count']} failures)")
                elif _cs["fail_count"] > 0:
                    st.warning(f"🟡 **{_prov}** — {_cs['fail_count']}/{_CB_THRESHOLD} failures (not yet tripped)")
                else:
                    st.success(f"🟢 **{_prov}** — Healthy")

    with _cb_col2:
        st.markdown("**Fetch Timings (last board load)**")
        if not _ft_timings:
            st.info("No timing data yet — load the board first")
        else:
            _ft_sorted = sorted(_ft_timings.items(), key=lambda x: x[1].get("time", 0), reverse=True)
            _ft_rows = []
            for _src, _td in _ft_sorted[:15]:
                _t_val = _td.get("time", 0)
                _status = _td.get("status", "?")
                _color = "#e04040" if "❌" in _status else ("#e8a020" if _t_val > 5 else "#22c55e")
                _ft_rows.append({"Source": _src[:30], "Time (s)": f"{_t_val:.2f}", "Status": _status})
            if _ft_rows:
                import pandas as _pd_sys
                st.markdown(_bc_df_html(_pd_sys.DataFrame(_ft_rows)), unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### 🔬 Signal Intelligence Summary")
    st.caption("Quick health check on signal quality. Full details in History tab.")
    _sys_perf = load_json_data(SIGNAL_PERFORMANCE_PATH, [], mem_ttl=60)
    _sys_resolved = [p for p in _sys_perf if p.get("outcome") in ("WIN","LOSS")]
    _scol1, _scol2, _scol3 = st.columns(3)
    _scol1.metric("Resolved Bets", len(_sys_resolved), help="Signal analysis needs 20+")
    if len(_sys_resolved) >= 20:
        _, _, _sys_warnings = compute_signal_correlation_matrix(_sys_perf)
        _scol2.metric("Overlap Warnings", len(_sys_warnings),
                     delta="⚠️ Review" if _sys_warnings else "✅ Clean",
                     delta_color="inverse" if _sys_warnings else "off")
        _sys_lift, _ = compute_signal_lift_analysis(_sys_perf)
        _neg_count = len([r for r in (_sys_lift or []) if "Negative" in r["Grade"]])
        _scol3.metric("Negative Signals", _neg_count,
                     delta="⚠️ Review" if _neg_count else "✅ All positive",
                     delta_color="inverse" if _neg_count else "off")
    else:
        _scol2.metric("Overlap Warnings", "—", help=f"Need {20-len(_sys_resolved)} more bets")
        _scol3.metric("Negative Signals", "—", help=f"Need {30-len(_sys_resolved)} more bets")
    st.markdown("---")
    st.markdown("### 📊 SEM Calibration")
    tier_stats_s = compute_tier_stats(st.session_state.get("history", []))
    if tier_stats_s:
        sem_df = pd.DataFrame([{"Tier": tier, "Bets": s["n"], "Hit Rate": f"{s['hit_rate']:.1%}", "Predicted": f"{s['avg_predicted']:.1%}", "SEM": f"\u00b1{s['sem']:.3f}" if s['sem'] else "\u2014"} for tier, s in tier_stats_s.items()])
        st.markdown(_bc_df_html(sem_df), unsafe_allow_html=True)
    else:
        st.info("No calibration data yet.")
    st.markdown("---")
    st.markdown("### \U0001f50d Error Log")
    errors_s = st.session_state.get("errors", [])
    if errors_s:
        for err in errors_s[-5:]:
            st.error(f"[{err.get('time','')}] {err.get('source','')}: {err.get('error','')}")
        if st.button("Clear Error Log"):
            st.session_state["errors"] = []
            st.rerun()
    else:
        st.caption("\u2705 No errors this session.")
    st.markdown("---")
    st.markdown("---")
    st.markdown("### ⏱️ Source Performance Profiler")
    st.caption("Timing from last board load. Reload the board to refresh.")
    _timings = st.session_state.get("fetch_timings", {})
    if _timings:
        _timing_rows = []
        for src, info in sorted(_timings.items(), key=lambda x: -x[1]["time"]):
            _timing_rows.append({
                "Source": src,
                "Time (s)": info["time"],
                "Status": info["status"],
                "Grade": "🟢" if info["time"] < 1.0 else "🟡" if info["time"] < 3.0 else "🔴"
            })
        _total = sum(r["Time (s)"] for r in _timing_rows)
        _cols = st.columns(3)
        _cols[0].metric("Total Sources", len(_timing_rows))
        _cols[1].metric("Slowest", f"{max(r['Time (s)'] for r in _timing_rows):.1f}s")
        _cols[2].metric("Wall Time (parallel)", f"{max(r['Time (s)'] for r in _timing_rows):.1f}s")
        st.markdown(_bc_df_html(pd.DataFrame(_timing_rows)), unsafe_allow_html=True)
        if st.button("Clear Timing Data", key="clear_timings"):
            st.session_state["fetch_timings"] = {}
            st.rerun()
    else:
        st.info("No timing data yet. Load the board first.")
    st.markdown("---")
    with st.expander("🔧 Developer Tools — Session Memory Audit", expanded=False):
        st.markdown("### 🧠 Session Memory Audit")
        st.caption("Size of key objects in session state.")
        import sys as _sys
        _mem_rows = []
        _large_keys = ["board_data","history","locks","fetch_timings","oddswrap_props",
                       "ud_props_compare","public_betting_data","an_props_data",
                       "parlayapi_props_cache","sleeper_props_cache"]
        for _k in _large_keys:
            _val = st.session_state.get(_k)
            if _val is not None:
                _sz = _sys.getsizeof(_val)
                if isinstance(_val, list):
                    _desc = f"list[{len(_val)}]"
                elif isinstance(_val, dict):
                    _desc = f"dict[{len(_val)}]"
                else:
                    _desc = type(_val).__name__
                _mem_rows.append({"Key": _k, "Type": _desc, "Size (bytes)": _sz,
                                  "Size (KB)": round(_sz/1024, 1)})
        if _mem_rows:
            _total_kb = sum(r["Size (KB)"] for r in _mem_rows)
            st.metric("Total tracked memory", f"{_total_kb:.1f} KB")
            st.markdown(_bc_df_html(pd.DataFrame(_mem_rows)), unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("### 💾 Gist Write Status")
    _dirty = st.session_state.get("gist_dirty", {})
    _last_writes = st.session_state.get("gist_last_write", {})
    if _dirty:
        st.warning(f"⏳ {len(_dirty)} pending write(s): {', '.join(_dirty.keys())}")
        if st.button("Flush All Pending Writes", key="flush_gist"):
            _flush_results = flush_all_gist_writes()
            st.success(f"Flushed: {_flush_results}")
            st.rerun()
    else:
        st.success("✅ All Gist writes up to date")
    if _last_writes:
        _write_rows = [{"Type": k, "Last Write": time.strftime("%H:%M:%S", time.localtime(v))}
                       for k, v in _last_writes.items()]
        st.markdown(_bc_df_html(pd.DataFrame(_write_rows)), unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("### 📡 API Control Panel")
    st.caption("Live status of every data source. Hit Refresh to ping all APIs.")

    # --- Ping definitions ---
    _PP_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": "https://app.prizepicks.com/",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://app.prizepicks.com",
    }
    _PING_SOURCES = [
        {
            "name": "PrizePicks",
            "description": "Primary prop source (via ScrapeOps proxy)",
            "url": "https://api.prizepicks.com/projections?league_id=7&per_page=10&single_stat=true&in_game=true&state_code=CA&game_mode=prizepools",
            "headers": _PP_HEADERS,
            "budget_key": None,
            "count_key": None,
            "is_prop_source": True,
            "use_scrapeops": True,
        },
        {
            "name": "Underdog Fantasy",
            "description": "Via ParlayAPI aggregator",
            "url": f"https://api.underdogfantasy.com/v1/lobbies/content/lines?include_live=true&product=fantasy&product_experience_id=018e1234-5678-9abc-def0-123456789006&show_mass_option_markets=false&sport_id=NBA&state_config_id=725014ef-3570-4e93-871d-d69674ab3521",
            "headers": {"Origin": "https://underdogfantasy.com", "Referer": "https://underdogfantasy.com/pick-em", "User-Agent": "Mozilla/5.0"},
            "budget_key": None,
            "count_key": None,
            "is_prop_source": True,
        },
        {
            "name": "ParlayPlay",
            "description": "Via ParlayAPI aggregator (bot-free)",
            "url": f"https://parlay-api.com/v1/sports/basketball_nba/props?bookmakers=parlayplay&dfsOdds=midpoint",
            "headers": {"X-API-Key": st.secrets.get("PARLAY_API_KEY", "")},
            "budget_key": "PARLAYPLAY",
            "count_key": "PARLAY_API_KEY",
            "is_prop_source": True,
        },
        {
            "name": "Action Network",
            "description": "Public betting % + projections",
            "url": "https://api.actionnetwork.com/web/v2/leagues/4/projections/available?limit=10",
            "headers": {"Origin": "https://www.actionnetwork.com", "Referer": "https://www.actionnetwork.com/"},
            "budget_key": "ACTION_NETWORK",
            "count_key": None,
            "is_prop_source": False,
        },
        {
            "name": "DraftKings DFS",
            "description": "Player salaries + value scores",
            "url": "https://www.draftkings.com/lobby/getcontests?sport=NBA",
            "headers": {"Referer": "https://www.draftkings.com/"},
            "budget_key": None,
            "count_key": None,
            "is_prop_source": False,
        },
        {
            "name": "BallsDontLie",
            "description": "Player averages + stats",
            "url": "https://api.balldontlie.io/v1/players?per_page=1",
            "headers": {"Authorization": st.secrets.get("BALLSDONTLIE_API_KEY", "")},
            "budget_key": "BDL",
            "count_key": "BALLSDONTLIE_API_KEY",
            "is_prop_source": False,
        },
        {
            "name": "ParlayAPI",
            "description": "ParlayPlay + Underdog + arb scanner",
            "url": f"https://api.underdogfantasy.com/v1/lobbies/content/lines?include_live=true&product=fantasy&product_experience_id=018e1234-5678-9abc-def0-123456789006&show_mass_option_markets=false&sport_id=NBA&state_config_id=725014ef-3570-4e93-871d-d69674ab3521",
            "headers": {"X-API-Key": st.secrets.get("PARLAY_API_KEY", "")},
            "budget_key": None,
            "count_key": "PARLAY_API_KEY",
            "is_prop_source": False,
        },
        {
            "name": "OddsPAPI",
            "description": "Props fallback odds",
            "url": "https://api.oddspapi.io/v4/sports?apiKey=" + st.secrets.get("ODDSPAPI_KEY", ""),
            "headers": {},
            "budget_key": "ODDSPAPI",
            "count_key": "ODDSPAPI_KEY",
            "is_prop_source": False,
        },
        {
            "name": "ESPN",
            "description": "Game schedules + scores",
            "url": "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard",
            "headers": {},
            "budget_key": "ESPN",
            "count_key": None,
            "is_prop_source": False,
        },
        {
            "name": "OddsAPI",
            "description": "Closing lines + CLV",
            "url": "https://api.the-odds-api.com/v4/sports?apiKey=" + st.secrets.get("ODDS_API_KEY", "demo"),
            "headers": {},
            "budget_key": "ODDS_API",
            "count_key": "ODDS_API_KEY",
            "is_prop_source": False,
        },
    ]

    def _ping_url(url, headers, timeout=8):
        """Returns (status_code, detail_str, color) — color: green/yellow/red."""
        try:
            r = _http.get(url, headers=headers, timeout=timeout)
            code = r.status_code
            if code == 200:
                return code, "✅ 200 OK — Responding normally", "green"
            elif code == 403:
                return code, "🔒 403 Forbidden — Blocked. Board will use fallback sources.", "red"
            elif code == 429:
                return code, "🚫 429 Rate Limited — Too many requests. Wait 15–30 min.", "yellow"
            elif code == 401:
                return code, "🔑 401 Unauthorized — API key missing or invalid.", "red"
            elif code == 404:
                return code, "❓ 404 Not Found — Endpoint may have changed.", "yellow"
            elif code >= 500:
                return code, f"💥 {code} Server Error — API is down on their end.", "red"
            else:
                return code, f"⚠️ {code} — Unexpected response.", "yellow"
        except requests.exceptions.Timeout:
            return None, "⏱️ Timeout — No response within 8s. API may be down.", "red"
        except requests.exceptions.ConnectionError:
            return None, "❌ Connection Error — Unreachable. Check if site is down.", "red"
        except (requests.RequestException, KeyError, ValueError) as ex:
            return None, f"❌ Error — {str(ex)[:60]}", "red"

    _COLOR_CSS = {
        "green":  "border-left: 4px solid #00c87a; background: rgba(0,200,122,0.07);",
        "yellow": "border-left: 4px solid #f0a500; background: rgba(240,165,0,0.07);",
        "red":    "border-left: 4px solid #e04040; background: rgba(224,64,64,0.07);",
    }
    _DOT = {"green": "🟢", "yellow": "🟡", "red": "🔴"}

    # Store ping results in session state so they persist until refresh
    if "api_panel_results" not in st.session_state:
        st.session_state["api_panel_results"] = {}
    # If board loaded via Gist, show that in panel
    _pp_src = st.session_state.get("pp_source","")
    if _pp_src == "gist_scraper":
        st.success("📡 **Board data loaded from local scraper (Gist)** — API status below is informational only.")

    col_refresh, col_reset = st.columns([2, 2])
    do_refresh = col_refresh.button("🔄 Refresh All", key="api_panel_refresh")
    do_reset   = col_reset.button("🗑️ Reset API Counters", key="api_panel_reset_counters")

    if do_reset:
        for key_s, budget_s in API_BUDGETS.items():
            path_s = budget_s["counter_path"]
            if os.path.exists(path_s):
                os.remove(path_s)
        st.success("✅ All API counters reset")

    if do_refresh:  # Only ping when user clicks Refresh — auto-ping wastes API calls
        with st.spinner("Pinging all sources..."):
            results = {}
            for src in _PING_SOURCES:
                # Use ScrapeOps proxy for blocked sources (PrizePicks, Kalshi etc)
                _use_scrapeops = src.get("use_scrapeops", False)
                if _use_scrapeops:
                    try:
                        _pr = scrapeops_get(src["url"], timeout=20)
                        code = _pr.status_code
                        # Determine which proxy actually worked
                        _log = st.session_state.get("scrapeops_log", [])
                        _last_proxy = _log[-1]["proxy"] if _log else "Unknown"
                        _last_status = _log[-1]["status"] if _log else code
                        color = "green" if code == 200 else "red"
                        detail = f"✅ 200 OK via {_last_proxy}" if code == 200 else f"❌ {code} (tried: ScrapeOps→ScraperAPI→Scrape.do)"
                    except (requests.RequestException, KeyError, ValueError) as _pe:
                        code, detail, color = _ping_url(src["url"], src["headers"])
                        if color != "green":
                            detail = f"⚠️ All proxies failed — direct: {detail}"
                else:
                    code, detail, color = _ping_url(src["url"], src["headers"])
                # For prop sources returning JSON, try to count items
                extra = ""
                if color == "green" and src.get("is_prop_source"):
                    try:
                        if _use_scrapeops:
                            r2 = scrapeops_get(src["url"], timeout=20)
                        else:
                            r2 = _http.get(src["url"], headers=src["headers"], timeout=8)
                        d2 = r2.json()
                        n = len(d2.get("data", d2.get("over_under_lines", d2.get("projections", []))))
                        if n > 0:
                            extra = f" — {n} props returned"
                            detail = f"✅ 200 OK — Responding normally{extra}"
                        elif n == 0:
                            detail = "⚠️ 200 OK — Connected but 0 props. No slate posted yet."
                            color = "yellow"
                    except (requests.RequestException, KeyError, ValueError):
                        pass
                results[src["name"]] = (code, detail, color)
            st.session_state["api_panel_results"] = results

    results = st.session_state.get("api_panel_results", {})

    # Auto-diagnosis summary
    if results:
        red_sources = [n for n, (c, d, col) in results.items() if col == "red"]
        yellow_sources = [n for n, (c, d, col) in results.items() if col == "yellow"]
        green_sources = [n for n, (c, d, col) in results.items() if col == "green"]

        if red_sources or yellow_sources:
            with st.expander("🔧 Auto-Diagnosis — What these errors mean and what to do", expanded=True):
                fixes = {
                    "ParlayPlay": {
                        "403": "ParlayPlay session cookie is missing or expired. Add PARLAYPLAY_SESSION to Streamlit Secrets. Get it from Chrome DevTools → parlayplay.io → Application → Cookies → sessionid value. Expires every ~2 weeks.",
                        "fix": "Add or refresh PARLAYPLAY_SESSION in Streamlit Secrets."
                    },
                    "Underdog Fantasy": {
                        "400": "Underdog changed their API format. This is a fallback source only — your board works fine without it.",
                        "fix": "No action needed. Used only for line comparison in Line Shop."
                    },
                    "OddsPAPI": {
                        "400": "Tournament ID lookup returned unexpected format. Try clearing cache and refreshing.",
                        "401": "API key is invalid or expired. Go to oddspapi.io/dashboard, regenerate your key, and update Streamlit Secrets.",
                        "fix": "Update ODDSPAPI_KEY in Streamlit Secrets."
                    },
                    "BallsDontLie": {
                        "401": "API key missing or expired. Go to balldontlie.io, check your key, update BALLSDONTLIE_API_KEY in Streamlit Secrets.",
                        "fix": "Update BALLSDONTLIE_API_KEY in Streamlit Secrets."
                    },
                    "PrizePicks": {
                        "200": "PrizePicks is responding but props may be cached from an earlier empty response. Click 'Clear PrizePicks Cache' below, then load the board again.",
                        "403": "PrizePicks is temporarily blocking requests. Wait 10 minutes and reload the board.",
                        "429": "PrizePicks rate limited — too many requests. Wait 15-30 minutes then try again.",
                        "fix": "Clear PrizePicks cache in System tab, then reload the board."
                    },
                }
                if green_sources:
                    st.success(f"✅ {len(green_sources)} sources working: {', '.join(green_sources)}")
                for name_err in red_sources + yellow_sources:
                    src_fix = fixes.get(name_err, {})
                    result_code, result_detail, result_color = results.get(name_err, (None, "", "yellow"))
                    code_str = str(result_code) if result_code else ""
                    explanation = src_fix.get(code_str, f"{name_err} is not responding correctly.")
                    fix_action = src_fix.get("fix", "Check the source's website and verify your API key.")
                    icon = "🔴" if result_color == "red" else "🟡"
                    st.html(f"""
<div style="background:var(--bc-bg-card);border:1px solid {'#e04040' if result_color == 'red' else '#e8a020'};border-radius:8px;padding:12px 16px;margin-bottom:8px;">
  <div style="font-size:18px;font-weight:700;color:var(--bc-text);margin-bottom:4px;">{icon} {name_err} — Code {result_code}</div>
  <div style="font-size:15px;color:#9aa8b8;margin-bottom:6px;">{explanation}</div>
  <div style="font-size:14px;color:#0ea5a0;">→ {fix_action}</div>
</div>""")

    if results:
        for src in _PING_SOURCES:
            name = src["name"]
            desc = src["description"]
            code, detail, color = results.get(name, (None, "Not checked yet", "yellow"))

            # Key status
            key_label = src.get("count_key")
            if key_label:
                has_key = bool(st.secrets.get(key_label, ""))
                key_str = "🟢 Key set" if has_key else "🔴 Key missing"
            else:
                key_str = "🟢 No key needed"

            # Usage + gate
            bkey = src.get("budget_key")
            if bkey and bkey in API_BUDGETS:
                usage_str = api_budget_status(bkey)
                allowed_b, _ = api_budget_check(bkey)
                gate_str = "✅ Open" if allowed_b else "🛑 Blocked"
            else:
                usage_str = "—"
                gate_str  = "✅ Open"

            dot = _DOT.get(color, "🟡")
            css = _COLOR_CSS.get(color, "")

            st.html(f"""
<div style="padding:12px 16px; margin-bottom:10px; border-radius:8px; {css}">
  <div style="display:flex; justify-content:space-between; align-items:center;">
    <div>
      <span style="font-size:15px; font-weight:700; color:var(--bc-text);">{dot} {name}</span>
      <span style="font-size:15px; color:#8899aa; margin-left:10px;">{desc}</span>
    </div>
    <span style="font-size:15px; color:#aabbcc;">Code: {code if code else "—"}</span>
  </div>
  <div style="margin-top:6px; font-size:16px; color:#ccd8e8;">{detail}</div>
  <div style="margin-top:8px; display:flex; gap:24px; font-size:15px; color:#8899aa;">
    <span><b>Key:</b> {key_str}</span>
    <span><b>Usage:</b> {usage_str}</span>
    <span><b>Gate:</b> {gate_str}</span>
  </div>
</div>
""")
    else:
        st.info("Hit **🔄 Refresh All** to check all API sources.")
    st.markdown("---")
    st.markdown("**\U0001f4be Data Persistence Status**")
    if GITHUB_TOKEN and GITHUB_GIST_ID:
        st.success("\u2705 GitHub Gist persistence active")
    else:
        st.error("\u26a0\ufe0f No persistence configured")
    st.markdown("---")
    st.markdown("**Cache Management**")
    cache_cols_s = st.columns(3)
    with cache_cols_s[0]:
        if st.button("Clear NBA Cache"):
            for f in ["nba_rolling_avgs.pkl", "nba_team_defense.pkl"]:
                p = os.path.join(CACHE_DIR, f)
                if os.path.exists(p):
                    os.remove(p)
            st.success("NBA cache cleared")

    st.markdown("---")
    st.markdown("**PrizePicks Cache**")
    col_pp1, col_pp2 = st.columns(2)
    with col_pp1:
        if st.button("🧹 Clear All Prop Cache", key="clear_pp_cache"):
            st.cache_data.clear()
            cleared = 0
            for f in os.listdir(CACHE_DIR):
                if f.endswith(".pkl") and any(x in f for x in ["_pp","prizepicks","parlayplay","oddspapi","oddsapi","oddswrap","underdog","sleeper"]):
                    try:
                        os.remove(os.path.join(CACHE_DIR, f))
                        cleared += 1
                    except (OSError, IOError):
                        pass
            # Reset status keys
            for _sk in ["pp_status","pp_source","scrapeops_exhausted","scraperapi_exhausted"]:
                if _sk in st.session_state:
                    del st.session_state[_sk]
            st.success(f"✅ Cleared {cleared} cache files + reset status flags — reload now")
    with col_pp2:
        pp_cache_files = [f for f in os.listdir(CACHE_DIR) if f.endswith("_pp.pkl")]
        pp_cache_age = 0
        if pp_cache_files:
            oldest = min(os.path.getmtime(os.path.join(CACHE_DIR, f)) for f in pp_cache_files)
            pp_cache_age = int((time.time() - oldest) / 60)
        st.caption(f"Cache files: {len(pp_cache_files)} | Oldest: {pp_cache_age}m ago")
    with cache_cols_s[1]:
        if st.button("Clear All Rolling Caches"):
            for f in os.listdir(CACHE_DIR):
                if f.endswith("_rolling_avgs.pkl") or f.endswith("_team_defense.pkl"):
                    os.remove(os.path.join(CACHE_DIR, f))
            st.success("All rolling caches cleared")
    with cache_cols_s[2]:
        if st.button("Clear All API Counters"):
            for budget_c in API_BUDGETS.values():
                path_c = budget_c["counter_path"]
                if os.path.exists(path_c):
                    os.remove(path_c)
            st.success("API counters reset")
    st.markdown("---")
    col_s1, col_s2 = st.columns(2)
    if col_s1.button("\U0001f504 Reset Session State"):
        # Clear Streamlit function caches (removes stale 429/403 responses)
        st.cache_data.clear()
        # Clear session state (keeps bankroll/history)
        keep = ["bankroll","history","locks","persistence_loaded","day_start_br","session_start"]
        for k in list(st.session_state.keys()):
            if k not in keep:
                del st.session_state[k]
        # Clear ALL pkl cache files
        _cleared_count = 0
        for _cf in os.listdir(CACHE_DIR):
            if _cf.endswith(".pkl"):
                try:
                    os.remove(os.path.join(CACHE_DIR, _cf))
                    _cleared_count += 1
                except (OSError, IOError):
                    pass
        # Clear API counters
        for _bc in API_BUDGETS.values():
            _cp = _bc.get("counter_path","")
            if _cp and os.path.exists(_cp):
                try:
                    os.remove(_cp)
                except (OSError, IOError):
                    pass
        st.success(f"✅ Full reset: session cleared, {_cleared_count} cache files removed, API counters reset")
        st.rerun()
    if col_s2.button("\U0001f9f9 Clean Old Cache Files"):
        cleaned = 0
        cutoff = time.time() - (7*24*3600)
        keep_files = ["history.json","locks.json","bankroll.json","calibration.json","line_movement.json","clv_tracking.json"]
        for f in os.listdir(CACHE_DIR):
            fp = os.path.join(CACHE_DIR, f)
            if os.path.isfile(fp) and f not in keep_files and os.path.getmtime(fp) < cutoff:
                os.remove(fp)
                cleaned += 1
        st.success(f"Cleaned {cleaned} old files")

    st.markdown("---")
    with st.expander("🔧 Developer Tools — Test Box Score APIs", expanded=False):
        st.markdown("#### 🧪 Test Box Score APIs")
        # Show ScrapeOps debug log
        scrapeops_log = st.session_state.get("scrapeops_log", [])
        if scrapeops_log:
            with st.expander(f"🔍 ScrapeOps Debug Log ({len(scrapeops_log)} calls)"):
                for entry in scrapeops_log[-10:]:
                    if "error" in entry:
                        st.caption(f"❌ {entry['url']} — {entry['error']}")
                    else:
                        icon = "✅" if entry['status']==200 and not entry['html'] else "⚠️"
                        st.caption(f"{icon} {entry['url']} — {entry['status']} {entry['size']}b HTML:{entry['html']} CT:{entry['ct']}")

        if st.button("🔍 Test ScrapeOps Proxy", key="test_scrapeops"):
            if not SCRAPEOPS_KEY:
                st.error("SCRAPEOPS_KEY not in Secrets")
            else:
                with st.spinner("Testing ScrapeOps..."):
                    try:
                        # Test 1: Basic connectivity
                        r1 = _http.get(
                            "https://proxy.scrapeops.io/v1/",
                            params={"api_key": SCRAPEOPS_KEY, "url": "https://httpbin.org/ip"},
                            timeout=15
                        )
                        if r1.status_code == 200:
                            ip = r1.json().get("origin","?")
                            st.success(f"✅ ScrapeOps working — routing through IP: {ip}")
                        else:
                            st.error(f"❌ ScrapeOps: {r1.status_code} — {r1.text[:100]}")

                        # Test 2: PrizePicks through ScrapeOps
                        r2 = _http.get(
                            "https://proxy.scrapeops.io/v1/",
                            params={"api_key": SCRAPEOPS_KEY, "url": "https://api.prizepicks.com/projections?league_id=4&per_page=10", "residential": "true", "country": "us"},
                            timeout=20
                        )
                        st.write(f"PrizePicks via ScrapeOps: {r2.status_code} — {len(r2.text)} bytes")

                        # Test 3: Kalshi through ScrapeOps
                        r3 = _http.get(
                            "https://proxy.scrapeops.io/v1/",
                            params={"api_key": SCRAPEOPS_KEY, "url": "https://api.elections.kalshi.com/v1/events/?series_tickers=KXNBA-26&page_size=5"},
                            timeout=20
                        )
                        if r3.status_code == 200:
                            data = r3.json()
                            events = data.get("events", [])
                            st.success(f"✅ Kalshi via ScrapeOps: {len(events)} events")
                        else:
                            st.write(f"Kalshi via ScrapeOps: {r3.status_code}")
                    except (requests.RequestException, KeyError, ValueError) as e:
                        st.error("Data unavailable — Kalshi/ScrapeOps request failed.")
                        st.caption(f"Detail: {str(e)[:100]}")

        if st.button("Test ESPN + NBA APIs", key="test_boxscore_apis"):
            test_urls = [
                ("ESPN web", "https://site.web.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event=401584793&region=us&lang=en&contentorigin=espn"),
                ("NBA CDN", "https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json"),
                ("NBA Stats", "https://stats.nba.com/stats/scoreboardv2?DayOffset=0&LeagueID=00&gameDate=05%2F27%2F2026"),
            ]
            for name, url in test_urls:
                try:
                    r = _http.get(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json", "Referer": "https://www.espn.com/", "x-nba-stats-origin": "stats", "x-nba-stats-token": "true"}, timeout=8)
                    if r.status_code == 200:
                        st.success(f"✅ {name}: 200 OK — {len(r.text)} bytes")
                    else:
                        st.error(f"❌ {name}: {r.status_code}")
                except (requests.RequestException, KeyError, ValueError) as e:
                    st.error(f"Data unavailable — {name} request failed.")
                    st.caption(f"Detail: {str(e)[:50]}")

    st.markdown("---")
    st.markdown("#### 🗑️ Reset Bet History")
    st.warning("⚠️ This permanently deletes all logged bets and resets your P&L to zero. Use this to start fresh with corrected data.")
    _confirm_reset = st.checkbox("I understand this cannot be undone", key="confirm_history_reset")
    if _confirm_reset:
        _reset_col1, _reset_col2 = st.columns(2)
        with _reset_col1:
            if st.button("🗑️ Clear History Only", key="clear_history_btn", type="primary"):
                st.session_state.history = []
                save_json_data(HISTORY_PATH, [])
                save_to_gist("history", [])
                st.success("✅ Bet history cleared. Ready for fresh data.")
                st.rerun()
        with _reset_col2:
            if st.button("🗑️ Full Reset (History + Calibration + Bankroll)", key="clear_history_br_btn"):
                # Clear history
                st.session_state.history = []
                save_json_data(HISTORY_PATH, [])
                save_to_gist("history", [])
                # Reset bankroll
                st.session_state.bankroll = 1000.0
                st.session_state["day_start_br"] = 1000.0
                save_json_data(BANKROLL_PATH, {"bankroll": 1000.0})
                save_to_gist("bankroll", {"bankroll": 1000.0})
                # Reset SEM calibration
                sem_path = os.path.join(CACHE_DIR, "sem_calibration.pkl")
                if os.path.exists(sem_path): os.remove(sem_path)
                st.session_state.pop("sem_calibration", None)
                # Reset signal performance tracker
                sig_path = os.path.join(CACHE_DIR, "signal_performance.pkl")
                if os.path.exists(sig_path): os.remove(sig_path)
                st.session_state.pop("signal_performance", None)
                # Reset weight optimizer
                wt_path = os.path.join(CACHE_DIR, "weight_optimizer.json")
                if os.path.exists(wt_path): os.remove(wt_path)
                st.session_state.pop("optimized_weights", None)
                # Reset CLV tracking
                clv_path = os.path.join(CACHE_DIR, "clv_tracking.json")
                if os.path.exists(clv_path): os.remove(clv_path)
                save_to_gist("clv_tracking", [])
                # Reset ROI tracking
                roi_path = os.path.join(CACHE_DIR, "roi_tracking.json")
                if os.path.exists(roi_path): os.remove(roi_path)
                # Clear trending picks
                st.session_state.pop("all_sports_best", None)
                st.session_state.pop("trending_picks", None)
                st.success("✅ Full reset complete — history, calibration, SEM, CLV, weights, bankroll all cleared.")
                st.rerun()



with tabs[11]:
    try:
        render_sharptrack_tab()
    except Exception as _sharptrack_render_err:
        st.error(f"SharpTrack hit an error: {_sharptrack_render_err}")
        st.caption("This is isolated to this tab — the rest of the app is unaffected.")


with tabs[1]:
    st.markdown(
        '<div style="background:linear-gradient(90deg,#0a5fa8,#0a1628);border-left:4px solid #1e90ff;'
        'border-radius:6px;padding:12px 16px;margin-bottom:14px;">'
        '<div style="color:#fff;font-weight:700;font-size:15px;">🎯 Pick For You</div>'
        '<div style="color:#8ab4d4;font-size:12.5px;margin-top:4px;">'
        'A shortlist for when you don\'t have time to read the full board — only SOVEREIGN/ELITE plays, '
        'correlation-checked, with a go/caution/don\'t verdict already worked out, and how it compares '
        'to what\'s free and public elsewhere. Display layer only — never changes SEM, signal weights, '
        'or any stored performance data.'
        '</div></div>',
        unsafe_allow_html=True,
    )

    st.caption(
        "Scans every active sport's board and game lines, keeps only SOVEREIGN/ELITE plays, checks them "
        "against DraftKings/FavoredProps/BettingPros/Covers/Dimers/FanDuel, and drops anything too "
        "correlated with a pick already on the list. If nothing clears the bar today, it says so instead "
        "of padding the list with weaker plays."
    )
    if st.button("🔍 Build My Shortlist", key="nb_build_shortlist"):
        with st.spinner("Scanning all boards and checking public sources..."):
            _nb_sl = build_new_bettor_shortlist()
            st.session_state["nb_shortlist"] = _nb_sl
            st.session_state["nb_comparison"] = build_market_comparison(_nb_sl)

    shortlist = st.session_state.get("nb_shortlist")
    comparison = st.session_state.get("nb_comparison")

    _SOURCE_STYLE = {
        "dk":      {"label": "DK",          "color": "#ff8c00"},
        "fp":      {"label": "FavoredProps","color": "#a855f7"},
        "bp":      {"label": "BettingPros", "color": "#14b8a6"},
        "cov":     {"label": "Covers",      "color": "#3b82f6"},
        "dimers":  {"label": "Dimers",      "color": "#ec4899"},
        "de":      {"label": "DraftEdge",   "color": "#22c55e"},
        "mb":      {"label": "MyBookie",    "color": "#f59e0b"},
        "vi":      {"label": "VegasInsider","color": "#06b6d4"},
        "si":      {"label": "SportsInsights","color": "#a3e635"},
        "sao":     {"label": "ScoresAndOdds", "color": "#fb7185"},
        "pw":      {"label": "Pickswise",     "color": "#c084fc"},
        "an":      {"label": "ActionNetwork", "color": "#38bdf8"},
        "bq":      {"label": "BetQL",         "color": "#facc15"},
        "fd":      {"label": "FanDuel",     "color": "#1493ff"},
    }

    def _chip(source_key, text):
        s = _SOURCE_STYLE[source_key]
        return (
            f'<span style="display:inline-block;background:{s["color"]}22;color:{s["color"]};'
            f'border:1px solid {s["color"]}55;padding:2px 9px;border-radius:12px;font-size:11px;'
            f'font-weight:700;margin:3px 5px 0 0;white-space:nowrap;">{s["label"]} · {text}</span>'
        )

    def _nb_verdict_card(verdict):
        v = verdict["verdict"]
        v_color = {"GO": "#22c55e", "CAUTION": "#ff8c00", "DON'T": "#e04040", "—": "#6a7a8a"}.get(v, "#6a7a8a")
        st.markdown(
            f'<div style="background:#0d1b2e;border:1px solid {v_color};border-radius:8px;'
            f'padding:14px 16px;margin:6px 0 16px 0;">'
            f'<div style="color:{v_color};font-weight:800;font-size:17px;">{v} — combine these into one slip?</div>'
            f'<div style="color:#e6edf3;font-size:13px;margin-top:6px;">{verdict["reason"]}</div>'
            + (f'<div style="color:#f5c518;font-size:12.5px;margin-top:6px;"><b>Suggested fix:</b> {verdict["suggested_fix"]}</div>' if verdict["suggested_fix"] else '')
            + f'<div style="color:#4a6a8a;font-size:11px;margin-top:8px;">Correlation score: {verdict["correlation_score"]:.2f}</div>'
            + f'</div>', unsafe_allow_html=True
        )
        if verdict["correlated_pairs"]:
            with st.expander("Why the correlation score is what it is"):
                for pair in verdict["correlated_pairs"]:
                    st.write(f"• {pair}")

    if shortlist:
        st.caption(
            f"Last built {shortlist['timestamp']} · scanned: {', '.join(shortlist['scanned_sports']) or 'none'}"
            + (f" · skipped (off-season/error): {', '.join(shortlist['skipped_sports'])}" if shortlist['skipped_sports'] else "")
        )

        # ── Build per-source lookup indices for chip matching ───────────
        cmp = comparison or {}
        _dk_by_player = {row.get("matched_player", ""): row for row in cmp.get("dk_props", [])}
        _fp_by_player = {}
        for row in cmp.get("favoredprops", []):
            _fp_by_player.setdefault(str(row.get("player", "")).lower(), row)
        _de_by_player = {}
        for row in cmp.get("draftedge", []):
            _de_by_player.setdefault(str(row.get("Player", "")).lower(), row)
        _bp_by_matchup = {row.get("matchup", ""): row for row in cmp.get("bettingpros", [])}
        _cov_by_matchup = {row.get("matchup", ""): row for row in cmp.get("covers", [])}
        _dimers_by_matchup = {row.get("matchup", ""): row for row in cmp.get("dimers", [])}
        _mybookie_by_matchup = {row.get("matchup", ""): row for row in cmp.get("mybookie", [])}
        _vegasinsider_by_matchup = {row.get("matchup", ""): row for row in cmp.get("vegasinsider", [])}
        _sportsinsights_by_matchup = {row.get("matchup", ""): row for row in cmp.get("sportsinsights", [])}
        _scoresandodds_by_matchup = {row.get("matchup", ""): row for row in cmp.get("scoresandodds", [])}
        _pickswise_by_matchup = {row.get("matchup", ""): row for row in cmp.get("pickswise", [])}
        _actionnetwork_by_matchup = {row.get("matchup", ""): row for row in cmp.get("actionnetwork", [])}
        _betql_by_matchup = {row.get("matchup", ""): row for row in cmp.get("betql", [])}

        st.markdown("#### ⭐ Top Props")
        if not shortlist["props"]:
            st.info("No SOVEREIGN/ELITE props cleared the bar right now — pass on props today.")
        else:
            prop_cols = st.columns(2)
            for _i, p in enumerate(shortlist["props"]):
                tc = TIER_COLORS.get(p["Tier"], "#6a7a8a")
                chips = ""
                _dk_row = _dk_by_player.get(p["Player"])
                if _dk_row:
                    chips += _chip("dk", "also most-bet")
                _fp_row = _fp_by_player.get(p["Player"].lower())
                if _fp_row:
                    _fp_hit = _fp_row.get("l10_hit_rate")
                    _fp_txt = f"{_fp_hit:.0%} L10" if isinstance(_fp_hit, (int, float)) else f'{_fp_row.get("n_books","?")} books'
                    chips += _chip("fp", _fp_txt)
                _de_row = _de_by_player.get(p["Player"].lower())
                if _de_row:
                    _de_pitcher = _de_row.get("OppPitcher_PitcherName")
                    _de_txt = f"vs {_de_pitcher}" if _de_pitcher else "matchup data"
                    chips += _chip("de", _de_txt)
                with prop_cols[_i % 2]:
                    st.markdown(
                        f'<div style="background:linear-gradient(145deg,#0d1b2e,#0a1420);border:1px solid #1a3a5c;'
                        f'border-left:5px solid {tc};border-radius:10px;padding:12px 14px;margin-bottom:10px;'
                        f'box-shadow:0 2px 8px rgba(0,0,0,0.25);">'
                        f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                        f'<div style="color:#fff;font-weight:800;font-size:14px;">{p["Player"]}</div>'
                        f'<span style="background:{tc};color:#0a1420;padding:2px 10px;border-radius:4px;font-weight:800;font-size:11px;">{p["Tier"]}</span>'
                        f'</div>'
                        f'<div style="color:{tc};font-weight:700;font-size:13px;margin-top:2px;">{p["Prop"]} {p["Side"]} {p["Line"]}</div>'
                        f'<div style="color:#8ab4d4;font-size:11.5px;margin-top:4px;">{p["Sport"]} · Edge {p["EdgePct"]} · 2-pick EV {p["EV_2pick"]}</div>'
                        + (f'<div style="margin-top:8px;">{chips}</div>' if chips else '')
                        + f'</div>', unsafe_allow_html=True
                    )
            st.markdown("**🧮 Should you parlay these props together?**")
            props_legs = [{**p, "leg_type": "prop"} for p in shortlist["props"]]
            _nb_verdict_card(evaluate_parlay_verdict(props_legs))

        st.markdown("#### 🏟️ Top Game Lines")
        if not shortlist["games"]:
            st.info("No SOVEREIGN/ELITE game lines cleared the bar right now — pass on game lines today.")
        else:
            game_cols = st.columns(2)
            for _i, g in enumerate(shortlist["games"]):
                tc = TIER_COLORS.get(g["Tier"], "#6a7a8a")
                chips = ""
                _bp_row = _bp_by_matchup.get(g["Matchup"])
                if _bp_row:
                    chips += _chip("bp", str(_bp_row.get("pick", ""))[:24])
                _cov_row = _cov_by_matchup.get(g["Matchup"])
                if _cov_row:
                    chips += _chip("cov", f'{_cov_row.get("home_pct","?")}% home')
                _dm_row = _dimers_by_matchup.get(g["Matchup"])
                if _dm_row:
                    _dm_h, _dm_a = _dm_row.get("home_edge"), _dm_row.get("away_edge")
                    if isinstance(_dm_h, (int, float)) and isinstance(_dm_a, (int, float)):
                        _dm_side = "home" if _dm_h > _dm_a else "away"
                        _dm_edge = _dm_h if _dm_h > _dm_a else _dm_a
                        chips += _chip("dimers", f"{_dm_side} {_dm_edge:+.1f}%")
                _mb_row = _mybookie_by_matchup.get(g["Matchup"])
                if _mb_row and _mb_row.get("ml_odds"):
                    chips += _chip("mb", f'{_mb_row.get("ml_team","")[:12]} {_mb_row.get("ml_odds","")}')
                _vi_row = _vegasinsider_by_matchup.get(g["Matchup"])
                if _vi_row and _vi_row.get("trends"):
                    _vi_top = max(_vi_row["trends"], key=lambda t: int(str(t.get("ml_pct","0%")).rstrip("%") or 0))
                    chips += _chip("vi", f'{_vi_top.get("team","")} {_vi_top.get("ml_pct","")} public')
                _si_row = _sportsinsights_by_matchup.get(g["Matchup"])
                if _si_row and _si_row.get("home_pct_ml") is not None:
                    _si_ml = _si_row["home_pct_ml"]
                    _si_side = _si_row.get("home_abv","") if _si_ml >= 50 else _si_row.get("away_abv","")
                    _si_pct = _si_ml if _si_ml >= 50 else 100 - _si_ml
                    chips += _chip("si", f'{_si_side} {_si_pct}% tickets ({_si_row.get("total_bets","?")})')
                _sao_row = _scoresandodds_by_matchup.get(g["Matchup"])
                if _sao_row and _sao_row.get("moneyline", {}).get("home") is not None:
                    _sao_ml = _sao_row["moneyline"]
                    _sao_nbooks = len(_sao_ml.get("comparison", {}))
                    chips += _chip("sao", f'{_sao_row.get("home_team","")} {_sao_ml.get("home","")} ({_sao_nbooks} books)')
                _pw_row = _pickswise_by_matchup.get(g["Matchup"])
                if _pw_row and _pw_row.get("pick_side"):
                    _pw_stars = "★" * int(_pw_row.get("pick_rating") or 0)
                    chips += _chip("pw", f'{_pw_row["pick_side"]} {_pw_row.get("pick_bet","")} {_pw_stars}')
                _an_row = _actionnetwork_by_matchup.get(g["Matchup"])
                if _an_row and _an_row.get("odds"):
                    _an_book = _an_row["odds"][0]
                    _an_nbooks = len(_an_row["odds"])
                    chips += _chip("an", f'ML {_an_row.get("home_team","")} {_an_book.get("ml_home","")} ({_an_nbooks} books)')
                _bq_row = _betql_by_matchup.get(g["Matchup"])
                if _bq_row and _bq_row.get("home_record", {}).get("atswins") is not None:
                    _bq_hr = _bq_row["home_record"]
                    chips += _chip("bq", f'{_bq_row.get("home_team","")} ATS {_bq_hr.get("atswins")}-{_bq_hr.get("atslosses")}')
                with game_cols[_i % 2]:
                    st.markdown(
                        f'<div style="background:linear-gradient(145deg,#0d1b2e,#0a1420);border:1px solid #1a3a5c;'
                        f'border-left:5px solid {tc};border-radius:10px;padding:12px 14px;margin-bottom:10px;'
                        f'box-shadow:0 2px 8px rgba(0,0,0,0.25);">'
                        f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                        f'<div style="color:#fff;font-weight:800;font-size:14px;">{g["Matchup"]}</div>'
                        f'<span style="background:{tc};color:#0a1420;padding:2px 10px;border-radius:4px;font-weight:800;font-size:11px;">{g["Tier"]}</span>'
                        f'</div>'
                        f'<div style="color:{tc};font-weight:700;font-size:13px;margin-top:2px;">{g["BetType"]}: {g["Pick"]}</div>'
                        f'<div style="color:#8ab4d4;font-size:11.5px;margin-top:4px;">{g["Sport"]} · Edge {g["EdgePct"]}</div>'
                        + (f'<div style="margin-top:8px;">{chips}</div>' if chips else '')
                        + f'</div>', unsafe_allow_html=True
                    )
            st.markdown("**🧮 Should you parlay these game lines together?**")
            games_legs = [{**g, "leg_type": "game"} for g in shortlist["games"]]
            _nb_verdict_card(evaluate_parlay_verdict(games_legs))

        if shortlist["props"] and shortlist["games"]:
            st.markdown("**🧮 Should you parlay props + game lines together, all in one slip?**")
            _nb_verdict_card(evaluate_parlay_verdict(props_legs + games_legs))
    else:
        st.caption("Click the button above to scan today's boards and check them against the public sources.")


with tabs[6]:
    # ── Market Scanner ──────────────────────────────────────────────
    # Cross-sport view: merges TODAY's latest board_snapshot per sport
    # (the same real data source Spotlight History and the signal-
    # backfill lookup already depend on) into one ranked list, since
    # Full Board only ever shows one sport at a time. No new data
    # source, no new infrastructure -- just a different lens on data
    # that's already being saved every time a board loads.
    #
    # Distinct violet visual treatment (scoped to .ms-* classes only,
    # doesn't touch the app-wide --bc-* blue palette used everywhere
    # else) per the user's reference image -- a trading/crypto-screener
    # look (Finviz/TradingView-style dense sortable table + glow cards),
    # not the sports-betting-site look used for the rest of the app.
    st.html("""
    <style>
    .ms-card {
        background: linear-gradient(160deg, #1a1230 0%, #12091f 100%);
        border: 1px solid rgba(168,120,255,0.25);
        border-radius: 12px;
        padding: 16px 18px;
        box-shadow: 0 0 24px rgba(140,90,255,0.08), 0 2px 8px rgba(0,0,0,0.4);
    }
    .ms-label {
        font-size: 11px;
        color: #9a86c9;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        margin-bottom: 4px;
    }
    .ms-value {
        font-size: 1.6rem;
        font-weight: 800;
        color: #f3eeff;
    }
    .ms-glow-line {
        height: 2px;
        background: linear-gradient(90deg, #a878ff, #6b46c1, transparent);
        border-radius: 2px;
        margin: 10px 0 16px;
        opacity: 0.6;
    }
    .ms-row {
        display: grid;
        grid-template-columns: 14px 150px 60px 90px 55px 70px 70px 60px;
        gap: 8px;
        align-items: center;
        padding: 8px 10px;
        border-bottom: 1px solid rgba(168,120,255,0.08);
        font-size: 13px;
        transition: background 150ms ease;
    }
    .ms-row:hover { background: rgba(168,120,255,0.06); }
    .ms-header-row {
        display: grid;
        grid-template-columns: 14px 150px 60px 90px 55px 70px 70px 60px;
        gap: 8px;
        padding: 6px 10px;
        font-size: 11px;
        color: #9a86c9;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        border-bottom: 1px solid rgba(168,120,255,0.2);
    }
    .ms-edge-bar-bg {
        background: rgba(168,120,255,0.1);
        border-radius: 3px;
        height: 6px;
        width: 100%;
        overflow: hidden;
    }
    .ms-edge-bar-fill {
        height: 100%;
        background: linear-gradient(90deg, #6b46c1, #a878ff);
        border-radius: 3px;
    }
    </style>
    """)

    st.markdown('<div style="font-size:1.3rem;font-weight:800;color:#f3eeff;margin-bottom:2px;">🔭 Market Scanner</div>', unsafe_allow_html=True)
    st.caption("Every sport's board merged into one ranked list — real data from today's saved board snapshots, no new source.")

    try:
        _ms_today = date.today().strftime("%Y-%m-%d")
        _ms_snaps = load_from_gist("board_snapshots", None) or {}
        _ms_today_snaps = {k: v for k, v in _ms_snaps.items() if v.get("date") == _ms_today}

        # Latest snapshot per sport only -- multiple loads/day shouldn't
        # duplicate props, just reflect the most recent board state.
        _ms_latest_per_sport = {}
        for snap in _ms_today_snaps.values():
            _sp = snap.get("sport", "")
            _ts = snap.get("timestamp", "")
            if _sp not in _ms_latest_per_sport or _ts > _ms_latest_per_sport[_sp].get("timestamp", ""):
                _ms_latest_per_sport[_sp] = snap

        _ms_all_props = []
        for sport, snap in _ms_latest_per_sport.items():
            for p in snap.get("props", []):
                _ms_all_props.append({**p, "sport": sport})

        if not _ms_all_props:
            st.info("No sports loaded yet today — load a board in Full Board first, then check back here.")
        else:
            _ms_all_props.sort(key=lambda p: abs(p.get("edge", 0) or 0), reverse=True)
            _ms_sports_active = sorted(_ms_latest_per_sport.keys())
            _ms_avg_edge = sum(abs(p.get("edge", 0) or 0) for p in _ms_all_props) / len(_ms_all_props)
            _ms_top_edge = _ms_all_props[0]

            # ── Top stat row ──
            _ms_c1, _ms_c2, _ms_c3, _ms_c4 = st.columns(4)
            with _ms_c1:
                st.markdown(f'<div class="ms-card"><div class="ms-label">Props Scanned</div><div class="ms-value">{len(_ms_all_props)}</div></div>', unsafe_allow_html=True)
            with _ms_c2:
                st.markdown(f'<div class="ms-card"><div class="ms-label">Sports Active Today</div><div class="ms-value">{len(_ms_sports_active)}</div></div>', unsafe_allow_html=True)
            with _ms_c3:
                st.markdown(f'<div class="ms-card"><div class="ms-label">Avg Edge</div><div class="ms-value">{_ms_avg_edge*100:.1f}%</div></div>', unsafe_allow_html=True)
            with _ms_c4:
                st.markdown(f'<div class="ms-card"><div class="ms-label">Top Edge Right Now</div><div class="ms-value" style="font-size:1.1rem;">{_ms_top_edge.get("player","")[:16]}</div></div>', unsafe_allow_html=True)

            st.markdown('<div class="ms-glow-line"></div>', unsafe_allow_html=True)

            # ── Sort control ──
            _ms_sort = st.selectbox("Sort by", ["Edge", "Tier", "Sport"], key="ms_sort")
            if _ms_sort == "Tier":
                _tier_order = {"SOVEREIGN": 0, "ELITE": 1, "APPROVED": 2, "LEAN": 3}
                _ms_all_props.sort(key=lambda p: _tier_order.get(p.get("tier", ""), 4))
            elif _ms_sort == "Sport":
                _ms_all_props.sort(key=lambda p: p.get("sport", ""))

            _ms_tier_colors = {"SOVEREIGN": "#f5c518", "ELITE": "#a878ff", "APPROVED": "#22c55e", "LEAN": "#6a7a8a"}
            _ms_max_edge = max(abs(p.get("edge", 0) or 0) for p in _ms_all_props) or 1

            st.markdown(
                '<div class="ms-header-row"><span></span><span>Player</span><span>Sport</span>'
                '<span>Prop</span><span>Line</span><span>Edge</span><span>Model %</span><span>Tier</span></div>',
                unsafe_allow_html=True
            )
            _ms_rows_html = ""
            for p in _ms_all_props[:60]:
                _tc = _ms_tier_colors.get(p.get("tier", ""), "#6a7a8a")
                _edge_pct = (p.get("edge", 0) or 0) * 100
                _edge_bar_w = min(100, abs(p.get("edge", 0) or 0) / _ms_max_edge * 100)
                _prob_pct = (p.get("prob", 0.5) or 0.5) * 100
                _ms_rows_html += (
                    f'<div class="ms-row">'
                    f'<span style="width:8px;height:8px;border-radius:50%;background:{_tc};display:inline-block;"></span>'
                    f'<span style="color:#f3eeff;">{p.get("player","")[:20]}</span>'
                    f'<span style="color:#9a86c9;font-size:11px;">{p.get("sport","")}</span>'
                    f'<span style="color:#c9bce8;font-size:12px;">{p.get("side","")} {p.get("prop","")[:14]}</span>'
                    f'<span style="color:#c9bce8;">{p.get("line","")}</span>'
                    f'<span><div class="ms-edge-bar-bg"><div class="ms-edge-bar-fill" style="width:{_edge_bar_w}%;"></div></div>'
                    f'<span style="font-size:11px;color:#a878ff;">{_edge_pct:+.1f}%</span></span>'
                    f'<span style="color:#c9bce8;">{_prob_pct:.0f}%</span>'
                    f'<span style="color:{_tc};font-weight:700;font-size:11px;">{p.get("tier","")}</span>'
                    f'</div>'
                )
            st.markdown(f'<div class="ms-card" style="padding:4px 8px;">{_ms_rows_html}</div>', unsafe_allow_html=True)
            if len(_ms_all_props) > 60:
                st.caption(f"Showing top 60 of {len(_ms_all_props)} props by {_ms_sort.lower()}.")
    except Exception as _ms_err:
        st.info("Market Scanner data unavailable right now — try loading a board first.")
        st.caption(f"Debug: {type(_ms_err).__name__}: {_ms_err}")

    # ── Kalshi order book ──────────────────────────────────────────
    # Real bid/ask spread + volume/liquidity/open interest per market
    # (same fields the Game Lines Kalshi block reads, just shown per-market
    # instead of collapsed to one midpoint %). For multi-strike totals
    # events, shows the real implied-probability distribution across
    # strikes instead of just the top market -- genuine depth data that
    # was already being fetched but not displayed anywhere.
    try:
        _mko_events = st.session_state.get("kalshi_events_scraped", [])
    except Exception:
        _mko_events = []
    if _mko_events:
        st.markdown('<div class="ms-glow-line" style="margin-top:1.2rem;"></div>', unsafe_allow_html=True)
        st.markdown('<div style="font-size:1.1rem;font-weight:800;color:#f3eeff;margin-bottom:2px;">🔷 Kalshi Order Book</div>', unsafe_allow_html=True)
        st.caption("Real bid/ask spread, volume, liquidity, and open interest per market. Multi-strike totals show the full implied-probability distribution.")

        def _mko_vol(ev):
            tot = 0.0
            for m in ev.get("markets", []):
                try:
                    tot += float(m.get("volume") or 0)
                except (TypeError, ValueError):
                    pass
            return tot

        for _mko_ev in sorted(_mko_events, key=_mko_vol, reverse=True)[:8]:
            _mko_markets = _mko_ev.get("markets") or []
            if not _mko_markets:
                continue
            st.markdown(
                f'<div class="ms-card" style="padding:10px 14px;margin-bottom:10px;">'
                f'<div style="color:#f3eeff;font-weight:700;font-size:1.0rem;margin-bottom:6px;">'
                f'{_mko_ev.get("title","")} <span style="color:#9a86c9;font-size:11px;font-weight:400;">· {_mko_ev.get("sport","")}</span></div>',
                unsafe_allow_html=True
            )
            _mko_sorted_markets = sorted(_mko_markets, key=lambda x: float(x.get("volume") or 0), reverse=True)
            for _mm in _mko_sorted_markets[:6]:
                try:
                    _mko_bid = float(_mm.get("yes_bid") or 0)
                    _mko_ask = float(_mm.get("yes_ask") or 0)
                except (TypeError, ValueError):
                    _mko_bid, _mko_ask = 0.0, 0.0
                _mko_bid_pct = max(0.0, min(100.0, _mko_bid * 100))
                _mko_ask_pct = max(0.0, min(100.0, _mko_ask * 100))
                def _mko_num(v):
                    try:
                        return float(v or 0)
                    except (TypeError, ValueError):
                        return 0.0
                _mko_vol_val = _mko_num(_mm.get("volume"))
                _mko_liq = _mko_num(_mm.get("liquidity"))
                _mko_oi = _mko_num(_mm.get("open_interest"))
                st.markdown(
                    f'<div style="margin-bottom:8px;">'
                    f'<div style="display:flex;justify-content:space-between;font-size:12px;color:#c9bce8;margin-bottom:2px;">'
                    f'<span>{_mm.get("title","")}</span>'
                    f'<span>Bid {_mko_bid*100:.0f}¢ / Ask {_mko_ask*100:.0f}¢</span>'
                    f'</div>'
                    f'<div style="position:relative;height:10px;border-radius:5px;background:#1a1428;overflow:hidden;">'
                    f'<div style="position:absolute;left:0;width:{_mko_bid_pct}%;height:100%;background:#22c55e88;"></div>'
                    f'<div style="position:absolute;right:0;width:{100-_mko_ask_pct}%;height:100%;background:#e0404088;"></div>'
                    f'</div>'
                    f'<div style="font-size:11px;color:#7a6a9c;margin-top:2px;">'
                    f'Volume ${_mko_vol_val:,.0f} · Liquidity ${_mko_liq:,.0f} · Open Interest {_mko_oi:,.0f}'
                    f'</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )
            st.markdown('</div>', unsafe_allow_html=True)


with tabs[2]:
    st.markdown(
        '<div style="background:linear-gradient(90deg,#0a5fa8,#0a1628);border-left:4px solid #1e90ff;'
        'border-radius:6px;padding:12px 16px;margin-bottom:14px;">'
        '<div style="color:#fff;font-weight:700;font-size:15px;">🔮 Predictions</div>'
        '<div style="color:#8ab4d4;font-size:12.5px;margin-top:4px;">'
        'Each source\'s own independent picks — player props and game lines — shown as-is, '
        'not filtered through our own model. Different from "Why this pick" elsewhere, which only '
        'shows whether a source agrees or disagrees with a pick we already made.'
        '</div></div>',
        unsafe_allow_html=True
    )

    _pred_sport_filter = st.selectbox("Sport", ["All", "MLB", "NBA", "NFL", "NHL", "WNBA", "SOCCER", "UFC", "TENNIS"], key="pred_sport_filter")

    def _pred_sport_match(s):
        return _pred_sport_filter == "All" or str(s or "").upper() == _pred_sport_filter

    # Abbreviation -> full team name, so substring matching works no matter
    # which name format a given source uses (bare mascot like "Phillies",
    # city-only, or full name) -- the full name contains all of them as
    # substrings. Confirmed real bug: the existing TEAM_ABBREV_TO_FRAGMENT
    # only disambiguates city vs city (built for a different matching
    # scenario), so e.g. "PHI"->"Philadelphia" never matched WiseGuyTeam's
    # bare "Phillies" and silently broke grouping for most MLB games.
    _PRED_MLB_FULL_NAMES = {
        "ARI": "Arizona Diamondbacks", "ATL": "Atlanta Braves", "BAL": "Baltimore Orioles",
        "BOS": "Boston Red Sox", "CHC": "Chicago Cubs", "CWS": "Chicago White Sox",
        "CIN": "Cincinnati Reds", "CLE": "Cleveland Guardians", "COL": "Colorado Rockies",
        "DET": "Detroit Tigers", "HOU": "Houston Astros", "KC": "Kansas City Royals",
        "LAA": "Los Angeles Angels", "LAD": "Los Angeles Dodgers", "MIA": "Miami Marlins",
        "MIL": "Milwaukee Brewers", "MIN": "Minnesota Twins", "NYM": "New York Mets",
        "NYY": "New York Yankees", "OAK": "Athletics", "ATH": "Athletics",
        "PHI": "Philadelphia Phillies", "PIT": "Pittsburgh Pirates", "SD": "San Diego Padres",
        "SEA": "Seattle Mariners", "SF": "San Francisco Giants", "STL": "St. Louis Cardinals",
        "TB": "Tampa Bay Rays", "TEX": "Texas Rangers", "TOR": "Toronto Blue Jays",
        "WSH": "Washington Nationals",
    }

    def _pred_norm_team(s):
        raw = str(s or "").strip()
        if 2 <= len(raw) <= 3 and raw.isupper() and raw in _PRED_MLB_FULL_NAMES:
            raw = _PRED_MLB_FULL_NAMES[raw]
        elif 2 <= len(raw) <= 4 and raw.isupper():
            for _sport_map in TEAM_ABBREV_TO_FRAGMENT.values():
                if raw in _sport_map:
                    raw = _sport_map[raw]
                    break
        return re.sub(r"[^a-z0-9]", "", raw.lower())

    def _pred_teams_match(a, b):
        na, nb = _pred_norm_team(a), _pred_norm_team(b)
        if not na or not nb:
            return False
        return na in nb or nb in na

    # ══════════════════════════════════════════════════════════════════
    # COLLECT — every source's game-line pick into one flat list, tagged
    # with source name and a short human-readable pick summary.
    # ══════════════════════════════════════════════════════════════════
    _pred_gl_items = []

    _pred_bl_sports = [s for s in ("MLB", "NBA", "NFL", "NHL", "WNBA", "SOCCER") if _pred_sport_match(s)]
    _pred_bl_fns = [(lambda _s=_s: fetch_betslib_predictions(_s)) for _s in _pred_bl_sports]
    _pred_bl_results = _fetch_parallel(_pred_bl_fns, show_progress=False)
    for _pred_sport, _bl_preds_for_sport in zip(_pred_bl_sports, _pred_bl_results):
        try:
            for p in (_bl_preds_for_sport or []):
                _pick = p.get("pick", "")
                if _pick and _pick in (p.get("home", ""), p.get("away", "")):
                    _pred_gl_items.append({
                        "sport": _pred_sport, "away": p.get("away", ""), "home": p.get("home", ""),
                        "source": "Signal Odds",
                        "text": f"{_pick} · {p.get('confidence', 0):.0%} conf, EV {p.get('ev', 0):+.1%}"
                    })
        except Exception:
            pass

    try:
        for a in fetch_signalodds_arbitrage_from_gist():
            if a.get("locked"):
                continue
            if not _pred_sport_match(a.get("sport", "")):
                continue
            _pred_gl_items.append({
                "sport": a.get("sport", ""), "away": a.get("away_team", ""), "home": a.get("home_team", ""),
                "source": "Signal Odds", "text": f"Arbitrage · {a.get('margin_percent', 0)}% margin"
            })
    except Exception:
        pass

    _pred_glp_sports = [s for s in ("MLB", "NBA", "NFL", "NHL") if _pred_sport_match(s)]
    _pred_glp_sources = [
        ("BetQL", fetch_betql_from_gist),
        ("Pickswise", fetch_pickswise_picks_from_gist),
        ("WiseGuyTeam", fetch_wiseguyteam_from_gist),
    ]
    _pred_glp_keys = [(src_name, sp) for src_name, _ in _pred_glp_sources for sp in _pred_glp_sports]
    _pred_glp_fns = [
        (lambda _fn=fn, _sp=sp: _fn(_sp))
        for src_name, fn in _pred_glp_sources for sp in _pred_glp_sports
    ]
    _pred_glp_results = _fetch_parallel(_pred_glp_fns, show_progress=False)
    _pred_glp_lookup = dict(zip(_pred_glp_keys, _pred_glp_results))

    for _pred_sport in _pred_glp_sports:
        try:
            for g in (_pred_glp_lookup.get(("BetQL", _pred_sport)) or []):
                _comm = g.get("community", [])
                _ml = next((c for c in _comm if c.get("bet_type") == "moneyline"), None)
                if _ml:
                    _tot = _ml.get("home_count", 0) + _ml.get("away_count", 0)
                    if _tot:
                        _lean = g.get("home_team", "") if _ml.get("home_count", 0) > _ml.get("away_count", 0) else g.get("away_team", "")
                        _pct = max(_ml.get("home_count", 0), _ml.get("away_count", 0)) / _tot
                        _pred_gl_items.append({
                            "sport": _pred_sport, "away": g.get("away_team", ""), "home": g.get("home_team", ""),
                            "source": "BetQL", "text": f"Community leans {_lean} ({_pct:.0%} of {_tot})"
                        })
        except Exception:
            pass

        try:
            for g in (_pred_glp_lookup.get(("Pickswise", _pred_sport)) or []):
                if g.get("pick_side"):
                    _pred_gl_items.append({
                        "sport": _pred_sport, "away": g.get("away_team", ""), "home": g.get("home_team", ""),
                        "source": "Pickswise",
                        "text": f"{g.get('pick_side','')} ({g.get('pick_bet','')}) · rating {g.get('pick_rating','?')}"
                    })
        except Exception:
            pass

        try:
            for g in (_pred_glp_lookup.get(("WiseGuyTeam", _pred_sport)) or []):
                if g.get("has_sharp"):
                    _away, _home = g.get("away_team", ""), g.get("home_team", "")
                    _tot_line = (g.get("total") or {}).get("line")
                    _sp_line = (g.get("spread") or {}).get("line")
                    _tot_str = f" {_tot_line}" if _tot_line is not None else ""
                    _sp_str = f" {_sp_line}" if _sp_line is not None else ""
                    _flag_labels = {
                        "ml_side1": f"ML {_away}", "ml_side2": f"ML {_home}",
                        "sp_side1": f"Spread {_away}{_sp_str}", "sp_side2": f"Spread {_home}{_sp_str}",
                        "tot_side1": f"Total Over{_tot_str}", "tot_side2": f"Total Under{_tot_str}",
                    }
                    _flags = ", ".join(_flag_labels.get(f, f) for f in g.get("sharp_flags", []))
                    _pred_gl_items.append({
                        "sport": _pred_sport, "away": _away, "home": _home,
                        "source": "WiseGuyTeam", "text": f"Sharp money: {_flags}"
                    })
        except Exception:
            pass

    try:
        for g in fetch_gamelinepicks_from_gist():
            if not _pred_sport_match(g.get("sport", "")):
                continue
            _glp_conf = g.get("confidence")
            _glp_conf_str = "⭐" * int(_glp_conf) if _glp_conf else ""
            _glp_text = f"{g.get('pick','')} ({g.get('odds','')}) via {g.get('bookmaker','')} · EV {g.get('ev',0):+.1%} {_glp_conf_str}"
            _glp_result = g.get("result")
            if _glp_result and _glp_result not in ("expired",):
                _glp_pu = g.get("profit_units")
                if _glp_pu is not None:
                    _glp_text += f" · {_glp_result.upper()} ({_glp_pu:+.1f}u)"
            _pred_gl_items.append({
                "sport": g.get("sport", ""), "away": g.get("away_team", "") or g.get("game", "").split(" @ ")[0],
                "home": g.get("home_team", "") or (g.get("game", "").split(" @ ")[-1] if " @ " in g.get("game", "") else ""),
                "source": "GameLinePicks", "text": _glp_text
            })
    except Exception:
        pass

    # ── GROUP game-line items by matchup (fuzzy team-name match across
    # sources' differing formats: abbreviations, full names, partials) ──
    _pred_gl_groups = []
    for _item in _pred_gl_items:
        _placed = False
        for _grp in _pred_gl_groups:
            if _pred_teams_match(_item["away"], _grp["away"]) and _pred_teams_match(_item["home"], _grp["home"]):
                _grp["items"].append(_item)
                _placed = True
                break
        if not _placed:
            _pred_gl_groups.append({"away": _item["away"], "home": _item["home"], "sport": _item["sport"], "items": [_item]})

    # Sort by real cross-source agreement (most-confirmed matchups first) --
    # was previously unsorted, displaying in whatever order sources
    # happened to run and append, not prioritized by the actual signal
    # this section is built around.
    _pred_gl_groups.sort(key=lambda g: len(set(it["source"] for it in g["items"])), reverse=True)

    # ══════════════════════════════════════════════════════════════════
    # RENDER — Game Lines: one card per matchup, each source's pick as a
    # row inside, consensus line when 2+ sources agree.
    # ══════════════════════════════════════════════════════════════════
    st.markdown(
        '<div style="display:flex;align-items:center;gap:0.75rem;margin:0.5rem 0 0.8rem;">'
        '<div style="flex:1;height:1px;background:var(--bc-bg2);"></div>'
        '<span style="color:var(--bc-dim);font-size:1.0rem;text-transform:uppercase;letter-spacing:0.08em;">🏟️ Game Lines</span>'
        '<div style="flex:1;height:1px;background:var(--bc-bg2);"></div></div>',
        unsafe_allow_html=True
    )
    _pred_source_domains = {
        "Signal Odds": "signalodds.com", "BetQL": "betql.co",
        "Pickswise": "pickswise.com", "WiseGuyTeam": "wiseguyteam.com",
        "GameLinePicks": "gamelinepicks.com",
    }
    if _pred_gl_groups:
        _pred_gl_per_row = 2
        for _gi in range(0, len(_pred_gl_groups), _pred_gl_per_row):
            _gl_cols = st.columns(_pred_gl_per_row)
            for _gj, _grp in enumerate(_pred_gl_groups[_gi:_gi + _pred_gl_per_row]):
                with _gl_cols[_gj]:
                    _rows_html = "".join(
                        f'<div style="padding:5px 0;border-top:1px solid var(--bc-bg2);font-size:12.5px;color:var(--bc-text);display:flex;align-items:center;gap:6px;">'
                        + (f'<img src="https://www.google.com/s2/favicons?domain={_pred_source_domains[it["source"]]}&sz=32" '
                           f'style="width:14px;height:14px;border-radius:3px;flex-shrink:0;" />'
                           if it["source"] in _pred_source_domains else '')
                        + f'<span><b>{it["source"]}</b>: {it["text"]}</span></div>'
                        for it in _grp["items"]
                    )
                    _n_sources = len(set(it["source"] for it in _grp["items"]))
                    st.markdown(
                        f'<div style="background:var(--bc-bg-card);border:1px solid var(--bc-bg2);border-radius:10px;'
                        f'padding:12px 14px;margin-bottom:12px;">'
                        f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                        f'<span style="font-weight:700;font-size:14.5px;color:var(--bc-text);">{_grp["away"]} @ {_grp["home"]}</span>'
                        f'<span style="color:var(--bc-dim);font-size:11px;">{_n_sources} source{"s" if _n_sources != 1 else ""}</span>'
                        f'</div>{_rows_html}</div>',
                        unsafe_allow_html=True
                    )
    else:
        st.caption("No game-line picks loaded for this sport right now.")

    # ══════════════════════════════════════════════════════════════════
    # COLLECT — player props from every source into one flat list.
    # ══════════════════════════════════════════════════════════════════
    _pred_pp_items = []

    for _pred_sport in ("MLB", "NBA", "NFL"):  # GamblingForecast's real coverage
        if not _pred_sport_match(_pred_sport):
            continue
        try:
            for p in fetch_gamblingforecast_props(_pred_sport):
                # "prop" already includes the line, e.g. "14.5 OUTS" -- no
                # separate line field to add here.
                _pred_pp_items.append({
                    "sport": _pred_sport, "player": p.get("name", ""), "line": "", "prop": p.get("prop", ""),
                    "pick": p.get("overUnder", ""), "source": "GamblingForecast", "note": f"diff {p.get('projDiff','')}",
                    "image": "", "team": "", "position": ""
                })
        except Exception:
            pass

    _pred_bp_sports = [s for s in ("MLB", "NBA", "NFL", "NHL", "WNBA") if _pred_sport_match(s)]
    _pred_bp_fns = [(lambda _s=_s: fetch_bettingpros_props(_s)) for _s in _pred_bp_sports]
    _pred_bp_results = _fetch_parallel(_pred_bp_fns, show_progress=False)
    for _pred_sport, _bp_props_for_sport in zip(_pred_bp_sports, _pred_bp_results):
        try:
            for p in (_bp_props_for_sport or []):
                _proj = p.get("projection", {}) or {}
                if not _proj.get("recommended_side"):
                    continue
                _bp_player = (p.get("participant", {}) or {}).get("player", {}) or {}
                _name = _bp_player.get("short_name") or f"{_bp_player.get('first_name','')} {_bp_player.get('last_name','')}".strip()
                _call = str(_proj.get("recommended_side", "")).upper()
                _stat = p.get("links", {}).get("odds", "").rstrip("/").rsplit("/", 1)[-1].replace("-", " ").title()
                # The actual bet line lives under the over/under side dict
                # matching the recommended call -- was never being pulled
                # in before, which is why every entry showed a pick with
                # no number attached.
                _side_data = p.get(_call.lower(), {}) or {}
                _line = _side_data.get("line", "")
                _pred_pp_items.append({
                    "sport": _pred_sport, "player": _name, "line": _line, "prop": _stat, "pick": _call,
                    "source": "BettingPros", "note": f"proj {_proj.get('value','?')}",
                    "image": _bp_player.get("image", ""), "team": _bp_player.get("team", ""),
                    "position": _bp_player.get("position", "")
                })
        except Exception:
            pass

    _pred_bbp_sports = [s for s in ("mlb", "nba", "wnba", "nfl", "nhl") if _pred_sport_match(s.upper())]
    _pred_bbp_fns = [(lambda _s=_s: fetch_bobbys_bets_picks(_s)) for _s in _pred_bbp_sports]
    _pred_bbp_results = _fetch_parallel(_pred_bbp_fns, show_progress=False)
    for _pred_sport, _bbp_picks_for_sport in zip(_pred_bbp_sports, _pred_bbp_results):
        try:
            for p in (_bbp_picks_for_sport or []):
                _pred_pp_items.append({
                    "sport": _pred_sport.upper(), "player": p.get("player_name", ""),
                    "line": p.get("line", ""), "prop": p.get("stat_category", ""),
                    "pick": p.get("label", ""), "source": "Bobby's Bets", "note": f"grade {p.get('grade','?')}",
                    "image": "", "team": "", "position": ""
                })
        except Exception:
            pass

    _pred_betql2_sports = [s for s in ("MLB", "NBA", "NFL", "NHL") if _pred_sport_match(s)]
    _pred_betql2_fns = [(lambda _s=_s: fetch_betql_from_gist(_s)) for _s in _pred_betql2_sports]
    _pred_betql2_results = _fetch_parallel(_pred_betql2_fns, show_progress=False)
    for _pred_sport, _betql2_games_for_sport in zip(_pred_betql2_sports, _pred_betql2_results):
        try:
            for g in (_betql2_games_for_sport or []):
                for pp in g.get("player_props", []):
                    _direction = "Over" if (pp.get("direction") or 0) > 0 else "Under"
                    _pred_pp_items.append({
                        "sport": _pred_sport, "player": pp.get("player", ""),
                        "line": pp.get("line", ""), "prop": pp.get("prop", ""),
                        "pick": _direction, "source": "BetQL", "note": f"proj {pp.get('projection','?')}",
                        "image": "", "team": "", "position": ""
                    })
        except Exception:
            pass

    # ── GROUP by player -- keep the first real headshot/team/position seen
    # (only BettingPros provides these) so the card has something to show
    # even though most sources don't carry player metadata. ──────────────
    _pred_pp_by_player = {}
    for _it in _pred_pp_items:
        _key = normalize_name(_it["player"])
        if not _key:
            continue
        _grp = _pred_pp_by_player.setdefault(_key, {
            "player": _it["player"], "sport": _it["sport"], "props": [],
            "image": "", "team": "", "position": ""
        })
        _grp["props"].append(_it)
        if _it.get("image") and not _grp["image"]:
            _grp["image"] = _it["image"]
            _grp["team"] = _it.get("team", "")
            _grp["position"] = _it.get("position", "")

    def _pred_pick_line(it):
        """Builds 'UNDER 29.5 Points' -- falls back gracefully when a
        source's prop string already has the number baked in (Gambling-
        Forecast) or a line genuinely isn't available. Appends the
        source's own real signal (projDiff/projection/grade) when
        present -- previously captured into "note" but never displayed."""
        base = f'{it["pick"]} {it["line"]} {it["prop"]}' if it.get("line") not in (None, "") else f'{it["pick"]} {it["prop"]}'
        _note = it.get("note", "")
        return f"{base} ({_note})" if _note else base

    # ══════════════════════════════════════════════════════════════════
    # RENDER — Player Props as cards (BettingPros-app style): headshot
    # circle, team/position, name, the pick's own biggest signal as the
    # large stat line, other sources listed underneath.
    # ══════════════════════════════════════════════════════════════════
    st.markdown(
        '<div style="display:flex;align-items:center;gap:0.75rem;margin:1.2rem 0 0.8rem;">'
        '<div style="flex:1;height:1px;background:var(--bc-bg2);"></div>'
        '<span style="color:var(--bc-dim);font-size:1.0rem;text-transform:uppercase;letter-spacing:0.08em;">🎯 Player Props</span>'
        '<div style="flex:1;height:1px;background:var(--bc-bg2);"></div></div>',
        unsafe_allow_html=True
    )
    _pred_pp_groups = list(_pred_pp_by_player.values())
    # Sort by real cross-source agreement (most-confirmed players first),
    # same fix and same reasoning as the game-line groups above.
    _pred_pp_groups.sort(key=lambda g: len(set(p["source"] for p in g["props"])), reverse=True)
    if _pred_pp_groups:
        _pp_per_row = 3
        for _pi in range(0, len(_pred_pp_groups), _pp_per_row):
            _pp_cols = st.columns(_pp_per_row)
            for _pj, _grp in enumerate(_pred_pp_groups[_pi:_pi + _pp_per_row]):
                with _pp_cols[_pj]:
                    _p0 = _grp["props"][0]
                    _headline = _pred_pick_line(_p0)
                    _sub_sources = _grp["props"][1:4]
                    _sub_html = "".join(
                        f'<div style="font-size:11px;color:var(--bc-dim);margin-top:3px;">'
                        f'{it["source"]}: {_pred_pick_line(it)}</div>'
                        for it in _sub_sources
                    )
                    _more_count = len(_grp["props"]) - 1 - len(_sub_sources)
                    _more_html = (
                        f'<div style="font-size:10.5px;color:var(--bc-dim);margin-top:4px;">+{_more_count} more</div>'
                        if _more_count > 0 else ""
                    )
                    _avatar_html = (
                        f'<img src="{_grp["image"]}" style="width:64px;height:64px;border-radius:50%;'
                        f'object-fit:cover;border:2px solid var(--bc-bg2);" />'
                        if _grp["image"] else
                        f'<div style="width:64px;height:64px;border-radius:50%;background:var(--bc-bg2);'
                        f'display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:700;'
                        f'color:var(--bc-dim);">{"".join(w[0] for w in _grp["player"].split()[:2]).upper()}</div>'
                    )
                    _team_pos = f'{_grp["team"]} · {_grp["position"]}' if _grp["team"] else _grp["sport"]
                    st.markdown(
                        f'<div style="background:var(--bc-bg-card);border:1px solid var(--bc-bg2);border-radius:12px;'
                        f'padding:14px;margin-bottom:14px;text-align:center;">'
                        f'<div style="display:flex;justify-content:center;">{_avatar_html}</div>'
                        f'<div style="font-size:11px;color:var(--bc-dim);margin-top:8px;">{_team_pos}</div>'
                        f'<div style="font-weight:700;font-size:15px;color:var(--bc-text);margin-top:2px;">{_grp["player"]}</div>'
                        f'<div style="font-size:16px;font-weight:800;color:var(--bc-text);margin-top:8px;">{_headline}</div>'
                        f'<div style="font-size:10.5px;color:var(--bc-dim);margin-top:2px;">{_p0["source"]}</div>'
                        f'{_sub_html}{_more_html}'
                        f'</div>',
                        unsafe_allow_html=True
                    )
    else:
        st.caption("No player props loaded for this sport right now.")
