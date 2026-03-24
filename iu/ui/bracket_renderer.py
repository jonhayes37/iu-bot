"""Utility module for rendering HTML/CSS templates into images using Playwright."""

import io
import logging
import os
from jinja2 import Environment, FileSystemLoader
from playwright.async_api import async_playwright
from db.tournaments import get_bracket_render_data

logger = logging.getLogger('iu-bot')

TEMPLATE_DIR = os.path.dirname(os.path.abspath(__file__))

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
        env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
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
    Spins up a headless browser, renders the provided HTML, and takes a screenshot.
    
    Args:
        html_content: The raw HTML string (with embedded CSS) to render.
        width: The viewport width in pixels.
        height: The viewport height in pixels.
        
    Returns:
        An io.BytesIO object containing the raw PNG image data, or None if it fails.
    """
    try:
        async with async_playwright() as p:
            # Launch Chromium. The arguments are strictly required to run inside a Docker container.
            browser = await p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
            )

            page = await browser.new_page(viewport={"width": width, "height": height})

            # Load the HTML content directly into the browser
            # wait_until="networkidle" ensures external fonts/images finish loading before the screenshot
            await page.set_content(html_content, wait_until="networkidle")

            # Take the screenshot as a byte array
            screenshot_bytes = await page.screenshot(type="png")
            await browser.close()

            # Wrap it in BytesIO so Discord can consume it directly as a discord.File
            image_buffer = io.BytesIO(screenshot_bytes)
            image_buffer.seek(0)

            return image_buffer

    except Exception as ex:
        logger.error("Failed to render HTML to image: %s", ex)
        return None
