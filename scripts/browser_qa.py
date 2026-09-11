"""
Overnight publication-readiness browser QA driver for dist/ (served at
http://localhost:8843). Read-only: drives a real headless Chromium against
the actual exported bundle and records screenshots + console/network errors
+ extracted DOM text for each phase, so the final report reflects ACTUALLY
OBSERVED behavior, not inference from source. Not part of the app or test
suite -- a one-off QA tool for this pass.
"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://localhost:8843"
OUT = Path("data/diagnostics/browser_qa")
OUT.mkdir(parents=True, exist_ok=True)

console_errors = []
network_failures = []
page_errors = []


def log_console(msg):
    if msg.type in ("error", "warning"):
        console_errors.append(f"[{msg.type}] {msg.text}")


def log_request_failed(request):
    network_failures.append(f"FAILED: {request.method} {request.url} -- {request.failure}")


def log_response(response):
    if response.status >= 400:
        network_failures.append(f"HTTP {response.status}: {response.url}")


def log_page_error(exc):
    page_errors.append(str(exc))


def shot(page, name, full_page=True):
    path = OUT / f"{name}.png"
    page.screenshot(path=str(path), full_page=full_page)
    print(f"  screenshot: {path}")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        results = {}

        # ---- DESKTOP, LIGHT MODE (default) ----
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, color_scheme="light")
        page = ctx.new_page()
        page.on("console", log_console)
        page.on("requestfailed", log_request_failed)
        page.on("response", log_response)
        page.on("pageerror", log_page_error)

        print("=== LANDING (desktop, light) ===")
        page.goto(BASE, wait_until="networkidle")
        page.wait_for_timeout(500)
        shot(page, "01_landing_desktop_light")
        results["landing_title"] = page.title()
        results["landing_body_text_sample"] = page.inner_text("body")[:1500]

        # Find and click into the demo (banner / CTA / nav) -- try a few
        # plausible selectors rather than assuming exact markup.
        print("=== ENTERING DEMO ===")
        entered = False
        for sel in ["text=Try Interactive Demo", "text=View Demo", "text=Live Demo", "text=Try the Demo",
                     "a[href*='demo']", ".demo-banner a", ".demo-banner button", "#nav-dashboard",
                     "text=Dashboard", "text=Demo"]:
            try:
                loc = page.locator(sel).first
                if loc.count() > 0 and loc.is_visible():
                    loc.click(timeout=2000)
                    entered = True
                    print(f"  clicked selector: {sel}")
                    break
            except Exception:
                continue
        page.wait_for_timeout(1500)
        shot(page, "02_after_entering_demo_desktop_light")
        results["entered_demo_via_click"] = entered

        # Wait for session data (shot chips) to actually render. Scoped to
        # #tab-shots specifically -- the bare ".shot-chip" selector also
        # matches the (initially hidden) Replay "Jump to shot" panel, which
        # made Playwright's strict-mode "resolved to N elements" visibility
        # wait flaky/ambiguous even when the data had rendered correctly.
        try:
            page.wait_for_selector("#tab-shots .shot-chip", timeout=15000, state="attached")
            results["shot_chips_rendered"] = True
        except Exception as e:
            results["shot_chips_rendered"] = False
            results["shot_chips_error"] = str(e)

        shot(page, "03_dashboard_loaded_desktop_light")

        # ---- COACH TAB ----
        print("=== COACH TAB ===")
        for sel in ["text=Coach", "#nav-coach", "[data-tab='coach']"]:
            try:
                loc = page.locator(sel).first
                if loc.count() > 0 and loc.is_visible():
                    loc.click(timeout=2000)
                    break
            except Exception:
                continue
        page.wait_for_timeout(800)
        shot(page, "04_coach_tab_desktop_light")
        results["coach_header_text"] = page.inner_text("#tab-coach")[:2000] if page.locator("#tab-coach").count() else None

        # ---- SHOTS TAB ----
        print("=== SHOTS TAB ===")
        for sel in ["text=Shots", "#nav-shots", "[data-tab='shots']"]:
            try:
                loc = page.locator(sel).first
                if loc.count() > 0 and loc.is_visible():
                    loc.click(timeout=2000)
                    break
            except Exception:
                continue
        page.wait_for_timeout(800)
        chip_count = page.locator("#tab-shots .shot-chip").count()
        results["shot_chip_count"] = chip_count
        shot(page, "05_shots_tab_desktop_light")
        if chip_count:
            page.locator("#tab-shots .shot-chip").first.click()
            page.wait_for_timeout(500)
            shot(page, "06_shot_detail_desktop_light")
            results["shot1_detail_text"] = page.inner_text("#shot-detail")[:2000] if page.locator("#shot-detail").count() else None

        # ---- REPLAY TAB + JUMP TO SHOT TORTURE TEST ----
        print("=== REPLAY TAB ===")
        for sel in ["text=Replay", "#nav-replay", "[data-tab='replay']"]:
            try:
                loc = page.locator(sel).first
                if loc.count() > 0 and loc.is_visible():
                    loc.click(timeout=2000)
                    break
            except Exception:
                continue
        page.wait_for_timeout(1000)
        shot(page, "07_replay_tab_desktop_light")

        video_present = page.locator("video").count() > 0
        results["replay_video_present"] = video_present

        jump_results = []
        replay_chip_count = 0
        try:
            page.wait_for_selector("#tab-replay .shot-chip", timeout=8000, state="attached")
            replay_chip_count = page.locator("#tab-replay .shot-chip").count()
        except Exception:
            pass
        results["replay_chip_count"] = replay_chip_count

        if video_present and replay_chip_count:
            # The Replay "Jump to shot" chips render `#N` as text in a child
            # `.n` span and store the seek target in `data-t` (start_time_sec)
            # -- unlike the Shots-tab chips, they carry no `data-shot`
            # attribute and never toggle an "active" class (see app.js
            # renderReplay/seekReplayTo). Match by exact chip-number text.
            order = [1, 11, 3, 9, 4, 10, 2, 8] + list(range(1, 12))  # torture pattern + full sweep
            for shot_n in order:
                try:
                    chip = page.locator("#tab-replay .shot-chip").filter(
                        has=page.locator(f".n:text-is('#{shot_n}')")
                    )
                    if chip.count() == 0:
                        jump_results.append({"shot": shot_n, "ok": False, "error": "no chip matched by #N text"})
                        continue
                    target_t = chip.first.get_attribute("data-t")
                    chip.first.click(timeout=3000)
                    page.wait_for_timeout(600)
                    cur_time = page.eval_on_selector("video", "el => el.currentTime")
                    ready_state = page.eval_on_selector("video", "el => el.readyState")
                    seek_close_enough = (
                        target_t is not None and cur_time is not None and abs(cur_time - float(target_t)) < 1.0
                    )
                    jump_results.append({
                        "shot": shot_n, "ok": True, "currentTime": cur_time, "readyState": ready_state,
                        "target_t": target_t, "seek_close_enough": seek_close_enough,
                    })
                except Exception as e:
                    jump_results.append({"shot": shot_n, "ok": False, "error": str(e)})
            shot(page, "08_replay_after_jump_sequence_desktop_light")
        results["jump_to_shot"] = jump_results

        # ---- DETAILS TAB ----
        print("=== DETAILS TAB ===")
        for sel in ["text=Details", "#nav-details", "[data-tab='details']"]:
            try:
                loc = page.locator(sel).first
                if loc.count() > 0 and loc.is_visible():
                    loc.click(timeout=2000)
                    break
            except Exception:
                continue
        page.wait_for_timeout(800)
        shot(page, "09_details_tab_desktop_light")
        results["details_text_sample"] = page.inner_text("body")[:3000]

        # ---- METHODOLOGY (footer link) ----
        print("=== METHODOLOGY ===")
        for sel in ["#footer-methodology-link", "text=Methodology"]:
            try:
                loc = page.locator(sel).first
                if loc.count() > 0 and loc.is_visible():
                    loc.click(timeout=2000)
                    break
            except Exception:
                continue
        try:
            page.wait_for_selector("#tab-methodology-standalone .methodology-body", timeout=8000)
        except Exception as e:
            results["methodology_render_error"] = str(e)
        results["methodology_debug"] = page.evaluate("""() => {
            const view = document.getElementById('view-methodology');
            const tab = document.getElementById('tab-methodology-standalone');
            const body = document.querySelector('#tab-methodology-standalone .methodology-body');
            function d(el) {
                if (!el) return null;
                const cs = getComputedStyle(el);
                const r = el.getBoundingClientRect();
                return {display: cs.display, visibility: cs.visibility, height: r.height, width: r.width, top: r.top, classes: el.className};
            }
            return {view: d(view), tab: d(tab), body: d(body), scrollY: window.scrollY};
        }""")
        shot(page, "10_methodology_desktop_light")
        results["methodology_mentions_verified"] = "verified" in page.inner_text("body").lower()

        ctx.close()

        # ---- DARK MODE (desktop) ----
        print("=== DARK MODE ===")
        ctx_dark = browser.new_context(viewport={"width": 1440, "height": 900}, color_scheme="dark")
        page_dark = ctx_dark.new_page()
        page_dark.goto(BASE, wait_until="networkidle")
        page_dark.wait_for_timeout(500)
        shot(page_dark, "11_landing_desktop_dark")
        ctx_dark.close()

        # ---- TABLET ----
        print("=== TABLET (768) ===")
        ctx_tab = browser.new_context(viewport={"width": 768, "height": 1024})
        page_tab = ctx_tab.new_page()
        page_tab.goto(BASE, wait_until="networkidle")
        page_tab.wait_for_timeout(500)
        shot(page_tab, "12_landing_tablet")
        body_w = page_tab.evaluate("document.body.scrollWidth")
        viewport_w = page_tab.evaluate("window.innerWidth")
        results["tablet_horizontal_overflow"] = body_w > viewport_w + 2
        results["tablet_body_scrollwidth_vs_viewport"] = [body_w, viewport_w]
        ctx_tab.close()

        # ---- MOBILE ----
        print("=== MOBILE (390) ===")
        ctx_mob = browser.new_context(viewport={"width": 390, "height": 844})
        page_mob = ctx_mob.new_page()
        page_mob.goto(BASE, wait_until="networkidle")
        page_mob.wait_for_timeout(500)
        shot(page_mob, "13_landing_mobile")
        body_w_m = page_mob.evaluate("document.body.scrollWidth")
        viewport_w_m = page_mob.evaluate("window.innerWidth")
        results["mobile_horizontal_overflow"] = body_w_m > viewport_w_m + 2
        results["mobile_body_scrollwidth_vs_viewport"] = [body_w_m, viewport_w_m]
        ctx_mob.close()

        browser.close()

        results["console_errors"] = console_errors
        results["network_failures"] = network_failures
        results["page_errors"] = page_errors

        (OUT / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        print("\n=== SUMMARY ===")
        print(json.dumps({k: v for k, v in results.items() if k not in
                            ("landing_body_text_sample", "coach_header_text", "shot1_detail_text", "details_text_sample")},
                           indent=2))


if __name__ == "__main__":
    main()
