#!/usr/bin/env python3
"""
BetCouncil Login Diagnostic
Finds the correct input selectors for each book.
Run: python login_diagnostic.py
"""
from playwright.sync_api import sync_playwright
import time

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

def inspect_login_page(book, url):
    print(f"\n{'='*50}")
    print(f"Inspecting: {book}")
    print(f"URL: {url}")
    print(f"{'='*50}")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)  # visible so you can see it
            ctx  = browser.new_context(user_agent=UA, viewport={"width":1280,"height":800})
            page = ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            time.sleep(3)

            # Find all inputs
            inputs = page.query_selector_all("input")
            print(f"\nInputs found: {len(inputs)}")
            for inp in inputs:
                try:
                    attrs = {
                        "type":        inp.get_attribute("type"),
                        "name":        inp.get_attribute("name"),
                        "id":          inp.get_attribute("id"),
                        "placeholder": inp.get_attribute("placeholder"),
                        "class":       (inp.get_attribute("class") or "")[:40],
                    }
                    print(f"  {attrs}")
                except:
                    pass

            # Find buttons
            buttons = page.query_selector_all("button")
            print(f"\nButtons found: {len(buttons)}")
            for btn in buttons[:10]:
                try:
                    print(f"  type={btn.get_attribute('type')} text='{btn.inner_text()[:30]}'")
                except:
                    pass

            print(f"\nCurrent URL: {page.url}")
            input("\nPress Enter to close browser and continue...")
            browser.close()
    except Exception as e:
        print(f"Error: {e}")

# Inspect each book login page
books = [
    ("DraftKings", "https://sportsbook.draftkings.com/login"),
    ("FanDuel",    "https://sportsbook.fanduel.com/login"),
    ("BetMGM",     "https://sports.betmgm.com/en/sports/login"),
    ("Caesars",    "https://sportsbook.caesars.com/us/nj/bet#login"),
    ("MyBookie",   "https://mybookie.ag/login"),
]

for book, url in books:
    inspect_login_page(book, url)
    choice = input(f"Continue to next book? (y/n): ")
    if choice.lower() != "y":
        break

print("\nDone — send the output to Claude to fix the selectors.")
