"""BetCouncil Styles — bet105-inspired dark blue aesthetic."""

# === COLOR PALETTE (bet105-inspired) ===
COLORS = {
    "bg_dark":       "#000000",    # pure black bg
    "bg_card":       "#0d1b2e",    # deep navy card
    "bg_panel":      "#071020",    # sidebar panel
    "bg_section":    "#0a1628",    # section headers
    "border":        "#1a3a5c",    # blue-tinted border
    "text_primary":  "#ffffff",    # pure white
    "text_secondary":"#8ab4d4",    # blue-tinted muted
    "text_muted":    "#4a6a8a",
    "accent_blue":   "#1e90ff",    # electric blue — primary
    "accent_blue_bright": "#4db8ff",
    "accent_blue_dark":   "#0a5fa8",
    "accent_green":  "#22c55e",
    "accent_red":    "#e04040",
    "accent_gold":   "#f5c518",
    "accent_orange": "#ff8c00",
    "tier_sovereign":"#f5c518",
    "tier_elite":    "#1e90ff",    # electric blue for ELITE
    "tier_approved": "#22c55e",
    "tier_lean":     "#ff8c00",
    "tier_pass":     "#e04040",
}

# === TIER COLORS ===
TIER_COLORS = {
    "SOVEREIGN": "#f5c518",
    "ELITE":     "#1e90ff",
    "APPROVED":  "#22c55e",
    "LEAN":      "#ff8c00",
    "PASS":      "#e04040",
}

# === CSS TEMPLATES ===
def card_css(border_color=None, glow=False):
    bc = border_color or COLORS["border"]
    glow_str = f"; box-shadow: 0 0 12px rgba(30,144,255,0.2)" if glow else ""
    return (f"background:{COLORS['bg_card']};border:1px solid {bc};"
            f"border-radius:8px;padding:1rem{glow_str};")

def section_header_html(title: str, count: int = None) -> str:
    count_badge = f'<span style="background:#1e90ff;color:#fff;border-radius:50%;padding:2px 8px;font-size:12px;font-weight:700;float:right">{count}</span>' if count is not None else ""
    return (f'<div style="background:linear-gradient(90deg,#0a5fa8,#0a1628);'
'border-left:4px solid #1e90ff;border-radius:6px 6px 0 0;'
'padding:10px 16px;color:#fff;font-weight:700;font-size:14px;'
'letter-spacing:0.5px;text-transform:uppercase;margin-bottom:0">'
 f'{count_badge}{title}</div>')

def badge_css(color, bg_opacity="22"):
    return (f"background:{color}{bg_opacity};color:{color};"
            f"padding:2px 8px;border-radius:4px;font-weight:600;")

def metric_card(label, value, color=None):
    c = color or COLORS["accent_blue"]
    return f'''<div style="{card_css(border_color=COLORS['border'], glow=True)}">
        <div style="color:{COLORS['text_muted']};font-size:0.75rem;text-transform:uppercase;letter-spacing:0.5px">{label}</div>
        <div style="color:{c};font-size:1.5rem;font-weight:700">{value}</div>
    </div>'''

def live_badge_html() -> str:
    return '<span class="bc-live-badge">🔴 LIVE</span>'

def tier_badge_html(tier: str) -> str:
    colors = TIER_COLORS
    c = colors.get(tier, "#ffffff")
    return f'<span style="{badge_css(c)}">{tier}</span>'


