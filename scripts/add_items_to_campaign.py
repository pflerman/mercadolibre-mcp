#!/usr/bin/env python3
"""Add items to a Product Ads campaign via Playwright CDP.

Usage:
    python3 add_items_to_campaign.py <campaign_id> <item_id1> <item_id2> ...
    python3 add_items_to_campaign.py <campaign_id> --file items.txt

Campaign IDs:
    Pepe: 356608104
    saulo-de-tarso: 355566060

Requires: Brave/Chrome open with CDP on port 9222 and logged into ML Ads.
"""

import asyncio
import sys
from playwright.async_api import async_playwright

CDP_URL = "http://localhost:9222"


def get_add_url(campaign_id):
    # 2026-04: ML moved from /admin/campaigns/{id}/ads to /admin/sales/campaigns/{id}/ads
    return f"https://ads.mercadolibre.com.ar/product-ads/admin/sales/campaigns/{campaign_id}/ads?fe-rollout-version=v2&navigate_to=mercado_ads"


async def close_popups(page):
    """Close any promotional popups."""
    try:
        await page.evaluate("""() => {
            const selectors = [
                'button.ml-campaign-upselling-modal__close-button',
                'button[aria-label="Cerrar"]',
                'button[aria-label="Close"]',
            ];
            for (const sel of selectors) {
                const btn = document.querySelector(sel);
                if (btn) { btn.click(); return true; }
            }
            return false;
        }""")
    except:
        pass


async def add_single_item(page, item_id, index, total, add_url):
    """Navigate to add page, search item, select it, save."""
    print(f"[{index+1}/{total}] {item_id}...", end=" ", flush=True)

    await page.goto(add_url, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(3000)
    await close_popups(page)
    await page.wait_for_timeout(1000)

    # Find search input (placeholder actual: "Buscar por # o título")
    search = await page.query_selector('input[placeholder="Buscar por # o título"]')
    if not search:
        search = await page.query_selector("input[placeholder*='Buscar']")
    if not search:
        search = await page.query_selector("input[type='search']")
    if not search:
        print("ERROR: no hay input de busqueda")
        return False

    # Search by MLA ID
    await search.click()
    await search.fill(item_id)
    await search.press('Enter')
    await page.wait_for_timeout(2500)

    # Select checkbox. First try matching by MLA id in the row text;
    # if the search filtered to a single product but the row hides the MLA
    # (e.g. "family + N variantes" rendering), fall back to selecting the
    # only product checkbox in the result table — excluding the table-header
    # "select all" checkbox.
    selected = await page.evaluate(f"""() => {{
        const target = '{item_id}';
        const allCbs = Array.from(document.querySelectorAll('input[type="checkbox"]'));
        // Restrict to checkboxes inside data rows (not the header "select all")
        const rowCbs = allCbs.filter(cb => {{
            const row = cb.closest('tr,[role=row]');
            return row && !row.closest('thead');
        }});
        // 1. Try exact MLA match on row text
        for (const cb of rowCbs) {{
            const row = cb.closest('tr,[role=row]');
            if (row && row.textContent.includes(target)) {{
                if (!cb.checked) cb.click();
                return 'matched-mla';
            }}
        }}
        // 2. Fallback: if there's exactly one product row, select it
        //    (search filter narrowed the result down to one family)
        if (rowCbs.length === 1) {{
            if (!rowCbs[0].checked) rowCbs[0].click();
            return 'matched-single';
        }}
        return false;
    }}""")

    if not selected:
        print("NO ENCONTRADO")
        return False

    await page.wait_for_timeout(500)

    # Click Guardar (may navigate)
    try:
        await page.evaluate("""() => {
            const btns = Array.from(document.querySelectorAll('button'));
            const btn = btns.find(b => b.textContent.trim().includes('Guardar'));
            if (btn) { btn.click(); return true; }
            return false;
        }""")
    except:
        pass

    await page.wait_for_timeout(3000)

    # Handle activation modal if present
    try:
        await page.evaluate("""() => {
            const btns = Array.from(document.querySelectorAll('button'));
            const btn = btns.find(b => b.textContent.includes('activar anuncio') || b.textContent.includes('Si, activar'));
            if (btn) { btn.click(); return true; }
            return false;
        }""")
    except:
        pass

    await page.wait_for_timeout(1500)
    print("OK")
    return True


async def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    campaign_id = sys.argv[1]
    add_url = get_add_url(campaign_id)

    # Get item IDs from args or file
    if sys.argv[2] == "--file":
        with open(sys.argv[3]) as f:
            items = [line.strip() for line in f if line.strip()]
    else:
        items = sys.argv[2:]

    print(f"Campaña: {campaign_id}")
    print(f"Items a agregar: {len(items)}")
    print()

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP_URL)
        context = browser.contexts[0]

        # Find existing ads page or create new
        page = None
        for pg in context.pages:
            if 'ads.mercadolibre' in pg.url:
                page = pg
                break
        if not page:
            page = await context.new_page()

        total = len(items)
        ok = 0
        failed = []

        for i, item_id in enumerate(items):
            try:
                if await add_single_item(page, item_id, i, total, add_url):
                    ok += 1
                else:
                    failed.append(item_id)
            except Exception as e:
                print(f"ERROR: {e}")
                failed.append(item_id)
                await page.wait_for_timeout(2000)

        print(f"\n{'='*50}")
        print(f"RESULTADO: {ok} agregados, {len(failed)} no encontrados")
        if failed:
            print(f"No encontrados: {', '.join(failed)}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
