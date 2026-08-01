---
name: Gist 300-file cap rename
description: How to add a new file to the gist when it's at the 300-file hard cap
---

## Problem
The shared gist `7e52e1c2c2054847c7c4663a157386c5` is at GitHub's 300-file hard cap. Any PATCH that creates a brand-new filename silently fails (HTTP 200 returned, but the file is not actually created).

## Solution: Atomic rename
GitHub Gist PATCH API supports renaming an existing file while updating its content in a single atomic operation:

```json
PATCH /gists/{gist_id}
{
  "files": {
    "old_dead_filename.json": {
      "filename": "new_target_filename.json",
      "content": "... new content ..."
    }
  }
}
```

This renames `old_dead_filename.json` → `new_target_filename.json` AND updates the content, keeping total file count at 300.

## Script pattern
```python
existing_files = _get_gist_files(github_token)  # GET gist, return set of filenames
if TARGET_FILE in existing_files:
    files_payload = {TARGET_FILE: {"content": content}}
else:
    files_payload = {LEGACY_FILE: {"filename": TARGET_FILE, "content": content}}
push_files(files_payload, github_token)
```

## Confirmed dead files available for repurposing (as of 2026-08-01)
- `betcouncil_oddsshark_CFB.json` (143b) → repurposed to `betcouncil_evbets_combined.json`
- `betcouncil_oddsshark_NBA.json` (143b) → repurposed to `betcouncil_vsin_splits.json`
- `betcouncil_oddsshark_NFL.json` (143b) — still available
- `betcouncil_oddsshark_NHL.json` (143b) — still available
- `betcouncil_prophetx_sports.json` (126b) — still available
- `betcouncil_bettingpros_debug.json` (160b) — may be active (check before using)

**Why:** `betcouncil_oddsshark_{CFB,NBA,NFL,NHL}.json` are legacy files from a retired OddsShark scraper replaced by the covers.com consensus script (`betcouncil_oddsshark_consensus_*.json`).
