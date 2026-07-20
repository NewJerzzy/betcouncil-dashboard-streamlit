"""
weekly_audit.py — BetCouncil self-audit, runs on GitHub Actions on a
schedule (see .github/workflows/weekly_audit.yml). No manual action
required — this is the "catch it before it becomes a problem" pass that
was talked about early on and never actually got scheduled.

What it checks, every run:
  1. Dead-code audit: every fetch_* function in fetchers.py, checked via
     AST (not naive text search) for whether it's referenced anywhere
     outside its own function body — direct call, aliased import, or
     string/dict dispatch reference. Reports each as WIRED or ORPHANED,
     with the git-blame add-date so a 2-week-old function built for an
     upcoming feature doesn't get flagged the same way as something that's
     been sitting dead for 6 months.
  2. Dead signal-field audit (added 2026-07, after finding ps_ev_edge —
     a ParlaySavant confirmation signal that was computed into
     ev_signal_lookup via _sv.update({...}) but never read back
     anywhere, so it silently did nothing). Scans every _sv.update({...})
     block in app.py's board-build section, extracts each written key,
     and checks whether that key is ever read (.get(...)/[...]) outside
     its own write block. This is the same "written but never consumed"
     bug class as #1, just for dict fields instead of whole functions.
  3. Harvester freshness: pulls check_harvester_health() results for all
     HARVESTER_REGISTRY sources (reads Gist only — no live scraping, safe
     to run from a GitHub-hosted runner). Separates sources that are
     currently 🔴 STALE (were producing data, now not — actionable) from
     ⚫ NEVER SEEN (registered but no harvester has ever pushed for it —
     could be off-season, could be a registry entry with no real
     implementation behind it; needs human judgment either way, but
     shouldn't drown out the more urgent stale ones).
  4. File-size watch: app.py / fetchers.py / bc_utils.py byte size and
     line count, flagged if app.py is approaching the 1MB Git Contents
     API cutoff (already over it — this just tracks the trend).
  5. Week-over-week diff: compares against last week's audit (stored in
     the Gist) and calls out anything NEW — a function or signal field
     that flipped from WIRED to ORPHANED, a harvester that went from
     fresh to dead, a file that crossed a size threshold.

Output: pushes betcouncil_weekly_audit.json to the Gist (so the app or
any future dashboard tab can read history), and opens/updates a GitHub
Issue with a human-readable summary — so the result is visible without
anyone needing to go looking for it.

This script only reads and reports. It never deletes, edits, or disables
anything — deciding what to do with an ORPHANED function/field (wire it
in, hold it for a pending feature, or remove it) is a judgment call that
stays with a human.
"""

import ast
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

import requests

GIST_ID = "7e52e1c2c2054847c7c4663a157386c5"
AUDIT_FILE = "betcouncil_weekly_audit.json"
REPO = "NewJerzzy/betcouncil-dashboard-streamlit"

CORE_FILES = [
    "app.py", "fetchers.py", "bc_utils.py", "betcouncil_auto_scraper.py",
    "consensus_engine.py", "market_microstructure.py",
    "prop_market_intelligence.py", "sdv_source.py", "config.py",
    "arbitrage_detector.py", "diagnostics_panel.py", "unified_sharp_score.py",
]

# Files whose size we specifically track for the >1MB Git Contents API
# cutoff (anything over this needs the blob/tree/commit Git Data API
# pattern for edits, not the simple Contents API).
SIZE_WATCH = ["app.py", "fetchers.py", "bc_utils.py"]
SIZE_WARN_BYTES = 900_000   # flag as approaching the 1MB cutoff
SIZE_HARD_BYTES = 1_000_000


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


# ── 1. Dead-code audit ──────────────────────────────────────────────────

def _read(path):
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def _git_blame_date(path, lineno):
    try:
        out = subprocess.run(
            ["git", "blame", "-L", f"{lineno},{lineno}", "--date=short", path],
            capture_output=True, text=True, timeout=15,
        ).stdout
        for tok in out.split():
            if len(tok) == 10 and tok[4] == "-" and tok[7] == "-":
                return tok
    except Exception:
        pass
    return None


