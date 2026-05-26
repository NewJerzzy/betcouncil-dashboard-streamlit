"""
BetCouncil pre-push validation script
Run: python3 check_app.py
Catches the most common issues before deployment
"""
import ast
import re
import sys

with open('app.py', 'r') as f:
    code = f.read()
    lines = code.split('\n')

errors = []
warnings = []

# ─── 1. SYNTAX CHECK ───────────────────────────────────────
try:
    tree = ast.parse(code)
    print("✅ Syntax OK")
except SyntaxError as e:
    errors.append(f"SYNTAX ERROR line {e.lineno}: {e.msg}")

# ─── 2. FUNCTION ORDER CHECK ───────────────────────────────
# Any function called inside load_sport_data must be defined before it
critical_fns = [
    "fetch_dk_salaries", "fetch_dk_nba_draftgroup_id",
    "apply_dk_salary_signal", "fetch_pinnacle_lines",
    "pinnacle_fair_value", "get_pinnacle_edge",
    "fetch_player_id_bdl", "fetch_player_game_logs",
    "compute_h2h_hit_rate", "compute_home_away_splits",
    "fetch_parlayapi_props", "fetch_underdog_props",
    "scrape_prizepicks", "normalize_name",
]
load_line = next((i for i, l in enumerate(lines) if l.startswith("def load_sport_data(")), None)
sidebar_line = next((i for i, l in enumerate(lines) if l.startswith("with st.sidebar:")), None)
tabs_line = next((i for i, l in enumerate(lines) if l.startswith("tabs = st.tabs(")), None)

if load_line:
    print(f"✅ load_sport_data at line {load_line+1}")
    for fn in critical_fns:
        fn_line = next((i for i, l in enumerate(lines) if l.startswith(f"def {fn}(")), None)
        if fn_line and fn_line > load_line:
            errors.append(f"FUNCTION ORDER: {fn} (line {fn_line+1}) defined AFTER load_sport_data (line {load_line+1})")

# ─── 3. CODE BETWEEN SIDEBAR AND TABS ──────────────────────
if sidebar_line and tabs_line:
    between = lines[sidebar_line:tabs_line]
    for i, l in enumerate(between):
        if l.startswith("def "):
            errors.append(f"FUNCTION IN SIDEBAR CONTEXT: '{l.strip()}' at line {sidebar_line+i+1} — between sidebar and tabs")
    print(f"✅ Sidebar at line {sidebar_line+1}, tabs at line {tabs_line+1}")

# ─── 4. ST.CAPTION/INFO/SUCCESS IN DATA FUNCTIONS ──────────
data_fns = ["def fetch_dk_salaries", "def fetch_pinnacle_lines",
            "def fetch_underdog_props", "def scrape_prizepicks",
            "def fetch_parlayapi_props", "def load_sport_data"]
for fn_sig in data_fns:
    fn_start = next((i for i, l in enumerate(lines) if l.startswith(fn_sig)), None)
    if fn_start is None:
        continue
    # Find end of function (next def at same indent level)
    fn_end = next((i for i in range(fn_start+1, len(lines))
                   if lines[i].startswith("def ") or lines[i].startswith("class ")), len(lines))
    fn_body = lines[fn_start:fn_end]
    for i, l in enumerate(fn_body):
        if re.search(r'st\.(caption|info|success|warning|error)\(', l):
            warnings.append(f"ST.UI IN DATA FN: {fn_sig.replace('def ','')} line {fn_start+i+1}: {l.strip()[:60]}")

# ─── 5. TABS INDEX CHECK ───────────────────────────────────
tab_defs = re.findall(r'tabs = st\.tabs\(\[([^\]]+)\]', code)
if tab_defs:
    tab_count = len(tab_defs[0].split(','))
    used_indices = sorted(set(int(m) for m in re.findall(r'with tabs\[(\d+)\]', code)))
    expected = list(range(tab_count))
    if used_indices != expected:
        errors.append(f"TAB INDEX MISMATCH: defined {tab_count} tabs, used indices {used_indices}")
    else:
        print(f"✅ Tab indices OK ({tab_count} tabs, indices 0-{tab_count-1})")

# ─── 6. SESSION STATE KEY CONSISTENCY ─────────────────────
ss_writes = set(re.findall(r'st\.session_state\["([^"]+)"\]\s*=', code))
ss_reads = set(re.findall(r'st\.session_state\.get\("([^"]+)"', code))
ss_reads2 = set(re.findall(r'st\.session_state\["([^"]+)"\](?!\s*=)', code))
all_reads = ss_reads | ss_reads2
unset_reads = all_reads - ss_writes - {"board_data","games","history","locks","last_sport","last_scan_time","board_ready","errors","n_skipped_def","n_skipped_edge","bankroll","day_start_br"}
# Only flag ones used in tabs[0]
tab0_start = code.find("with tabs[0]:")
tab0_end = code.find("# ----- TAB 1:")
tab0_code = code[tab0_start:tab0_end] if tab0_start > 0 else ""
for key in unset_reads:
    if key in tab0_code and key not in ("gem_brief","analyzer_picks","analyzer_results","pl_logs","pl_name_display"):
        warnings.append(f"POSSIBLY UNSET KEY in tabs[0]: st.session_state['{key}']")


# ─── 7. F-STRING SAFETY IN TABS[0] ────────────────────────
tab0_start = code.find("with tabs[0]:")
tab0_end = code.find("# ----- TAB 1: FULL BOARD -----")
if tab0_start > 0 and tab0_end > 0:
    tab0 = code[tab0_start:tab0_end]
    # Check for embedded conditionals with quotes in f-strings
    embedded = re.findall(r'{["\'].+?["\'] if .+? else ["\'].+?["\']}', tab0)
    for e in embedded:
        errors.append(f"EMBEDDED CONDITIONAL IN F-STRING (will break HTML): {e[:60]}")
    # Check for empty format specs
    empty_fmt = re.findall(r'\{[^}]+:\}', tab0)
    for e in empty_fmt:
        errors.append(f"EMPTY FORMAT SPEC (TypeError): {e[:60]}")
    if not embedded and not empty_fmt:
        print("✅ No f-string issues in tabs[0]")
# ─── REPORT ────────────────────────────────────────────────
print()
if errors:
    print(f"❌ {len(errors)} ERRORS:")
    for e in errors:
        print(f"   {e}")
else:
    print("✅ No blocking errors found")

if warnings:
    print(f"\n⚠️  {len(warnings)} WARNINGS:")
    for w in warnings[:10]:
        print(f"   {w}")
else:
    print("✅ No warnings")

print(f"\nLines: {len(lines)}")
sys.exit(1 if errors else 0)
