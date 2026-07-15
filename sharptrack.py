"""
sharptrack.py — SharpTrack tab (Polymarket sharp-wallet tracker)
==================================================================
Reads the snapshot pushed every 15 min by scripts/sharptrack_harvester.py
(via .github/workflows/sharptrack_refresh.yml) and renders it as a
BetCouncil tab: a research view of where sharp Polymarket money is
positioned on sports/esports markets right now. This is not a pick
service — it surfaces wallet-quality-scored plays and order-book
sentiment so Abraham can do his own read on whether to follow.

Data flow:
  scripts/sharptrack_harvester.py (GitHub Actions, every 15 min)
    -> Gist: betcouncil_sharptrack_wallets.json, betcouncil_sharptrack_live.json
    -> this module reads both via fetchers._read_gist_file (same cached-Gist
       pattern every other book/source in the app already uses)
    -> render_sharptrack_tab() draws the UI

"My Plays" is a separate, user-owned log (Abraham's own sportsbook/Polymarket
plays, not wallet data) stored the same way as the rest of BetCouncil's
history — via save_to_gist/load_from_gist under SHARPTRACK_GIST_MYPLAYS_KEY —
so he can eyeball how his own calls compare to what the sharp wallets did.
"""

import time
from datetime import datetime, timezone

import streamlit as st

from fetchers import _read_gist_file, save_to_gist, load_from_gist
from styles import TIER_COLORS, badge_css
from config import (
    SHARPTRACK_MIN_WALLET_SCORE, SHARPTRACK_SCORE_TIERS,
    SHARPTRACK_GIST_MYPLAYS_KEY,
)


def _score_tier(score: float) -> str:
    for threshold, label in SHARPTRACK_SCORE_TIERS:
        if score >= threshold:
            return label
    return "PASS"


def _tier_chip(tier: str) -> str:
    c = TIER_COLORS.get(tier, "#8ab4d4")
    return f'<span style="{badge_css(c)}">{tier}</span>'


def _age_label(iso_ts: str) -> str:
    if not iso_ts:
        return "never"
    try:
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        mins = (datetime.now(timezone.utc) - dt).total_seconds() / 60
        if mins < 1:
            return "just now"
        if mins < 60:
            return f"{int(mins)}m ago"
        return f"{mins/60:.1f}h ago"
    except (ValueError, TypeError):
        return "unknown"


def _load_snapshots():
    live = _read_gist_file("betcouncil_sharptrack_live.json", cache_minutes=5) or {}
    wallets = _read_gist_file("betcouncil_sharptrack_wallets.json", cache_minutes=5) or {}
    return live, wallets


def _load_my_plays():
    data = load_from_gist(SHARPTRACK_GIST_MYPLAYS_KEY, [])
    return data if isinstance(data, list) else []


def _save_my_plays(plays):
    save_to_gist(SHARPTRACK_GIST_MYPLAYS_KEY, plays)