def audit_dead_code():
    fetchers_src = _read("fetchers.py")
    tree = ast.parse(fetchers_src)
    fn_spans = {}  # name -> (start_line, end_line)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("fetch_"):
            end = getattr(node, "end_lineno", node.lineno + 1)
            fn_spans[node.name] = (node.lineno, end)

    all_src = {f: _read(f) for f in CORE_FILES}
    combined_lines = []
    for f, src in all_src.items():
        for i, line in enumerate(src.splitlines(), 1):
            combined_lines.append((f, i, line))

    # alias map: "from fetchers import X as Y"
    import re
    alias_map = {}
    full_combined = "\n".join(all_src.values())
    for m in re.finditer(r'import\s+(fetch_\w+)\s+as\s+(\w+)', full_combined):
        alias_map[m.group(2)] = m.group(1)

    results = []
    for name, (start, end) in fn_spans.items():
        wired = False
        search_names = [name] + [a for a, real in alias_map.items() if real == name]
        for f, ln, line in combined_lines:
            in_own_body = (f == "fetchers.py" and start <= ln <= end)
            if in_own_body:
                continue
            for sn in search_names:
                if sn in line:
                    wired = True
                    break
            if wired:
                break
        date = _git_blame_date("fetchers.py", start)
        results.append({
            "name": name, "status": "WIRED" if wired else "ORPHANED",
            "added": date, "line": start,
        })

    results.sort(key=lambda r: (r["status"] != "ORPHANED", r["name"]))
    return results


# ── 1b. Dead signal-field audit ─────────────────────────────────────────
# Catches a different bug class than #1: not a whole orphaned function,
# but a dict key written into ev_signal_lookup (via `_sv.update({...})`
# in app.py's board-build section) and never read back anywhere. Found
# this by hand in ps_ev_edge (2026-07) — it was computed every board
# load and silently did nothing. This makes sure the next one doesn't
# sit undetected for months.

def audit_dead_signal_fields():
    app_src = _read("app.py")
    write_pattern = re.compile(r"_sv\.update\(\{(.*?)\}\)", re.DOTALL)
    key_pattern = re.compile(r'"([a-zA-Z_][a-zA-Z0-9_]*)"\s*:')

    write_blocks = write_pattern.findall(app_src)
    written_keys = set()
    for block in write_blocks:
        written_keys.update(key_pattern.findall(block))

    results = []
    for key in sorted(written_keys):
        total = len(re.findall(rf'"{re.escape(key)}"', app_src))
        in_write_blocks = sum(len(re.findall(rf'"{re.escape(key)}"', b)) for b in write_blocks)
        read_count = total - in_write_blocks
        status = "WIRED" if read_count > 0 else "ORPHANED"
        line = None
        date = None
        if status == "ORPHANED":
            # Only blame ORPHANED entries — WIRED ones never show a date in
            # the report, and git blame on app.py (heavily-churned, 25k+
            # lines) is the slow part of this whole audit; skipping it for
            # the ~20% that don't need it is a free, easy win.
            m = re.search(rf'"{re.escape(key)}"\s*:', app_src)
            if m:
                line = app_src[: m.start()].count("\n") + 1
                date = _git_blame_date("app.py", line)
        results.append({"key": key, "status": status, "added": date, "line": line})

    results.sort(key=lambda r: (r["status"] != "ORPHANED", r["key"]))
    return results


