"""Utility module for rendering HTML/CSS templates into images using Playwright."""

import asyncio
import contextlib
import io
import logging
import os
from jinja2 import Environment, FileSystemLoader
from playwright.async_api import async_playwright
from db.tournaments import get_bracket_render_data

logger = logging.getLogger('iu-bot')

TEMPLATE_DIR = os.path.dirname(os.path.abspath(__file__))

# How long Chromium may sit unused before it is shut down (it holds a few hundred MB of memory)
BROWSER_IDLE_SECONDS = 300

class _BrowserCache:
    """Launches Chromium on demand, shares it between overlapping renders, and closes it when idle.

    A fresh headless Chromium launch costs 1-3 seconds, but renders come in bursts (creation,
    a round advance, the finale) and then nothing for days. So the browser is kept for
    BROWSER_IDLE_SECONDS after the last render and shut down after that.
    """

    def __init__(self):
        self._playwright = None
        self._browser = None
        self._lock = asyncio.Lock()
        self._in_use = 0
        self._idle_timer = None
        self._close_task = None

    @contextlib.asynccontextmanager
    async def browser(self):
        """Yields the shared Chromium instance (launching, or relaunching after a crash, as needed)."""
        async with self._lock:
            if self._idle_timer:
                self._idle_timer.cancel()
                self._idle_timer = None
            if self._browser is None or not self._browser.is_connected():
                await self._shutdown()
                self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(
                    headless=True,
                    args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
                )
                logger.info("Launched Chromium for bracket rendering.")
            self._in_use += 1
            browser = self._browser
        try:
            yield browser
        finally:
            self._in_use -= 1
            if self._in_use == 0:
                self._idle_timer = asyncio.get_running_loop().call_later(
                    BROWSER_IDLE_SECONDS, self._start_close)

    def _start_close(self):
        # Keep a reference so the task isn't garbage collected before it finishes
        self._close_task = asyncio.create_task(self._close_if_idle())

    async def _close_if_idle(self):
        async with self._lock:
            if self._in_use == 0 and self._browser is not None:
                await self._shutdown()
                logger.info("Closed idle Chromium.")

    async def _shutdown(self):
        """Stops the browser and Playwright's driver process, ignoring errors from one that already died."""
        browser, playwright = self._browser, self._playwright
        self._browser = self._playwright = None
        for closer in (browser and browser.close, playwright and playwright.stop):
            if closer:
                try:
                    await closer()
                except Exception:
                    logger.debug("Error while shutting down Chromium", exc_info=True)

    def invalidate(self):
        """Forces a relaunch on the next render, e.g. after the browser crashed mid-render."""
        self._browser = None

_browser_cache = _BrowserCache()

async def generate_bracket_image(tournament_id: str) -> io.BytesIO | None:
    """
    Fetches DB state, compiles the Jinja template, and renders the screenshot dynamically
    for any power-of-2 tournament size.
    """
    context = get_bracket_render_data(tournament_id)
    if not context:
        logger.error("Could not generate image: No data found for tournament %s", tournament_id)
        return None

    try:
        total_rounds = context["total_rounds"]

        # Dynamically build the viewport
        # Total columns = (left side + right side + 1 center)
        num_columns = ((total_rounds - 1) * 2) + 1
        num_gaps = num_columns - 1

        # Width: 220px per side col, 280px for center, 50px per gap, 120px base padding
        viewport_width = ((num_columns - 1) * 220) + 280 + (num_gaps * 50) + 120

        # Height: Scales based on the number of matches stacking in Round 1
        r1_matches_per_side = 2 ** (total_rounds - 2)
        # 90px per match box + roughly 60px of flex spacing per box + 200px header
        viewport_height = max(950, (r1_matches_per_side * 150) + 200)

        # Compile the Jinja2 template
        # autoescape: entrant names are typed by admins and end up in a page Chromium executes
        env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=True)
        template = env.get_template('bracket_template.html.j2')
        rendered_html = template.render(context)

        # Render in playwright
        image_buffer = await render_html_to_image(
            rendered_html,
            width=viewport_width,
            height=viewport_height
        )

        return image_buffer

    except Exception as ex:
        logger.error("Failed to compile or render bracket image: %s", ex)
        return None

async def render_html_to_image(html_content: str, width: int = 2100, height: int = 950) -> io.BytesIO | None:
    """
    Renders the provided HTML in the shared headless browser and takes a screenshot.

    Args:
        html_content: The raw HTML string (with embedded CSS) to render.
        width: The viewport width in pixels.
        height: The viewport height in pixels.

    Returns:
        An io.BytesIO object containing the raw PNG image data, or None if it fails.
    """
    try:
        async with _browser_cache.browser() as browser:
            page = await browser.new_page(viewport={"width": width, "height": height})
            try:
                # Load the HTML content directly into the browser
                # wait_until="networkidle" ensures external fonts/images finish loading before the screenshot
                await page.set_content(html_content, wait_until="networkidle")

                # Take the screenshot as a byte array
                screenshot_bytes = await page.screenshot(type="png")
            finally:
                await page.close()

        # Wrap it in BytesIO so Discord can consume it directly as a discord.File
        image_buffer = io.BytesIO(screenshot_bytes)
        image_buffer.seek(0)

        return image_buffer

    except Exception as ex:
        logger.error("Failed to render HTML to image: %s", ex)
        # The shared browser may have crashed or disconnected -- force a relaunch next time.
        _browser_cache.invalidate()
        return None
