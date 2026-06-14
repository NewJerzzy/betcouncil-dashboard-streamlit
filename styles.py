"""BetCouncil Styles — centralized CSS variables and color constants."""

# === COLOR PALETTE ===
COLORS = {
    "bg_dark": "#0a0e14",
    "bg_card": "#0d1117",
    "bg_panel": "#161b22",
    "border": "#30363d",
    "text_primary": "#e6edf3",
    "text_secondary": "#8b949e",
    "text_muted": "#6e7681",
    "accent_green": "#00ff88",
    "accent_blue": "#58a6ff",
    "accent_red": "#ff4444",
    "accent_gold": "#ffd700",
    "accent_orange": "#ff8c00",
    "tier_sovereign": "#ffd700",
    "tier_elite": "#00ff88",
    "tier_approved": "#58a6ff",
    "tier_lean": "#ff8c00",
    "tier_pass": "#ff4444",
}

# === TIER COLORS ===
TIER_COLORS = {
    "SOVEREIGN": "#ffd700",
    "ELITE": "#00ff88",
    "APPROVED": "#58a6ff",
    "LEAN": "#ff8c00",
    "PASS": "#ff4444",
}

# === CSS TEMPLATES ===
def card_css(border_color=None):
    bc = border_color or COLORS["border"]
    return f"background:{COLORS['bg_card']};border:1px solid {bc};border-radius:8px;padding:1rem;"

def badge_css(color, bg_opacity="22"):
    return f"background:{color}{bg_opacity};color:{color};padding:2px 8px;border-radius:4px;font-weight:600;"

def metric_card(label, value, color=None):
    c = color or COLORS["accent_green"]
    return f"""<div style="{card_css()}">
        <div style="color:{COLORS['text_muted']};font-size:0.75rem;">{label}</div>
        <div style="color:{c};font-size:1.5rem;font-weight:700;">{value}</div>
    </div>"""