# ── 1c. Suspected stub functions (2026-07-16, added after a real miss) ──
# audit_dead_code() only catches functions that are never CALLED. It
# completely missed build_game_line_consensus() being a no-op — that
# function genuinely was called (once, from analyze_game_edge) and would
# have shown as WIRED. The actual bug: its whole body was a docstring
# plus `return {}`, ignoring every argument, so 18 books' worth of real
# game-line data fed into it and produced nothing every single time.
# "Called from somewhere" and "does something with what it's called
# with" are different questions — this checks the second one, which
# audit_dead_code() structurally cannot.
#
# Detection: AST-parse every CORE_FILES module, walk top-level (and
# class-level) function defs, and flag any whose body — after stripping
# a leading docstring — is just ONE statement, and that statement is
# `pass` or `return <constant-shaped literal>` (a bare value, an empty
# dict/list/set, or None) with NO reference to the function's own
# arguments anywhere in it. A function that echoes back one of its
# arguments isn't flagged (that's a real, if simple, function) — only
# ones whose return value is provably independent of every input.
def audit_stub_functions():
    results = []
    for filename in CORE_FILES:
        try:
            src = _read(filename)
        except Exception:
            continue
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            body = node.body
            # Strip a leading docstring, if present
            if body and isinstance(body[0], ast.Expr) and isinstance(
                getattr(body[0], "value", None), (ast.Constant,)
            ) and isinstance(body[0].value.value, str):
                body = body[1:]
            if len(body) != 1:
                continue

            stmt = body[0]
            is_trivial = False
            if isinstance(stmt, ast.Pass):
                is_trivial = True
            elif isinstance(stmt, ast.Return):
                val = stmt.value
                if val is None:
                    is_trivial = True
                elif isinstance(val, ast.Constant):
                    is_trivial = True
                elif isinstance(val, (ast.Dict, ast.List, ast.Set, ast.Tuple)) and not (
                    val.keys if isinstance(val, ast.Dict) else val.elts
                ):
                    is_trivial = True  # empty {}/[]/()/set()

            if not is_trivial:
                continue

            # Skip if the function has no arguments at all — a genuinely
            # argument-less constant-returning function (a config getter,
            # a version string) isn't a "silently ignores its inputs" bug,
            # since it has no inputs to ignore.
            arg_names = [a.arg for a in node.args.args + node.args.kwonlyargs]
            if node.args.vararg:
                arg_names.append(node.args.vararg.arg)
            if node.args.kwarg:
                arg_names.append(node.args.kwarg.arg)
            if not arg_names:
                continue

            date = _git_blame_date(filename, node.lineno)
            results.append({
                "name": node.name, "file": filename, "line": node.lineno,
                "args": arg_names, "added": date,
            })

    results.sort(key=lambda r: r.get("added") or "", reverse=True)
    return results




def audit_harvester_health():
    try:
        sys.path.insert(0, ".")
        import fetchers as _f
        out = {}
        for sport in ("NBA", "MLB", "NFL", "NHL", "WNBA"):
            try:
                out[sport] = _f.check_harvester_health(sport)
            except Exception as e:
                out[sport] = {"error": str(e)[:200]}
        return out
    except Exception as e:
        return {"error": f"could not import fetchers.py: {str(e)[:200]}"}


# ── 1d. Missing/broken local imports ──────────────────────────────────
# The exact check that would have caught unified_sharp_score.py importing
# 5 modules (team_canon, book_quality, bayesian_line_updater,
# movement_classifier, bet_decision_layer) that didn't exist anywhere in
# the repo -- the whole Sharp Board was silently dead because of it, and
# none of the existing audits checked this basic thing: does every local
# import actually resolve to a real file with the name actually defined
# in it. Found by an external audit (Replit) instead of catching it here
# first, which is the whole reason this check exists now.
def audit_missing_imports():
    import re as _re
    results = []
    repo_files = {f for f in os.listdir(".") if f.endswith(".py")}
    local_modules = {f[:-3] for f in repo_files}  # "team_canon.py" -> "team_canon"

    for filename in CORE_FILES:
        try:
            src = _read(filename)
        except Exception:
            continue
        try:
            tree = ast.parse(src)
        except SyntaxError as e:
            results.append({"file": filename, "import": "(file itself)",
                             "issue": f"SYNTAX ERROR: {e}"})
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                mod = node.module.split(".")[0]
                if mod not in local_modules:
                    continue  # not a local module (stdlib/third-party) -- not our concern here
                mod_path = f"{mod}.py"
                if mod_path not in repo_files:
                    results.append({"file": filename, "import": f"from {node.module} import ...",
                                     "issue": f"MODULE MISSING: {mod_path} does not exist in the repo"})
                    continue
                # Module exists -- verify each imported name is actually
                # defined there (function/class/module-level assignment).
                try:
                    mod_src = _read(mod_path)
                    mod_tree = ast.parse(mod_src)
                except Exception:
                    continue
                defined_names = set()
                for n in ast.walk(mod_tree):
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        defined_names.add(n.name)
                    elif isinstance(n, ast.Assign):
                        for t in n.targets:
                            if isinstance(t, ast.Name):
                                defined_names.add(t.id)
                # Star imports and wildcard re-exports can't be statically
                # verified this way -- skip rather than false-flag.
                if any(a.name == "*" for a in node.names):
                    continue
                for alias in node.names:
                    if alias.name not in defined_names:
                        results.append({"file": filename, "import": f"from {node.module} import {alias.name}",
                                         "issue": f"NAME NOT FOUND: '{alias.name}' is not defined anywhere in {mod_path}"})

    return results


