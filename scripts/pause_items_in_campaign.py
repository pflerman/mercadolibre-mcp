#!/usr/bin/env python3
"""Pause / activate / remove items in a Product Ads campaign via Playwright CDP.

Usage:
    python3 pause_items_in_campaign.py <campaign_id> <action> <target1> <target2> ...

action: 'pause' | 'activate' | 'remove'

Each <targetN> can be:
  - an MLA id (e.g. MLA1718952491) → matched against row text
  - any substring of the item title (e.g. "Andromeda") → matched against
    row text. Useful for catalog/family items where the row hides the MLA.

The dashboard is reloaded between items because pausing/removing reorders
the table and stale row references silently fail. Removal triggers a
confirmation modal whose primary button is labeled "Eliminar".

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

# Confirmation modal button text per action (None = no confirm needed)
CONFIRM_BUTTON = {
    "pause": None,
    "activate": None,
    "remove": "Eliminar",
}


def dashboard_url(campaign_id):
    return f"https://ads.mercadolibre.com.ar/product-ads/admin/campaigns/{campaign_id}/dashboard?navigate_to=mercado_ads"


async def act_on_item(page, target, action, label, confirm_btn, index, total):
    print(f"[{index+1}/{total}] {target} → {label}...", end=" ", flush=True)

    # Open the ad-actions menu for the first row containing the target text
    opened = await page.evaluate(f"""() => {{
        const target = {repr(target)};
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
        print("NO ENCONTRADO")
        return False

    await page.wait_for_timeout(1500)

    # Click the actionable menu option whose label span text matches.
    # The clickable element is button.andes-list__item-actionable with
    # aria-labelledby pointing to a span containing the label text.
    clicked = await page.evaluate(f"""() => {{
        const label = {repr(label)};
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
        print(f"sin opción '{label}'")
        return False

    await page.wait_for_timeout(2000)

    # Confirmation modal (only for 'remove' currently)
    if confirm_btn:
        confirmed = await page.evaluate(f"""() => {{
            const text = {repr(confirm_btn)};
            const dlgs = document.querySelectorAll('[role=dialog]');
            for (const d of dlgs) {{
                const btns = d.querySelectorAll('button');
                for (const b of btns) {{
                    if ((b.innerText||'').trim() === text) {{ b.click(); return true; }}
                }}
            }}
            return false;
        }}""")
        if not confirmed:
            print(f"sin confirm '{confirm_btn}'")
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
    targets = sys.argv[3:]

    if action not in ACTION_LABEL:
        print(f"Acción inválida: {action}. Usar: {list(ACTION_LABEL.keys())}")
        sys.exit(1)
    label = ACTION_LABEL[action]
    confirm_btn = CONFIRM_BUTTON[action]

    print(f"Campaña: {campaign_id}")
    print(f"Acción: {action} ({label})")
    print(f"Targets: {len(targets)}")
    print()

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP_URL)
        ctx = browser.contexts[0]
        page = next((pg for pg in ctx.pages if 'ads.mercadolibre' in pg.url), None) or await ctx.new_page()

        ok = 0
        failed = []
        for i, target in enumerate(targets):
            try:
                # Always reload before each action: pausing/removing reorders
                # the table and stale row references silently fail.
                await page.goto(dashboard_url(campaign_id), wait_until="load", timeout=45000)
                await page.wait_for_timeout(6000)
                if await act_on_item(page, target, action, label, confirm_btn, i, len(targets)):
                    ok += 1
                else:
                    failed.append(target)
            except Exception as e:
                print(f"ERROR: {e}")
                failed.append(target)
                await page.wait_for_timeout(1000)

        print(f"\n{'='*50}")
        print(f"RESULTADO: {ok}/{len(targets)} {action}")
        if failed:
            print(f"No procesados: {', '.join(failed)}")


if __name__ == "__main__":
    asyncio.run(main())