def render_sharptrack_tab():
    st.markdown("## 🦈 SharpTrack — Polymarket Sharp Wallet Tracker")
    st.caption(
        "Tracks the highest-quality wallets on Polymarket's SPORTS/ESPORTS leaderboards "
        "and surfaces their live plays, scored 1-100. Research tool, not a pick service — "
        "do your own homework before following a play."
    )

    live, wallet_reg = _load_snapshots()
    plays = live.get("plays", []) or []
    clusters = live.get("clusters", []) or []
    wallets = wallet_reg.get("wallets", []) or []

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Sharp wallets tracked", wallet_reg.get("wallet_count", len(wallets)))
    c2.metric("Live plays (2h window)", len(plays))
    c3.metric("Clusters flagged", len(clusters))
    c4.metric("Last refresh", _age_label(live.get("updated", "")))

    if not plays and not wallets:
        st.info(
            "No SharpTrack data yet. The harvester (`sharptrack_refresh.yml`) runs every "
            "15 minutes via GitHub Actions — if this was just enabled, give it one cycle "
            "to populate the wallet registry and live feed."
        )
        return

    tab_plays, tab_clusters, tab_wallets, tab_mine = st.tabs(
        ["📖 Live Plays", "🔵 Cluster Alerts", "🏆 Wallet Leaderboard", "📝 My Plays"]
    )

    # ── Live Plays ───────────────────────────────────────────────────
    with tab_plays:
        if not plays:
            st.info("No sharp-wallet plays in the current lookback window.")
        else:
            with st.expander("What am I looking at?"):
                st.markdown(
                    "Each card is one trade a tracked sharp wallet made on a Polymarket "
                    "market in the last 2 hours.\n\n"
                    "- **Title** — the market question (e.g. an exact final score, a "
                    "moneyline, a total).\n"
                    "- **Outcome (side)** — which side of that market they bought, and "
                    "whether it was a buy or sell.\n"
                    "- **$ @ price** — dollars spent, and the price paid per $1 share "
                    "(price ≈ the market's implied probability, so 0.98 means the market "
                    "already sees it as ~98% likely).\n"
                    "- **wallet (score)** — which sharp wallet, and its 1-100 quality score.\n"
                    "- **sentiment** — the order book's lean at that moment.\n\n"
                    "⚠️ **A price near 0.95+ or 0.05- is a near-certainty, not a sharp read.** "
                    "Markets like 'exact final score' have dozens of possible outcomes, so "
                    "betting against any one specific score is normally a safe, low-edge "
                    "trade — closer to hedging or market-making than a directional signal. "
                    "Those are marked below. The plays worth paying attention to are the "
                    "ones without that flag, especially anything in Cluster Alerts."
                )

            sports_seen = sorted({p.get("sport", "") for p in plays if p.get("sport")})
            sel_sport = st.selectbox("Filter by sport", ["All"] + sports_seen, key="st_sport_filter")
            filtered = [p for p in plays if sel_sport == "All" or p.get("sport") == sel_sport]

            for p in filtered[:40]:
                tier = _score_tier(p.get("play_score", 0))
                cluster_flag = "🔵 " if p.get("cluster_wallet_count", 1) >= 2 else ""
                sentiment = (p.get("market_sentiment") or {}).get("label", "")
                price = p.get("price", 0) or 0
                try:
                    price_f = float(price)
                except (TypeError, ValueError):
                    price_f = 0.5
                near_certain = price_f >= 0.95 or price_f <= 0.05
                hedge_note = (
                    ' <span style="color:#e0a030;font-size:11px;">⚠️ near-certain price — '
                    'likely hedge, not a directional read</span>' if near_certain else ''
                )
                with st.container():
                    st.markdown(
                        f'<div style="background:#0d1b2e;border:1px solid #1a3a5c;border-radius:8px;'
                        f'padding:10px 14px;margin-bottom:6px;">'
                        f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                        f'<span style="color:#fff;font-weight:600;">{cluster_flag}{p.get("title","")[:90]}</span>'
                        f'{_tier_chip(tier)}</div>'
                        f'<div style="color:#8ab4d4;font-size:12px;margin-top:4px;">'
                        f'{p.get("sport","")} · {p.get("outcome","")} ({p.get("side","")}) · '
                        f'${p.get("usd_value",0):,.0f} @ {price} · '
                        f'wallet <b>{p.get("userName","")}</b> (score {p.get("wallet_score",0)}) · '
                        f'{sentiment}{hedge_note}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

    # ── Cluster Alerts ───────────────────────────────────────────────
    with tab_clusters:
        if not clusters:
            st.info("No multi-wallet consensus plays flagged in the current window.")
        else:
            st.caption("2+ distinct sharp wallets took the same side of the same market within the lookback window.")
            for c in clusters[:25]:
                st.markdown(
                    f'<div style="background:#0d1b2e;border:1px solid #1e90ff;border-radius:8px;'
                    f'padding:10px 14px;margin-bottom:6px;">'
                    f'<span style="color:#fff;font-weight:700;">🔵 {c.get("wallet_count")} sharp wallets → '
                    f'{c.get("outcome","")}</span><br>'
                    f'<span style="color:#8ab4d4;font-size:12px;">{c.get("title","")[:100]}</span><br>'
                    f'<span style="color:#8ab4d4;font-size:12px;">{c.get("sport","")} · '
                    f'avg wallet score {c.get("avg_wallet_score")} · '
                    f'${c.get("total_usd",0):,.0f} combined · {c.get("trade_count")} trades</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

def _format_periods_seen(periods_seen: list) -> str:
    """Turns raw entries like ['SPORTS:WEEK','SPORTS:MONTH','ESPORTS:ALL'] into
    a readable 'Category: Sports (This week, This month) · Esports (All-time)'
    string. This is per-wallet leaderboard metadata (which Polymarket category
    that specific wallet ranked in) — not the scope of SharpTrack itself,
    which tracks all sports."""
    period_labels = {"WEEK": "this week", "MONTH": "this month", "ALL": "all-time"}
    by_category = {}
    for entry in periods_seen or []:
        if ":" not in entry:
            continue
        cat, period = entry.split(":", 1)
        by_category.setdefault(cat.title(), []).append(period_labels.get(period, period.lower()))
    if not by_category:
        return ""
    parts = [f"{cat} ({', '.join(periods)})" for cat, periods in by_category.items()]
    return "Category: " + " · ".join(parts)
    with tab_wallets:
        if not wallets:
            st.info("Wallet registry not populated yet.")
        else:
            for w in wallets[:100]:
                score = w.get("score") or 0
                tier = _score_tier(score)
                addr = w.get("address") or ""
                wallet_label = w.get("userName") or (addr[:10] if addr else "unknown")
                verified = " ✓" if w.get("verifiedBadge") else ""
                periods = _format_periods_seen(w.get("periods_seen", []))
                st.markdown(
                    f'<div style="background:#0d1b2e;border:1px solid #1a3a5c;border-radius:8px;'
                    f'padding:10px 14px;margin-bottom:6px;">'
                    f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                    f'<span style="color:#fff;font-weight:600;">{wallet_label}{verified}</span>'
                    f'{_tier_chip(tier)}</div>'
                    f'<div style="color:#8ab4d4;font-size:12px;margin-top:4px;">'
                    f'Score {score} · Best PnL ${w.get("best_pnl",0):,.0f} · '
                    f'Best Vol ${w.get("best_vol",0):,.0f}'
                    + (f' · {periods}' if periods else '') + '</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            st.caption(f"Wallets below score {SHARPTRACK_MIN_WALLET_SCORE} are dropped from tracking entirely.")

    # ── My Plays ─────────────────────────────────────────────────────
    with tab_mine:
        st.caption("Your own logged plays — for comparing your calls against what sharp wallets were doing at the time.")
        my_plays = _load_my_plays()

        with st.form("sharptrack_log_play", clear_on_submit=True):
            fc1, fc2, fc3 = st.columns(3)
            sport = fc1.text_input("Sport / market")
            side = fc2.text_input("Side / outcome")
            stake = fc3.number_input("Stake ($)", min_value=0.0, step=5.0)
            note = st.text_input("Note (optional)")
            submitted = st.form_submit_button("Log play")
            if submitted and sport and side:
                my_plays.append({
                    "sport": sport,
                    "side": side,
                    "stake": stake,
                    "note": note,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "result": "pending",
                })
                _save_my_plays(my_plays)
                st.success("Logged.")
                st.rerun()

        if my_plays:
            for p in reversed(my_plays[-50:]):
                when = (p.get("timestamp") or "")[:16].replace("T", " ")
                result = p.get("result", "pending")
                result_color = {"win": "#2ecc71", "loss": "#e74c3c"}.get(result, "#8ab4d4")
                st.markdown(
                    f'<div style="background:#0d1b2e;border:1px solid #1a3a5c;border-radius:8px;'
                    f'padding:10px 14px;margin-bottom:6px;">'
                    f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                    f'<span style="color:#fff;font-weight:600;">{p.get("sport","")} — {p.get("side","")}</span>'
                    f'<span style="color:{result_color};font-size:12px;font-weight:600;">{result}</span></div>'
                    f'<div style="color:#8ab4d4;font-size:12px;margin-top:4px;">'
                    f'{when} · ${p.get("stake",0):,.2f}'
                    + (f' · {p.get("note","")}' if p.get("note") else '')
                    + '</div></div>',
                    unsafe_allow_html=True,
                )
        else:
            st.info("No plays logged yet.")
