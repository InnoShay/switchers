"""Playwright page screenshot (SPEC §12.7, RS-10). Any failure returns None -> screen fallback."""

from __future__ import annotations

from roomservice.log import get_logger

log = get_logger("pageshot")

VIEWPORT = {"width": 1440, "height": 900}
SCALE = 2
TIMEOUT_MS = 15_000


async def capture_page(url: str) -> bytes | None:
    """Headless chromium, 1440x900 @2x, wait for networkidle (15 s). None on any failure."""
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                ctx = await browser.new_context(viewport=VIEWPORT, device_scale_factor=SCALE)
                page = await ctx.new_page()
                await page.goto(url, wait_until="networkidle", timeout=TIMEOUT_MS)
                return await page.screenshot(type="png")
            finally:
                await browser.close()
    except Exception as e:
        log.warning("page screenshot failed for %s: %s", url, e)
        return None