# === GLOBAL DARK-THEME POLISH ===
def global_css() -> str:
    """Additive dark-theme polish: skeleton-loader shimmer, empty-state
    styling, card hover lift, button/scrollbar/focus polish. Deliberately
    does NOT redeclare :root -- app.py already defines --bc-blue/--bc-muted/
    --bc-dim/--bc-border/etc. and hundreds of existing elements depend on
    those exact values; this only adds new rules on top, using the same
    variable names."""
    return """
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
    /* Font upgrade -- Inter app-wide instead of the generic browser sans
       serif fallback. Same clean geometric sans used by most of the
       platforms referenced in the UI redesign notes (FanDuel, Unabated,
       BetQL). Purely typographic -- doesn't touch the existing --bc-*
       color palette or any layout. */
    html, body, [class*="css"], .stApp {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    }
    /* Card hover lift. .bc-card is defined (here and in app.py's own CSS
       block) but has zero real usage -- almost every card in this app is
       built via inline styles in an f-string, not a class attribute. The
       attribute selector below catches that existing pattern directly
       (virtually every card container already uses border-radius:8px
       inline) so the hover effect actually applies across the app without
       needing to touch hundreds of scattered markdown call sites. */
    /* Tab navigation -- hover + active-state feedback. Confirmed missing
       entirely (no tab-specific CSS existed anywhere) before this. */
    [data-testid="stTabs"] button[data-baseweb="tab"] {
        transition: color 0.15s ease, border-color 0.15s ease;
        border-radius: 6px 6px 0 0;
    }
    [data-testid="stTabs"] button[data-baseweb="tab"]:hover {
        color: var(--bc-blue, #1e90ff) !important;
        background: rgba(30,144,255,0.06);
    }
    [data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"] {
        border-bottom: 2px solid var(--bc-blue, #1e90ff) !important;
    }
    .bc-card {
        transition: border-color 0.15s ease;
    }
    /* .pulse-stale -- applied to the sidebar Edge Freshness metric-box
       when get_edge_staleness() returns red/orange (stale, very stale, or
       never loaded), so a genuinely untrustworthy board gets an urgent
       visual cue instead of sitting there as static text easy to miss. */
    @keyframes pulse-stale-glow {
        0%, 100% { box-shadow: 0 0 0 0 rgba(224,64,64,0.35); }
        50%      { box-shadow: 0 0 0 6px rgba(224,64,64,0); }
    }
    .pulse-stale {
        animation: pulse-stale-glow 2s ease-in-out infinite;
        border-color: rgba(224,64,64,0.5) !important;
    }
    .bc-card:hover {
        border-color: var(--bc-blue) !important;
    }
    div[style*="border-radius:8px"] {
        transition: border-color 0.15s ease, box-shadow 0.15s ease;
    }
    div[style*="border-radius:8px"]:hover {
        border-color: var(--bc-blue) !important;
        box-shadow: 0 0 10px rgba(30,144,255,0.15);
    }
    /* Skeleton loader shimmer */
    @keyframes bc-shimmer {
        0% { background-position: -400px 0; }
        100% { background-position: 400px 0; }
    }
    .bc-skeleton {
        background: linear-gradient(90deg, var(--bc-bg-card) 25%, #14263d 37%, var(--bc-bg-card) 63%);
        background-size: 800px 100%;
        animation: bc-shimmer 1.4s ease infinite;
        border-radius: 6px;
        border: 1px solid var(--bc-border);
    }
    /* Empty state */
    .bc-empty-state {
        text-align: center;
        padding: 2.5rem 1rem;
        color: var(--bc-dim);
    }
    .bc-empty-state .bc-empty-icon { font-size: 2.2rem; margin-bottom: 0.5rem; opacity: 0.7; }
    .bc-empty-state .bc-empty-title { color: var(--bc-muted); font-size: 1rem; font-weight: 600; margin-bottom: 0.25rem; }
    .bc-empty-state .bc-empty-subtitle { font-size: 0.85rem; }
    /* Button polish -- smoother state transitions on Streamlit's native buttons */
    .stButton > button {
        transition: transform 0.1s ease, box-shadow 0.15s ease, border-color 0.15s ease;
    }
    .stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 2px 8px rgba(30,144,255,0.25);
    }
    .stButton > button:active {
        transform: translateY(0);
    }
    /* Scrollbar polish -- thin, dark-theme-matched instead of the default */
    ::-webkit-scrollbar { width: 8px; height: 8px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: var(--bc-border); border-radius: 4px; }
    ::-webkit-scrollbar-thumb:hover { background: var(--bc-blue); }
    /* Focus states -- visible, on-brand outline instead of the browser default */
    input:focus, textarea:focus, select:focus, .stTextInput input:focus {
        outline: 1px solid var(--bc-blue) !important;
        box-shadow: 0 0 0 2px rgba(30,144,255,0.15) !important;
    }
    /* .command-card / .command-value / .command-label -- used by the Summary
       tab's hero metrics bar (Props Loaded, Sovereign, Avg Edge, Win Rate,
       CLV, Bankroll Mult) but never actually defined anywhere in the
       codebase until now -- those cards had been rendering as unstyled
       plain divs the entire time, which is the real, concrete reason the
       most important row on the page never looked like it changed. */
    .command-card {
        background: linear-gradient(160deg, var(--bc-bg-card) 0%, #0a1622 100%);
        border: 1px solid var(--bc-border);
        border-radius: 10px;
        padding: 14px 16px 12px;
        text-align: center;
        box-shadow: 0 2px 6px rgba(0,0,0,0.3);
        transition: transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease;
    }
    .command-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 16px rgba(0,0,0,0.4), 0 0 0 1px rgba(30,144,255,0.2);
    }
    .command-value {
        font-size: 1.65rem;
        font-weight: 800;
        color: var(--bc-text);
        line-height: 1.15;
        letter-spacing: -0.02em;
    }
    .command-label {
        font-size: 0.7rem;
        font-weight: 600;
        color: var(--bc-muted);
        text-transform: uppercase;
        letter-spacing: 0.06em;
        margin-top: 4px;
    }
    /* .bc-section-header -- tab-level section title banner (e.g. "EV
       Optimizer -- MLB"). Used but never defined, same gap as .command-card. */
    .bc-section-header {
        background: linear-gradient(90deg, #0a5fa8, #0a1628);
        border-left: 4px solid var(--bc-blue);
        border-radius: 6px 6px 0 0;
        padding: 10px 16px;
        color: #ffffff;
        font-weight: 700;
        font-size: 1.05rem;
        letter-spacing: 0.02em;
        margin-bottom: 12px;
    }
    /* .odds-mono -- numeric odds/line/edge values. Tabular figures so
       digits align column-to-column instead of jittering width by value. */
    .odds-mono {
        font-family: "SF Mono", "Roboto Mono", Consolas, monospace;
        font-variant-numeric: tabular-nums;
    }
    /* .line-up/.line-down/.line-flat -- line movement direction arrows. */
    .line-up   { color: var(--bc-green, #22c55e); font-weight: 700; }
    .line-down { color: var(--bc-red, #e04040);   font-weight: 700; }
    .line-flat { color: var(--bc-dim);            font-weight: 700; }
    /* .bc-summary-bar / .bc-summary-pill -- Full Board's sticky tier-count
       bar (Sovereign/Elite/Approved/total action). Same gap as above --
       used, never defined, rendering as unstyled inline text this whole time. */
    .bc-summary-bar {
        display: flex;
        align-items: center;
        gap: 10px;
        background: var(--bc-bg-card);
        border: 1px solid var(--bc-border);
        border-radius: 8px;
        padding: 8px 14px;
        margin-bottom: 10px;
        flex-wrap: wrap;
    }
    .bc-summary-pill {
        font-size: 0.8rem;
        font-weight: 700;
        padding: 4px 10px;
        border-radius: 5px;
        white-space: nowrap;
    }
    .bc-sov-pill    { background: rgba(245,197,24,0.15); color: #f5c518; }
    .bc-elite-pill  { background: rgba(30,144,255,0.15); color: #4db8ff; }
    .bc-appr-pill   { background: rgba(34,197,94,0.15);  color: #22c55e; }
    .bc-action-pill { background: rgba(30,144,255,0.1);  color: var(--bc-text); }
    /* Full Board's filter bar (st.container(key="ev_sticky_filters")) --
       stays visible while scrolling the board below it, so filters/sort
       don't require scrolling back up to adjust. Streamlit 1.3+ generates
       a real .st-key-<key> class on keyed containers -- this targets that
       directly rather than a fragile internal DOM selector. */
    .st-key-ev_sticky_filters {
        position: sticky;
        top: 0;
        z-index: 999;
        background: var(--bc-bg);
        padding: 8px 0 4px;
        border-bottom: 1px solid var(--bc-border);
    }
    /* Header accent -- was a plain 1px gray border, replaced with a
       gradient underline for a real brand identity line instead of
       blending into the rest of the page. */
    .bc-header {
        border-bottom: none !important;
        position: relative;
    }
    .bc-header::after {
        content: "";
        position: absolute;
        left: 0; right: 0; bottom: -1px;
        height: 2px;
        background: linear-gradient(90deg, var(--bc-blue, #1e90ff), #4dd8c4, transparent);
    }
    /* Active tab glow -- adds to the border-bottom already set earlier */
    [data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"] {
        box-shadow: 0 2px 8px rgba(30,144,255,0.25);
    }
    /* Bankroll pulse-on-change -- applied via a conditional class (see
       app_core.py) only on the render where the value actually differs
       from the prior one, not a constant/looping animation. */
    @keyframes bankroll-pulse {
        0%   { transform: scale(1); }
        30%  { transform: scale(1.06); }
        100% { transform: scale(1); }
    }
    .bankroll-pulse {
        animation: bankroll-pulse 0.5s ease-out;
        display: inline-block;
    }
    /* Edge heatmap legend */
    .heatmap-legend {
        display: flex;
        align-items: center;
        gap: 6px;
        font-size: 0.72rem;
        color: var(--bc-dim);
        margin: 4px 0 8px;
    }
    .heatmap-legend-swatch {
        display: inline-block;
        width: 40px;
        height: 8px;
        border-radius: 3px;
        background: linear-gradient(90deg, rgba(34,197,94,0.05), rgba(34,197,94,0.4));
    }
    </style>"""


