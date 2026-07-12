"""Writes a minimal config.json for betcouncil_auto_scraper.py in CI.
Only includes what's needed for the no-login books (DK, BetMGM, Novig, Betr) --
none of them require credentials, just the github_token/gist_id for pushing
results. Real credentials for login-gated books (FanDuel, Caesars, MyBookie)
stay out of this file entirely; those books aren't run from CI.
"""
import json
import os

cfg = {
    "github_token": os.environ["GIST_TOKEN"],
    "gist_id": "7e52e1c2c2054847c7c4663a157386c5",
    "draftkings": {},
    "betmgm": {},
}

with open("config.json", "w") as f:
    json.dump(cfg, f)

print("config.json written")
