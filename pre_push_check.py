"""
BetCouncil Pre-Push Verification Script
Run this before every push. Catches runtime errors that ast.parse misses.
Usage: python3 /tmp/pre_push_check.py
"""
import re, ast, sys

with open('/tmp/app.py', 'r') as f:
    source = f.read()

errors   = []
warnings = []
passed   = []

# ══════════════════════════════════════════════════════
# CHECK 1: Syntax
# ══════════════════════════════════════════════════════
try:
    ast.parse(source)
    passed.append("Syntax OK")
except SyntaxError as e:
    errors.append(f"SYNTAX ERROR at line {e.lineno}: {e.msg}")

# ══════════════════════════════════════════════════════
# CHECK 2: Return dict keys vs UI reads
# ══════════════════════════════════════════════════════
RESULT_VARS = {
    '_bi':        'compute_bankroll_multiplier',
    '_drift':     'compute_model_drift',
    '_regime':    'detect_season_regime',
    '_weekly':    'generate_weekly_model_report',
    '_portfolio': 'compute_portfolio_exposure',
}

for var, fn_name in RESULT_VARS.items():
    reads    = set(re.findall(rf"{re.escape(var)}\[[\'\"](\w+)[\'\"]\]", source))
    fn_start = source.find(f"def {fn_name}(")
    if fn_start < 0:
        errors.append(f"MISSING FUNCTION: {fn_name} not defined")
        continue
    fn_end   = source.find("\ndef ", fn_start + 10)
    fn_body  = source[fn_start:fn_end]
    returned = set(re.findall(r'[\'\"]([\w]+)[\'\"]:', fn_body))
    missing  = reads - returned
    if missing:
        errors.append(f"KEYERROR RISK: {fn_name} missing keys {sorted(missing)}")
    elif reads:
        passed.append(f"{fn_name} keys OK ({len(reads)} keys)")

# ══════════════════════════════════════════════════════
# CHECK 3: Nested function scanner
# ══════════════════════════════════════════════════════
fn_positions = [(m.start(), m.group(1))
                for m in re.finditer(r'^def (\w+)\s*\(', source, re.MULTILINE)]

all_defined = set(name for _, name in fn_positions)

for i, (pos, name) in enumerate(fn_positions):
    end = fn_positions[i+1][0] if i+1 < len(fn_positions) else len(source)
    fn_body = source[pos:end]
    nested = re.findall(r'^\s{4,}def (\w+)\s*\(', fn_body, re.MULTILINE)
    if nested:
        # Check if any nested fn is called outside this function
        for nested_fn in nested:
            outside_calls = len(re.findall(
                rf'\b{re.escape(nested_fn)}\s*\(',
                source[end:]  # only search AFTER this function
            ))
            if outside_calls > 0:
                warnings.append(
                    f"NESTED FN RISK: '{nested_fn}' defined inside '{name}' "
                    f"but called {outside_calls}x outside it — "
                    f"deleting '{name}' will break '{nested_fn}'"
                )

# ══════════════════════════════════════════════════════
# CHECK 4: Scope errors — variables used before defined
# ══════════════════════════════════════════════════════
scope_checks = [
    ('_enrich_t0',  'perf_counter', 'enrichment timer'),
    ('_bc_track',   'def _bc_track', 'telemetry'),
    ('bc_timer',    'def bc_timer',  'telemetry context manager'),
]
for var, definition, label in scope_checks:
    var_uses    = [m.start() for m in re.finditer(rf'\b{re.escape(var)}\b', source)]
    def_pos     = source.find(definition)
    if var_uses and def_pos > 0:
        first_use = min(var_uses)
        if first_use < def_pos:
            errors.append(f"SCOPE ERROR: '{var}' used at char {first_use} before defined at {def_pos}")
        else:
            passed.append(f"Scope OK: {label}")

# ══════════════════════════════════════════════════════
# CHECK 5: Duplicate function definitions
# ══════════════════════════════════════════════════════
from collections import Counter
fn_names   = re.findall(r'^def (\w+)\s*\(', source, re.MULTILINE)
duplicates = {k: v for k, v in Counter(fn_names).items() if v > 1}
if duplicates:
    for fn, count in duplicates.items():
        errors.append(f"DUPLICATE FUNCTION: '{fn}' defined {count} times — second silently overrides first")
else:
    passed.append(f"No duplicate functions ({len(fn_names)} total)")

# ══════════════════════════════════════════════════════
# CHECK 6: ReadTimeout not caught in network functions
# ══════════════════════════════════════════════════════
timeout_fns = re.findall(
    r'def (fetch_\w+|scrape_\w+)\([^)]*\).*?(?=\ndef |\Z)',
    source, re.DOTALL
)
# Check for requests.get with timeout but no ReadTimeout in except
fn_blocks = re.findall(
    r'(def (?:fetch|scrape)_\w+\([^)]*\).*?)(?=\ndef (?:fetch|scrape)|\Z)',
    source, re.DOTALL
)
timeout_risk = 0
for block in fn_blocks:
    if 'requests.get(' in block and 'timeout=' in block:
        if 'ReadTimeout' not in block and 'RequestException' not in block:
            fn_name_match = re.match(r'def (\w+)', block)
            if fn_name_match:
                warnings.append(f"TIMEOUT RISK: {fn_name_match.group(1)} has requests.get but no ReadTimeout handler")
                timeout_risk += 1

if timeout_risk == 0:
    passed.append("All fetch functions handle ReadTimeout")

# ══════════════════════════════════════════════════════
# REPORT
# ══════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("BETCOUNCIL PRE-PUSH VERIFICATION")
print("=" * 60)

if errors:
    print(f"\n🔴 ERRORS ({len(errors)}) — DO NOT PUSH:")
    for e in errors:
        print(f"  ❌ {e}")

if warnings:
    print(f"\n🟡 WARNINGS ({len(warnings)}) — Review before pushing:")
    for w in warnings:
        print(f"  ⚠️  {w}")

print(f"\n✅ PASSED ({len(passed)}):")
for p in passed:
    print(f"  ✓  {p}")

print("\n" + "=" * 60)
if errors:
    print("❌ PUSH BLOCKED — fix errors above first")
    sys.exit(1)
elif warnings:
    print("⚠️  PUSH WITH CAUTION — review warnings above")
    sys.exit(0)
else:
    print("✅ CLEAR TO PUSH")
    sys.exit(0)