def skeleton_rows_html(n: int = 3, height_px: int = 54) -> str:
    """n shimmering placeholder rows, same shape as a .bc-card row, shown
    while data is loading instead of a bare spinner."""
    rows = "".join(
        f'<div class="bc-skeleton" style="height:{height_px}px;margin-bottom:6px;"></div>'
        for _ in range(n)
    )
    return rows


def empty_state_html(icon: str, title: str, subtitle: str = "") -> str:
    sub = f'<div class="bc-empty-subtitle">{subtitle}</div>' if subtitle else ""
    return (f'<div class="bc-empty-state">'
            f'<div class="bc-empty-icon">{icon}</div>'
            f'<div class="bc-empty-title">{title}</div>'
            f'{sub}</div>')


def line_movement_html(opening, current, higher_is_worse_for_bettor=True) -> str:
    """Small inline movement indicator built from real opening-vs-current
    line data (BetCouncil captures opening lines once/day already) --
    not a fabricated multi-point sparkline the data can't actually support.
    Returns '' if either value is missing (no fake movement shown)."""
    try:
        opening_f = float(opening)
        current_f = float(current)
    except (TypeError, ValueError):
        return ""
    delta = round(current_f - opening_f, 1)
    if delta == 0:
        return '<span style="color:var(--bc-muted);font-size:11px;">→ unmoved</span>'
    moved_against = (delta > 0) == higher_is_worse_for_bettor
    color = "#e04040" if moved_against else "#22c55e"
    arrow = "↑" if delta > 0 else "↓"
    return (f'<span style="color:{color};font-size:11px;font-weight:600;" '
            f'title="Opened {opening_f}, now {current_f}">{arrow} {abs(delta)}</span>')

