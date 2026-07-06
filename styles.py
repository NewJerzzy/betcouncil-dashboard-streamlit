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
