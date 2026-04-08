#!/usr/bin/env python3
"""Pause items in a Product Ads campaign via Playwright CDP.

Usage:
    python3 pause_items_in_campaign.py <campaign_id> <action> <item_id1> <item_id2> ...

action: 'pause' | 'activate' | 'remove'

Requires: Brave/Chrome with CDP on port 9222 and logged into ML Ads.
"""

import asyncio
import sys
from playwright.async_api import async_playwright

CDP_URL = "http://localhost:9222"

ACTION_LABEL = {
    "pause": "Pausar",
    "activate": "Activar",
    "remove": "Quitar de la campaña",
}


def dashboard_url(campaign_id):
    return f"https://ads.mercadolibre.com.ar/product-ads/admin/campaigns/{campaign_id}/dashboard?navigate_to=mercado_ads"


async def act_on_item(page, item_id, label, index, total):
    print(f"[{index+1}/{total}] {item_id} → {label}...", end=" ", flush=True)

    # Open the ad-actions menu for this item's row
    opened = await page.evaluate(f"""() => {{
        const target = '{item_id}';
        const rows = Array.from(document.querySelectorAll('tr,[role=row]'));
        for (const r of rows) {{
            if (r.innerText.includes(target)) {{
                const btn = r.querySelector('button[aria-label="ad-actions"]');
                if (btn) {{ btn.click(); return true; }}
            }}
        }}
        return false;
    }}""")
    if not opened:
        print("NO ENCONTRADO en la página")
        return False

    await page.wait_for_timeout(1500)

    # Click the actionable button whose label span text matches.
    # The clickable element is button.andes-list__item-actionable with
    # aria-labelledby pointing to a span containing the label text.
    clicked = await page.evaluate(f"""() => {{
        const label = '{label}';
        const items = document.querySelectorAll('button.andes-list__item-actionable');
        for (const btn of items) {{
            const ref = btn.getAttribute('aria-labelledby');
            if (ref) {{
                const span = document.getElementById(ref);
                if (span && span.innerText.trim() === label) {{ btn.click(); return true; }}
            }}
            if ((btn.innerText||'').trim() === label) {{ btn.click(); return true; }}
        }}
        return false;
    }}""")
    if not clicked:
        print(f"NO HAY OPCIÓN '{label}'")
        return False

    await page.wait_for_timeout(2500)
    print("OK")
    return True


async def main():
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)

    campaign_id = sys.argv[1]
    action = sys.argv[2]
    items = sys.argv[3:]

    if action not in ACTION_LABEL:
        print(f"Acción inválida: {action}. Usar: {list(ACTION_LABEL.keys())}")
        sys.exit(1)
    label = ACTION_LABEL[action]

    print(f"Campaña: {campaign_id}")
    print(f"Acción: {action} ({label})")
    print(f"Items: {len(items)}")
    print()

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP_URL)
        ctx = browser.contexts[0]
        page = next((pg for pg in ctx.pages if 'ads.mercadolibre' in pg.url), None) or await ctx.new_page()
        await page.goto(dashboard_url(campaign_id), wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(6000)

        ok = 0
        failed = []
        for i, item_id in enumerate(items):
            try:
                # Reload dashboard before each action: after a pause/activate
                # the table reorders and stale row references silently fail.
                if i > 0:
                    await page.goto(dashboard_url(campaign_id), wait_until="domcontentloaded", timeout=30000)
                    await page.wait_for_timeout(5000)
                if await act_on_item(page, item_id, label, i, len(items)):
                    ok += 1
                else:
                    failed.append(item_id)
            except Exception as e:
                print(f"ERROR: {e}")
                failed.append(item_id)
                await page.wait_for_timeout(1000)

        print(f"\n{'='*50}")
        print(f"RESULTADO: {ok} {action}d, {len(failed)} no procesados")
        if failed:
            print(f"No procesados: {', '.join(failed)}")


if __name__ == "__main__":
    asyncio.run(main())