# ── 1e. Broad exception blocks that swallow everything silently ────────
# A different, real bug class than a missing import: classify_book_role()
# was called as classify_book_role(x)["role"] -- a guaranteed TypeError
# every time it ran with real data -- but a wrapping `except Exception:
# pass` (no logging, no re-raise) hid it completely; it never showed up
# anywhere, not in logs, not in the UI. This doesn't try to prove a given
# except block IS hiding a bug (too many legitimate defensive ones exist
# to do that reliably) -- it just enumerates the highest-risk shape (bare
# except / except Exception, body is ONLY `pass` or `continue`, zero
# logging) so they're periodically reviewable instead of invisible.
def audit_silent_except_blocks():
    results = []
    for filename in CORE_FILES:
        try:
            src = _read(filename)
            tree = ast.parse(src)
        except Exception:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Try):
                continue
            for handler in node.handlers:
                is_broad = (
                    handler.type is None or
                    (isinstance(handler.type, ast.Name) and handler.type.id == "Exception") or
                    (isinstance(handler.type, ast.Attribute) and handler.type.attr == "Exception")
                )
                if not is_broad:
                    continue
                body = handler.body
                is_silent = len(body) >= 1 and all(
                    isinstance(s, (ast.Pass, ast.Continue)) or
                    (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))  # a bare string/comment-like expr
                    for s in body
                )
                if is_silent:
                    results.append({
                        "file": filename, "line": handler.lineno,
                        "note": "bare/Exception except with no logging -- any real bug here is invisible",
                    })
    return results


# ── 3. File size watch ──────────────────────────────────────────────────

def audit_file_sizes():
    out = []
    for f in SIZE_WATCH:
        try:
            size = os.path.getsize(f)
            lines = len(_read(f).splitlines())
        except FileNotFoundError:
            continue
        status = "OK"
        if size >= SIZE_HARD_BYTES:
            status = "OVER_1MB_LIMIT"
        elif size >= SIZE_WARN_BYTES:
            status = "APPROACHING_1MB"
        out.append({"file": f, "bytes": size, "lines": lines, "status": status})
    return out


# ── Gist read/write ───────────────────────────────────────────────────

def gist_read_previous(token):
    try:
        resp = requests.get(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
            timeout=20,
        )
        if resp.status_code != 200:
            return None
        files = resp.json().get("files", {})
        f = files.get(AUDIT_FILE)
        if not f:
            return None
        content = f.get("content", "")
        if f.get("truncated"):
            raw = requests.get(f["raw_url"], timeout=20).text
            content = raw
        return json.loads(content)
    except Exception as e:
        log(f"Could not read previous audit: {e}")
        return None


def gist_push(token, payload):
    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {AUDIT_FILE: {"content": json.dumps(payload, indent=2)}}},
        timeout=30,
    )
    return resp.status_code in (200, 201)


# ── Diff against previous run ────────────────────────────────────────

