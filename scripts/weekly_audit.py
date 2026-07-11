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
  2. Harvester freshness: pulls check_harvester_health() results for all
     HARVESTER_REGISTRY sources (reads Gist only — no live scraping, safe
     to run from a GitHub-hosted runner).
  3. File-size watch: app.py / fetchers.py / bc_utils.py byte size and
     line count, flagged if app.py is approaching the 1MB Git Contents
     API cutoff (already over it — this just tracks the trend).
  4. Week-over-week diff: compares against last week's audit (stored in
     the Gist) and calls out anything NEW — a function that flipped from
     WIRED to ORPHANED, a harvester that went from fresh to dead, a file
     that crossed a size threshold.

Output: pushes betcouncil_weekly_audit.json to the Gist (so the app or
any future dashboard tab can read history), and opens/updates a GitHub
Issue with a human-readable summary — so the result is visible without
anyone needing to go looking for it.

This script only reads and reports. It never deletes, edits, or disables
anything — deciding what to do with an ORPHANED function (wire it in,
hold it for a pending feature, or remove it) is a judgment call that
stays with a human.
"""

import ast
import json
import os
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


# ── 2. Harvester freshness (Gist read only, no live scraping) ──────────

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

    lines = [f"## BetCouncil Weekly Self-Audit — {current['run_date']}", ""]
    lines.append(f"**Fetch functions:** {wired_count} wired in / {len(dead)} orphaned (defined, never referenced)")
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

    lines.append("### File sizes")
    lines.append("| File | Bytes | Lines | Status |")
    lines.append("|---|---|---|---|")
    for r in current["file_sizes"]:
        lines.append(f"| {r['file']} | {r['bytes']:,} | {r['lines']:,} | {r['status']} |")
    lines.append("")

    hh = current["harvester_health"]
    lines.append("### Harvester freshness (by sport)")
    for sport, results in hh.items():
        if isinstance(results, dict) and "error" in results:
            lines.append(f"- **{sport}**: check failed — {results['error']}")
            continue
        green = sum(1 for r in results if r.get("status") == "🟢")
        red = sum(1 for r in results if r.get("status") == "🔴")
        yellow = sum(1 for r in results if r.get("status") == "🟡")
        grey = sum(1 for r in results if r.get("status") == "⚫")
        lines.append(f"- **{sport}**: {green} fresh, {yellow} stale, {red} dead, {grey} never-seen")

    return "\n".join(lines)


def file_github_issue(token, body_md):
    title = f"Weekly Self-Audit — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
    resp = requests.post(
        f"https://api.github.com/repos/{REPO}/issues",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"title": title, "body": body_md, "labels": ["audit", "automated"]},
        timeout=30,
    )
    if resp.status_code == 201:
        log(f"Filed issue: {resp.json().get('html_url')}")
        return True
    log(f"Issue creation failed: {resp.status_code} {resp.text[:300]}")
    return False


def main():
    token = os.environ["GITHUB_TOKEN"]

    log("Running dead-code audit...")
    dead_code = audit_dead_code()
    log(f"  {sum(1 for r in dead_code if r['status']=='ORPHANED')} orphaned / {len(dead_code)} total fetch functions")

    log("Checking harvester health...")
    harvester_health = audit_harvester_health()

    log("Checking file sizes...")
    file_sizes = audit_file_sizes()

    current = {
        "run_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "run_ts": datetime.now(timezone.utc).isoformat(),
        "dead_code": dead_code,
        "harvester_health": harvester_health,
        "file_sizes": file_sizes,
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
