"""Small Streamlit view for hit-focused ranking; no stake/EV side effects."""
import streamlit as st

from demon_hit_analysis import rank_assessments
from demon_hit_sources import assess_player


def render_hit_rows(rows):
    rows = rank_assessments(rows)
    st.caption(
        "Ranked by evidence quality, then the lower end of a 90% historical hit-rate interval. "
        "Estimates use the exact submitted line, not payout, an edge tier, or a different board line. "
        "Pushes are not hits. Up to 30 dated games from the past year are used."
    )
    records = []
    for row in rows:
        assessment = row["hit_analysis"]
        available = assessment.get("prob") is not None
        records.append({
            "Player": row["player"], "Sport": row["sport"], "Stat": row["stat"],
            "More than": row["line"], "Assessment": assessment["grade"],
            "Historical estimate": f'{assessment["prob"]:.0%}' if available else "—",
            "90% history interval": (
                f'{assessment["lower"]:.0%}–{assessment["upper"]:.0%}' if available else "—"
            ),
            "Hits / games": f'{assessment.get("hits", 0)}/{assessment["n"]}',
            "Pushes": assessment.get("pushes", 0),
            "Last 5": f'{assessment["last5"]:.0%}' if available else "—",
            "Last 10": f'{assessment["last10"]:.0%}' if available else "—",
            "Latest game": assessment.get("latest", "—"),
            "Warnings": " ".join(assessment["warnings"]) or "No historical-data flags.",
        })
    st.dataframe(records, hide_index=True, use_container_width=True)
    st.caption(
        "STRONGER HISTORY requires ≥20 games and a historical lower bound ≥60%; "
        "SUPPORTED requires ≥20 and ≥50%, with no data-quality flags. These are selection rules, "
        "not validated confidence tiers. PROVISIONAL is not a recommendation. "
        "The estimate is a smoothed historical rate, not a calibrated next-game forecast. "
        "Today's injuries, opponent, lineup and role still need checking. "
        "Historical intervals do not measure all future uncertainty."
    )
    st.info(
        "Calibration: unvalidated for this hit-focused method. Existing edge-tier results are "
        "not evidence that these exact-line estimates are calibrated. No learned correction "
        "or automatic wager is applied."
    )
    return rows


def render_loaded_demons(core, board):
    with st.expander("Demon Analyzer · prioritize hit likelihood", expanded=False):
        st.write(
            "Compare the loaded demon props on evidence for clearing their exact More line. "
            "This view does not rank by payout or change the main board's financial model."
        )
        demons = [prop for prop in board
                  if str(prop.get("OddsType", "")).lower() == "demon"]
        if not demons:
            st.caption("No explicitly tagged demon props are loaded. Paste a board below to grade More lines.")
            return
        fingerprint = tuple(sorted(
            (str(p.get("Sport", "")), str(p.get("Player", "")),
             str(p.get("Prop", "")), str(p.get("Line", ""))) for p in demons
        ))
        if st.button("Grade loaded demon lines", key="grade_loaded_demon_hits"):
            rows = []
            with st.spinner("Checking exact lines against dated game logs…"):
                for prop in demons:
                    row = {
                        "player": prop["Player"], "stat": prop["Prop"], "line": prop["Line"],
                        "sport": prop.get("Sport", ""),
                    }
                    row["hit_analysis"] = assess_player(
                        core, row["player"], row["stat"], row["line"], row["sport"]
                    )
                    rows.append(row)
            st.session_state["_demon_hit_results"] = (fingerprint, rows)
        saved = st.session_state.get("_demon_hit_results")
        if saved and saved[0] == fingerprint:
            render_hit_rows(saved[1])
        elif saved:
            st.caption("The loaded lines changed. Grade again rather than reusing old-line estimates.")