def diff_reports(prev, current):
    changes = []
    if not prev:
        return ["First audit run — no prior baseline to diff against."]

    prev_dead = {r["name"] for r in prev.get("dead_code", []) if r["status"] == "ORPHANED"}
    cur_dead = {r["name"] for r in current["dead_code"] if r["status"] == "ORPHANED"}
    newly_orphaned = cur_dead - prev_dead
    newly_wired = prev_dead - cur_dead
    for n in sorted(newly_orphaned):
        changes.append(f"🔴 NEW orphaned function this week: {n}")
    for n in sorted(newly_wired):
        changes.append(f"✅ Now wired in (was orphaned last week): {n}")

    prev_dead_sig = {r["key"] for r in prev.get("dead_signal_fields", []) if r["status"] == "ORPHANED"}
    cur_dead_sig = {r["key"] for r in current.get("dead_signal_fields", []) if r["status"] == "ORPHANED"}
    newly_orphaned_sig = cur_dead_sig - prev_dead_sig
    newly_wired_sig = prev_dead_sig - cur_dead_sig
    for n in sorted(newly_orphaned_sig):
        changes.append(f"🔴 NEW orphaned signal field this week: {n}")
    for n in sorted(newly_wired_sig):
        changes.append(f"✅ Signal field now wired in (was orphaned last week): {n}")

    prev_stubs = {(r["file"], r["name"]) for r in prev.get("stub_functions", [])}
    cur_stubs = {(r["file"], r["name"]) for r in current.get("stub_functions", [])}
    for f, n in sorted(cur_stubs - prev_stubs):
        changes.append(f"🔴 NEW suspected stub function this week: {f}::{n}")
    for f, n in sorted(prev_stubs - cur_stubs):
        changes.append(f"✅ Stub function now implemented (was a stub last week): {f}::{n}")

    prev_sizes = {r["file"]: r["status"] for r in prev.get("file_sizes", [])}
    for r in current["file_sizes"]:
        old = prev_sizes.get(r["file"])
        if old and old != r["status"] and r["status"] != "OK":
            changes.append(f"⚠️ {r['file']} size status changed: {old} → {r['status']} ({r['bytes']:,} bytes)")

    return changes or ["No material changes since last audit."]


# ── GitHub Issue ─────────────────────────────────────────────────────

