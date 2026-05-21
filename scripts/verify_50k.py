"""
End-to-end verification that a 50,000-page historical crawl loads in the UI
without freezing the browser or shipping the whole dataset at once.

Prerequisites:
  1. Seed the test fixture:   python scripts/seed_test_crawl.py
  2. Run the app:             python main.py --local
     (or any host/port — pass it via BASE_URL)
  3. Install browsers once:   playwright install chromium

Usage (from repo root):
    python scripts/verify_50k.py
    BASE_URL=http://127.0.0.1:5001 python scripts/verify_50k.py

Exit code 0 = all checks passed, non-zero = a check failed.
"""

import os
import sys
import time

from playwright.sync_api import sync_playwright

BASE_URL = os.environ.get('BASE_URL', 'http://localhost:5000').rstrip('/')

# Expected fixture shape (see scripts/seed_test_crawl.py)
EXPECT_URLS = 50_000
EXPECT_LINKS = 200_000

# A correctly windowed table keeps only a small buffer of rows in the DOM.
MAX_DOM_ROWS = 300
# Time budget for the table to show its first real rows after loading.
FIRST_PAINT_BUDGET_S = 10.0

failures = []


def check(label, ok, detail=''):
    mark = 'PASS' if ok else 'FAIL'
    print(f'  [{mark}] {label}' + (f' — {detail}' if detail else ''))
    if not ok:
        failures.append(label)


def data_row_count(page):
    """Number of real (non-placeholder, multi-cell) rows in the active table."""
    return page.evaluate("""() => {
        const active = document.querySelector('.tab-pane.active');
        const tbody = active && active.querySelector('tbody');
        if (!tbody) return 0;
        return [...tbody.querySelectorAll('tr')]
            .filter(r => r.querySelectorAll('td').length > 1).length;
    }""")


def main():
    print(f'Verifying LibreCrawl large-crawl loading at {BASE_URL}')

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        console_errors = []
        page.on('console', lambda m: console_errors.append(m.text)
                if m.type == 'error' else None)

        # --- Find the seeded crawl id -------------------------------------
        page.goto(BASE_URL, wait_until='networkidle')
        crawls = page.evaluate("""async () => {
            const r = await fetch('/api/crawls/list');
            return (await r.json()).crawls || [];
        }""")
        seed = next((c for c in crawls
                     if 'seed-50k' in (c.get('base_url', '') + c.get('base_domain', ''))),
                    None)
        if not seed:
            print('  [FAIL] seed crawl not found — run scripts/seed_test_crawl.py first')
            browser.close()
            sys.exit(1)
        crawl_id = seed['id']
        print(f'  Found seed crawl id={crawl_id}')

        # --- Load it and time the first paint -----------------------------
        t0 = time.time()
        load_resp = page.evaluate(f"""async () => {{
            const r = await fetch('/api/crawls/{crawl_id}/load', {{method: 'POST'}});
            return await r.json();
        }}""")
        check('POST /api/crawls/<id>/load succeeds', load_resp.get('success') is True)
        check('load response reports 50000 URLs',
              load_resp.get('urls_count') == EXPECT_URLS,
              f"got {load_resp.get('urls_count')}")

        # crawl_status must stay tiny — no full dataset in the payload
        status = page.evaluate("""async () => {
            const r = await fetch('/api/crawl_status');
            const t = await r.text();
            return {bytes: t.length, json: JSON.parse(t)};
        }""")
        check('/api/crawl_status payload stays small (<50KB)',
              status['bytes'] < 50_000, f"{status['bytes']} bytes")
        check('/api/crawl_status returns no inline rows',
              not status['json'].get('urls') and not status['json'].get('links'))

        # crawl_data must paginate
        page_resp = page.evaluate("""async () => {
            const r = await fetch('/api/crawl_data?kind=urls&offset=0&limit=1000');
            return await r.json();
        }""")
        check('/api/crawl_data paginates (1000-row page)',
              len(page_resp.get('rows', [])) == 1000 and page_resp.get('total') == EXPECT_URLS,
              f"rows={len(page_resp.get('rows', []))} total={page_resp.get('total')}")

        # Reload the page so the windowed UI renders the loaded crawl
        page.goto(BASE_URL, wait_until='networkidle')
        deadline = t0 + FIRST_PAINT_BUDGET_S
        while data_row_count(page) == 0 and time.time() < deadline:
            time.sleep(0.2)
        first_paint = time.time() - t0
        rows = data_row_count(page)
        check('overview table renders rows', rows > 0, f'{rows} rows')
        check(f'first paint within {FIRST_PAINT_BUDGET_S:.0f}s',
              first_paint < FIRST_PAINT_BUDGET_S, f'{first_paint:.1f}s')
        check(f'DOM holds a windowed buffer, not 50k rows (<={MAX_DOM_ROWS})',
              rows <= MAX_DOM_ROWS, f'{rows} rows in DOM')

        # --- Scroll to the bottom; placeholders must resolve --------------
        page.evaluate("""() => {
            const c = document.querySelector('.tab-pane.active .table-container');
            if (c) c.scrollTop = c.scrollHeight;
        }""")
        time.sleep(1.5)
        bottom_rows = data_row_count(page)
        check('rows render after scrolling to the bottom', bottom_rows > 0,
              f'{bottom_rows} rows')

        # --- Links tab (200k rows) ---------------------------------------
        page.get_by_role('button', name='Links').click()
        time.sleep(1.5)
        link_rows = data_row_count(page)
        check('Links tab (200k rows) renders windowed', 0 < link_rows <= MAX_DOM_ROWS,
              f'{link_rows} rows in DOM')

        # Ignore the harmless favicon 404 that every page load produces.
        real_errors = [e for e in console_errors if 'favicon' not in e.lower()]
        check('no uncaught console errors', not real_errors,
              '; '.join(real_errors[:3]))

        browser.close()

    print()
    if failures:
        print(f'FAILED — {len(failures)} check(s) failed: {", ".join(failures)}')
        sys.exit(1)
    print('All checks passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()
