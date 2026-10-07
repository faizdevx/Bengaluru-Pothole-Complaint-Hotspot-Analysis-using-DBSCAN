"""Browser smoke test: loads every page against a running server, fails on JS errors
or error/empty states, and saves screenshots. Usage: python scripts/smoke_ui.py [base_url] [out_dir]"""
import sys
from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
OUT = sys.argv[2] if len(sys.argv) > 2 else "docs/screenshots"
PAGES = ["", "map", "hotspots", "timeline", "clusters?id=47", "spatial", "parameters", "quality", "about"]
errors, report = [], []
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium", args=["--no-sandbox"]) if __import__("os").path.exists("/opt/pw-browsers/chromium") else p.chromium.launch()
    for name in PAGES:
        pg = b.new_page(viewport={"width": 1360, "height": 900})
        msgs = []
        pg.on("pageerror", lambda e, m=msgs: m.append("pageerror: " + str(e)))
        pg.on("console", lambda c, m=msgs: m.append("console.error: " + c.text) if c.type == "error" and "tile.openstreetmap" not in c.text and "ERR_" not in c.text and "Failed to load resource" not in c.text else None)
        pg.goto(f"{BASE}/{name}", wait_until="networkidle")
        if name == "map":
            pg.wait_for_function("window.__mapReady === true", timeout=15000)
            pg.evaluate("document.querySelector('#l-grid').click(); document.querySelector('#l-noise').click(); document.querySelector('#l-tiles').click()")
        pg.wait_for_timeout(600)
        state = pg.locator("#state")
        st = state.inner_text() if state.count() and state.is_visible() else ""
        prov = pg.locator("#prov-retrieved").inner_text()
        body = pg.locator("main").inner_text()
        slug = name.split("?")[0] or "dashboard"
        pg.screenshot(path=f"{OUT}/{slug}.png", full_page=slug != "map")
        bad = bool(msgs) or ("Could not load" in st) or ("No analysis" in st) or "loading" in prov or "LIVE" in body
        report.append((slug, "FAIL" if bad else "ok", st, prov, msgs))
        pg.close()
    b.close()
for r in report:
    print(r)
sys.exit(1 if any(r[1] != "ok" for r in report) else 0)
