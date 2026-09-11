"""
Captures the five README/publication screenshots from the REAL, currently
exported dist/ demo -- no fabricated data, no image generation, no editing
of analysis values. Viewport-only captures (not full-page) at a normal
desktop size, since full-page captures of the Details tab in particular are
many thousands of pixels tall and unsuitable for a README embed.

Requires dist/ to be served with Range-request support (see
scripts/range_http_server.py -- plain `python -m http.server` breaks video
seeking, which matters for the Replay screenshot). Not part of the shipped
app or the exported dist/ bundle.

Usage (with the Range server already running on :8843):
    .venv\\Scripts\\python scripts\\capture_readme_screenshots.py
"""
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://localhost:8843"
OUT = Path("docs/screenshots")
OUT.mkdir(parents=True, exist_ok=True)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        page.goto(BASE, wait_until="networkidle")
        page.wait_for_timeout(400)
        page.screenshot(path=str(OUT / "landing.png"), full_page=False)
        print("landing.png")

        page.click("text=Try Interactive Demo")
        page.wait_for_selector("#tab-shots .shot-chip", timeout=15000, state="attached")
        page.wait_for_timeout(600)
        page.screenshot(path=str(OUT / "coach.png"), full_page=False)
        print("coach.png")

        # Precise tab-button IDs -- a bare "text=Shots"/"text=Replay"/etc.
        # locator also matches the (currently hidden, but still present in
        # the DOM) landing-page hero heading "...good shots and bad
        # shots?", and Playwright's actionability wait then times out
        # against that invisible match instead of the real tab button.
        page.click("#tabbtn-shots")
        page.wait_for_timeout(400)
        page.locator("#tab-shots .shot-chip").first.click()
        page.wait_for_timeout(400)
        page.screenshot(path=str(OUT / "shots.png"), full_page=False)
        print("shots.png")

        page.click("#tabbtn-replay")
        page.wait_for_selector("#tab-replay .shot-chip", timeout=8000, state="attached")
        page.wait_for_timeout(800)  # let the first frame paint
        page.screenshot(path=str(OUT / "replay.png"), full_page=False)
        print("replay.png")

        page.click("#tabbtn-details")
        page.wait_for_timeout(600)
        page.screenshot(path=str(OUT / "details.png"), full_page=False)
        print("details.png")

        browser.close()


if __name__ == "__main__":
    main()