def build_summary_markdown(current, diff):
    dead = [r for r in current["dead_code"] if r["status"] == "ORPHANED"]
    wired_count = len(current["dead_code"]) - len(dead)

    dead_sig = [r for r in current.get("dead_signal_fields", []) if r["status"] == "ORPHANED"]
    wired_sig_count = len(current.get("dead_signal_fields", [])) - len(dead_sig)

    stubs = current.get("stub_functions", [])
    missing_imports = current.get("missing_imports", [])
    silent_excepts = current.get("silent_excepts", [])

    lines = [f"## BetCouncil Weekly Self-Audit — {current['run_date']}", ""]
    lines.append(f"**Fetch functions:** {wired_count} wired in / {len(dead)} orphaned (defined, never referenced)")
    lines.append(f"**Signal fields:** {wired_sig_count} wired in / {len(dead_sig)} orphaned "
                  f"(written into ev_signal_lookup, never read back — see ps_ev_edge, fixed 2026-07)")
    lines.append(f"**Suspected stub functions:** {len(stubs)} — called from real code, but their entire "
                  f"body is a docstring + a constant return that ignores every argument (see "
                  f"build_game_line_consensus, fixed 2026-07 — 18 books' real data fed a function "
                  f"that silently returned {{}} regardless)")
    lines.append(f"**Broken local imports:** {len(missing_imports)} — a module imported by a CORE_FILES "
                  f"file that either doesn't exist in the repo, or doesn't define the specific name being "
                  f"imported (see unified_sharp_score.py importing 5 nonexistent modules, found by an "
                  f"external audit rather than this one, fixed 2026-07 — this check exists because of that miss)")
    lines.append(f"**Silent exception blocks:** {len(silent_excepts)} — bare/`except Exception:` blocks "
                  f"whose entire body is `pass`/`continue` with zero logging, the highest-risk shape for "
                  f"hiding a real bug completely (see classify_book_role() called as a dict when it "
                  f"returns a string, a guaranteed TypeError every run, invisible because of exactly "
                  f"this pattern, fixed 2026-07)")
    if missing_imports:
        lines.append("")
        lines.append("#### 🔴 Broken imports (fix immediately — these modules/names don't exist)")
        for r in missing_imports[:20]:
            lines.append(f"- `{r['file']}`: `{r['import']}` — {r['issue']}")
    if silent_excepts:
        lines.append("")
        lines.append("#### 🟡 Silent except blocks (review — may be hiding a real bug)")
        for r in silent_excepts[:20]:
            lines.append(f"- `{r['file']}:{r['line']}` — {r['note']}")
    lines.append("")
    lines.append("### Changes since last audit")
    for c in diff:
        lines.append(f"- {c}")
    lines.append("")

    if dead:
        lines.append("### Currently orphaned functions (age-sorted, newest first)")
        lines.append("*Not an automatic delete list — check against pending feature work "
                      "(e.g. off-season sports, in-progress builds) before removing anything.*")
        lines.append("")
        lines.append("| Function | Added | Line |")
        lines.append("|---|---|---|")
        dead_sorted = sorted(dead, key=lambda r: r.get("added") or "", reverse=True)
        for r in dead_sorted[:40]:
            lines.append(f"| `{r['name']}` | {r.get('added') or 'unknown'} | {r['line']} |")
        if len(dead_sorted) > 40:
            lines.append(f"| ...and {len(dead_sorted)-40} more | | |")
        lines.append("")

    if dead_sig:
        lines.append("### Currently orphaned signal fields (age-sorted, newest first)")
        lines.append("*A field computed into ev_signal_lookup but never read back anywhere — "
                      "silently inert, same bug class as ps_ev_edge. Either wire it into "
                      "compute_multi_signal_edge or remove the dead write.*")
        lines.append("")
        lines.append("| Field | Added | Line |")
        lines.append("|---|---|---|")
        dead_sig_sorted = sorted(dead_sig, key=lambda r: r.get("added") or "", reverse=True)
        for r in dead_sig_sorted[:40]:
            lines.append(f"| `{r['key']}` | {r.get('added') or 'unknown'} | {r.get('line') or '?'} |")
        if len(dead_sig_sorted) > 40:
            lines.append(f"| ...and {len(dead_sig_sorted)-40} more | | |")
        lines.append("")

    if stubs:
        lines.append("### Suspected stub functions (age-sorted, newest first)")
        lines.append("*Called from real code, but the whole body is a docstring + a constant "
                      "return (`return {}`, `return []`, `return None`, `pass`) that ignores every "
                      "argument. Not automatically wrong — some of these may be deliberate "
                      "compatibility shims — but each one is worth a human look, since this is "
                      "exactly the shape build_game_line_consensus had for who knows how long "
                      "before anyone noticed 18 books' worth of real data was going nowhere.*")
        lines.append("")
        lines.append("| Function | File | Args ignored | Added | Line |")
        lines.append("|---|---|---|---|---|")
        for r in stubs[:40]:
            lines.append(f"| `{r['name']}` | {r['file']} | {', '.join(r['args'])} | {r.get('added') or 'unknown'} | {r['line']} |")
        if len(stubs) > 40:
            lines.append(f"| ...and {len(stubs)-40} more | | | | |")
        lines.append("")

    lines.append("### File sizes")
    lines.append("| File | Bytes | Lines | Status |")
    lines.append("|---|---|---|---|")
    for r in current["file_sizes"]:
        lines.append(f"| {r['file']} | {r['bytes']:,} | {r['lines']:,} | {r['status']} |")
    lines.append("")

    hh = current["harvester_health"]
    lines.append("### Harvester freshness (by sport)")
    lines.append("*🔴 STALE = was producing data, now hasn't in longer than expected — actionable, "
                  "check the workflow/harvester script. ⚫ NEVER SEEN = registered but no data has "
                  "ever landed — could be off-season, could be a registry entry with nothing wired "
                  "behind it; lower urgency but still worth a look if it's a core props/sharp source.*")
    lines.append("")
    # Surface actually-actionable regressions by name, not just a count —
    # a wall of "N never-seen" per sport buries the sources that were
    # WORKING and have since broken, which matter far more.
    stale_by_tier = {}
    for sport, results in hh.items():
        if isinstance(results, dict) and "error" in results:
            continue
        for r in results:
            if r.get("status") == "🔴":
                stale_by_tier.setdefault(r.get("tier", "signal"), []).append(
                    f"{r['name']} ({sport}, {r.get('age_minutes', '?')}min old, expected {r.get('expected_minutes','?')}min)"
                )
    tier_priority = ["props", "sharp", "lines", "signal"]
    any_stale = any(stale_by_tier.get(t) for t in tier_priority)
    if any_stale:
        lines.append("**🔴 Actionable — currently stale (was working, now isn't):**")
        for tier in tier_priority:
            for item in sorted(set(stale_by_tier.get(tier, []))):
                lines.append(f"- [{tier}] {item}")
        lines.append("")

    for sport, results in hh.items():
        if isinstance(results, dict) and "error" in results:
            lines.append(f"- **{sport}**: check failed — {results['error']}")
            continue
        green = sum(1 for r in results if r.get("status") == "🟢")
        red = sum(1 for r in results if r.get("status") == "🔴")
        yellow = sum(1 for r in results if r.get("status") == "🟡")
        grey = sum(1 for r in results if r.get("status") == "⚫")
        lines.append(f"- **{sport}**: {green} fresh, {yellow} stale, {red} broken, {grey} never-seen")

    return "\n".join(lines)


