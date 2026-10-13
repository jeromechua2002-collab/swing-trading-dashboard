"""Actual Chromium UI smoke test for all 11 sector stock loads and core pages.

Served locally from generated data, using a same-origin iframe to reproduce the
Notion embedded experience. Do not mistake static-file unit tests for usable UI.
"""
import os
import time
from urllib.request import urlopen
from playwright.sync_api import sync_playwright

BASE = os.environ.get("DASHBOARD_TEST_URL", "http://127.0.0.1:8765/")
SECTORS = ("XLK","XLY","XLC","XLF","XLI","XLB","XLV","XLE","XLP","XLU","XLRE")

def wait_server():
    for _ in range(20):
        try:
            with urlopen(BASE+"data/rrg-core.json", timeout=2) as res:
                if res.status == 200: return
        except Exception:
            time.sleep(.4)
    raise RuntimeError("The dashboard HTTP server is not serving RRG data")

def run():
    wait_server()
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True, args=["--no-sandbox"])
        page=browser.new_page(viewport={"width":1280,"height":860})
        errors=[]
        page.on("pageerror",lambda err:errors.append(str(err)))
        page.route("**/*", lambda route: route.continue_() if route.request.url.startswith(BASE) else route.abort())
        page.goto(BASE+"stock-leadership.html",wait_until="domcontentloaded")
        page.locator("#rows tr").first.wait_for(timeout=18000)
        assert "NO VALID SIGNAL" not in page.locator("#status").inner_text(),page.locator("#status").inner_text()
        for sector in SECTORS:
            page.locator("#sector").select_option(sector)
            page.wait_for_function("document.querySelector('#coverage').textContent.includes('/')",timeout=20000)
            page.wait_for_function("document.querySelector('#status').textContent.includes('Completed-session')",timeout=20000)
            page.wait_for_function("(sector) => document.querySelector('#benchmark').textContent.startsWith(sector)",arg=sector,timeout=20000)
            rows=page.locator("#rows tr").count()
            assert rows>=8,(sector,rows,page.locator("#status").inner_text())
            page.locator("#filter").select_option("improving")
            assert page.locator("#rows tr").count()>=1
            page.locator("#filter").select_option("all")
        print("CHROMIUM STOCK RADAR: all 11 sector selectors render, recent dates and stock tables valid")
        for mode in ("sectors","industries"):
            page.goto(BASE+"rrg.html?mode="+mode,wait_until="domcontentloaded")
            page.wait_for_function("document.querySelector('#updated').textContent.includes('BAR AS-OF')",timeout=20000)
            assert page.locator("#symbols .symbol-row").count()>8,mode
            assert "Data build unavailable" not in page.locator("#updated").inner_text()
            print("CHROMIUM RRG",mode,page.locator("#updated").inner_text()[:180])
        for sector in ("XLV","XLE","XLK"):
            page.goto(BASE+"rrg.html?mode=stocks&sector="+sector,wait_until="domcontentloaded")
            page.wait_for_function("document.querySelector('#updated').textContent.includes('BAR AS-OF')",timeout=20000)
            assert page.locator("#symbols .symbol-row").count()>=10,sector
        page.goto(BASE+"index.html",wait_until="domcontentloaded")
        page.wait_for_function("document.querySelector('#releaseBadge').textContent !== 'Checking publication…'",timeout=16000)
        assert "Data needs attention" not in page.locator("#releaseBadge").inner_text(),page.locator("#marketStatus").inner_text()
        assert "No synchronized release" not in page.locator("#journalStatus").inner_text()
        page.goto(BASE+"trade-gate.html",wait_until="domcontentloaded")
        assert page.locator("#entry").count()==1
        for path in ("sector-breadth.html","equity.html","calendar.html","sectors.html","industries.html","rates.html"):
            r=page.goto(BASE+path,wait_until="domcontentloaded")
            assert r and r.status==200,path
            assert page.locator("body").inner_text().strip(),path
        # Embedded frame, same code path Notion typically uses.
        page.goto(BASE+"index.html",wait_until="domcontentloaded")
        page.evaluate("""() => {const iframe=document.createElement('iframe');iframe.id='notion-simulator';iframe.src='/stock-leadership.html';document.body.appendChild(iframe)}""")
        frame=page.frame_locator("#notion-simulator")
        frame.locator("#rows tr").first.wait_for(timeout=20000)
        assert "NO VALID SIGNAL" not in frame.locator("#status").inner_text()
        # Public journal views: percentages only, never currency or positions.
        page.goto(BASE+"equity.html",wait_until="domcontentloaded")
        page.wait_for_function("document.querySelector('#index').textContent !== '—'",timeout=15000)
        page.goto(BASE+"calendar.html",wait_until="domcontentloaded")
        page.wait_for_function("document.querySelector('#status').textContent.includes('closed trades')",timeout=15000)
        assert page.locator(".day .total").count()>=1
        assert not errors, "Unhandled script errors: "+repr(errors[:8])
        mobile=browser.new_page(viewport={"width":375,"height":812},is_mobile=True,has_touch=True)
        mobile.on("pageerror",lambda err:errors.append(str(err)))
        mobile.route("**/*", lambda route: route.continue_() if route.request.url.startswith(BASE) else route.abort())
        for path,ready in (("index.html","document.querySelector('#releaseBadge').textContent !== 'Checking publication…'"),
                           ("equity.html","document.querySelector('#index').textContent !== '—'"),
                           ("calendar.html","document.querySelector('#status').textContent.includes('closed trades')")):
            mobile.goto(BASE+path,wait_until="domcontentloaded")
            mobile.wait_for_function(ready,timeout=16000)
            assert "S$" not in mobile.locator("body").inner_text(),(path,"currency shown on a public journal view")
            if path=="index.html":
                assert "/" not in mobile.locator("#tradeCount").inner_text(),"open-position count shown on home page"
            if path!="index.html":
                assert mobile.evaluate("document.documentElement.scrollWidth<=innerWidth+1"),(path,"horizontal overflow at 375px")
        assert not errors, "Unhandled script errors: "+repr(errors[:8])
        print("CHROMIUM DASHBOARD SMOKE PASSED: 11 stock sectors, 2 ETF RRGs, 3 stock RRGs, sector breadth, journal, index, embedded iframe, percent-only journal views and 375px mobile journal pages")
        browser.close()

if __name__=="__main__":run()