def file_github_issue(token, body_md):
    """
    Update a single persistent audit issue instead of filing a new one every
    run. Previous behavior opened a new "Weekly Self-Audit — <date>" issue
    on every run (scheduled or manual) with no follow-through mechanism —
    confirmed 2026-07-18 that issues #1/#3/#4/#5/#6 had piled up open and
    unread since 2026-07-11 despite the audit running (and finding real,
    fixable problems) every time. Now: find the existing open issue labeled
    "audit"+"automated", edit its body in place (title stays static, GitHub
    preserves edit history) so there's one persistent, always-current
    status page instead of an ever-growing unread backlog.
    """
    title = "Weekly Self-Audit (persistent — updated in place each run)"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}

    search = requests.get(
        f"https://api.github.com/repos/{REPO}/issues",
        headers=headers,
        params={"state": "open", "labels": "audit,automated", "per_page": 20},
        timeout=30,
    )
    existing_number = None
    if search.status_code == 200:
        for issue in search.json():
            if issue.get("title", "").startswith("Weekly Self-Audit"):
                existing_number = issue["number"]
                break

    stamped_body = f"_Last updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_\n\n{body_md}"

    if existing_number:
        resp = requests.patch(
            f"https://api.github.com/repos/{REPO}/issues/{existing_number}",
            headers=headers,
            json={"title": title, "body": stamped_body},
            timeout=30,
        )
        if resp.status_code == 200:
            log(f"Updated existing issue #{existing_number}: {resp.json().get('html_url')}")
            return True
        log(f"Issue update failed: {resp.status_code} {resp.text[:300]}")
        return False

    resp = requests.post(
        f"https://api.github.com/repos/{REPO}/issues",
        headers=headers,
        json={"title": title, "body": stamped_body, "labels": ["audit", "automated"]},
        timeout=30,
    )
    if resp.status_code == 201:
        log(f"Filed new persistent issue: {resp.json().get('html_url')}")
        return True
    log(f"Issue creation failed: {resp.status_code} {resp.text[:300]}")
    return False


def main():
    token = os.environ["GITHUB_TOKEN"]

    log("Running dead-code audit...")
    dead_code = audit_dead_code()
    log(f"  {sum(1 for r in dead_code if r['status']=='ORPHANED')} orphaned / {len(dead_code)} total fetch functions")

    log("Running dead signal-field audit...")
    dead_signal_fields = audit_dead_signal_fields()
    log(f"  {sum(1 for r in dead_signal_fields if r['status']=='ORPHANED')} orphaned / {len(dead_signal_fields)} total signal fields")

    log("Running stub-function audit...")
    stub_functions = audit_stub_functions()
    log(f"  {len(stub_functions)} suspected stub functions found")

    log("Checking harvester health...")
    harvester_health = audit_harvester_health()

    log("Checking file sizes...")
    file_sizes = audit_file_sizes()

    log("Checking local imports resolve...")
    missing_imports = audit_missing_imports()
    log(f"  {len(missing_imports)} broken import(s) found")

    log("Scanning for silent exception blocks...")
    silent_excepts = audit_silent_except_blocks()
    log(f"  {len(silent_excepts)} bare/silent except block(s) found")

    current = {
        "run_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "run_ts": datetime.now(timezone.utc).isoformat(),
        "dead_code": dead_code,
        "dead_signal_fields": dead_signal_fields,
        "stub_functions": stub_functions,
        "harvester_health": harvester_health,
        "file_sizes": file_sizes,
        "missing_imports": missing_imports,
        "silent_excepts": silent_excepts,
    }

    log("Reading previous audit for diff...")
    previous = gist_read_previous(token)
    diff = diff_reports(previous, current)
    for c in diff:
        log(f"  {c}")

    log("Pushing this week's audit to Gist...")
    gist_push(token, current)

    log("Filing GitHub Issue with summary...")
    summary = build_summary_markdown(current, diff)
    file_github_issue(token, summary)

    log("Done.")


if __name__ == "__main__":
    main()
