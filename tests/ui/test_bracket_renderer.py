"""Tests for ui/bracket_renderer.py

Chromium is never launched: a fake Playwright stands in for it.
"""

import asyncio
import contextlib
import io
import logging
from unittest import mock

import pytest

from config import Database
from db.tournaments import advance_winner, create_tournament
from ui import bracket_renderer
from ui.bracket_renderer import _BrowserCache, generate_bracket_image, render_html_to_image


class FakePage:
    """A page that 'renders' by remembering what it was given."""

    def __init__(self, screenshot=b"PNGDATA", fail_on=None):
        self.set_content = mock.AsyncMock()
        self.screenshot = mock.AsyncMock(return_value=screenshot)
        self.close = mock.AsyncMock()
        if fail_on:
            getattr(self, fail_on).side_effect = RuntimeError("render failed")


class FakeBrowser:
    """A browser that hands out FakePages."""

    def __init__(self, page=None):
        self.page = page or FakePage()
        self.new_page = mock.AsyncMock(return_value=self.page)
        self.close = mock.AsyncMock()
        self.connected = True

    def is_connected(self):
        return self.connected


class FakePlaywright:
    """Stands in for `async_playwright()`: start() gives a driver whose chromium.launch gives a FakeBrowser."""

    def __init__(self):
        self.browsers = []
        self.launch_calls = []
        self.stop = mock.AsyncMock()
        self.chromium = mock.Mock()
        self.chromium.launch = mock.AsyncMock(side_effect=self._launch)
        self.start_calls = 0

    async def _launch(self, **kwargs):
        self.launch_calls.append(kwargs)
        browser = FakeBrowser()
        self.browsers.append(browser)
        return browser

    def factory(self):
        """What replaces `async_playwright`: calling it returns an object with an awaitable start()."""
        outer = self

        async def start():
            outer.start_calls += 1
            return outer

        return mock.Mock(start=start)


@pytest.fixture(name="playwright")
def _playwright(monkeypatch):
    fake = FakePlaywright()
    monkeypatch.setattr("ui.bracket_renderer.async_playwright", fake.factory)
    return fake


class TestBrowserCache:
    """Chromium starts when needed, is shared between overlapping renders, and closes when idle."""

    async def test_launches_a_headless_browser_the_first_time(self, playwright):
        cache = _BrowserCache()

        async with cache.browser() as browser:
            assert browser is playwright.browsers[0]

        kwargs = playwright.launch_calls[0]
        assert kwargs["headless"] is True
        assert "--no-sandbox" in kwargs["args"]

    async def test_reuses_the_browser_for_back_to_back_renders(self, playwright):
        cache = _BrowserCache()

        async with cache.browser() as first:
            pass
        async with cache.browser() as second:
            pass

        assert first is second
        assert len(playwright.browsers) == 1

    async def test_overlapping_renders_share_one_browser(self, playwright):
        cache = _BrowserCache()

        async def use():
            async with cache.browser() as browser:
                await asyncio.sleep(0.01)
                return browser

        first, second = await asyncio.gather(use(), use())

        assert first is second
        assert len(playwright.browsers) == 1

    async def test_a_crashed_browser_is_replaced(self, playwright):
        cache = _BrowserCache()
        async with cache.browser() as first:
            pass
        first.connected = False

        async with cache.browser() as second:
            pass

        assert second is not first
        assert len(playwright.browsers) == 2
        first.close.assert_awaited()          # the dead one is cleaned up

    @pytest.mark.usefixtures("playwright")
    async def test_invalidate_forces_a_relaunch(self):
        cache = _BrowserCache()
        async with cache.browser() as first:
            pass

        cache.invalidate()

        async with cache.browser() as second:
            pass
        assert second is not first

    async def test_closes_after_the_idle_time(self, playwright, monkeypatch):
        monkeypatch.setattr(bracket_renderer, "BROWSER_IDLE_SECONDS", 0.05)
        cache = _BrowserCache()
        async with cache.browser() as browser:
            pass

        await asyncio.sleep(0.25)

        browser.close.assert_awaited_once()
        playwright.stop.assert_awaited_once()

    @pytest.mark.usefixtures("playwright")
    async def test_stays_open_while_a_render_is_using_it(self, monkeypatch):
        monkeypatch.setattr(bracket_renderer, "BROWSER_IDLE_SECONDS", 0.05)
        cache = _BrowserCache()

        async with cache.browser() as browser:
            await asyncio.sleep(0.25)
            browser.close.assert_not_awaited()

    @pytest.mark.usefixtures("playwright")
    async def test_a_new_render_cancels_the_pending_close(self, monkeypatch):
        monkeypatch.setattr(bracket_renderer, "BROWSER_IDLE_SECONDS", 0.2)
        cache = _BrowserCache()
        async with cache.browser() as browser:
            pass
        await asyncio.sleep(0.1)

        async with cache.browser():
            await asyncio.sleep(0.25)          # well past the first timer, but the second render is still going
            browser.close.assert_not_awaited()

    async def test_relaunches_after_an_idle_close(self, playwright, monkeypatch):
        monkeypatch.setattr(bracket_renderer, "BROWSER_IDLE_SECONDS", 0.05)
        cache = _BrowserCache()
        async with cache.browser() as first:
            pass
        await asyncio.sleep(0.25)

        async with cache.browser() as second:
            pass

        assert second is not first
        assert len(playwright.browsers) == 2

    async def test_errors_while_cleaning_up_a_dead_browser_do_not_stop_a_relaunch(self, playwright, caplog):
        cache = _BrowserCache()
        async with cache.browser() as first:
            pass
        first.connected = False
        first.close.side_effect = RuntimeError("already dead")
        playwright.stop.side_effect = RuntimeError("driver gone")

        with caplog.at_level(logging.DEBUG, logger="iu-bot"):
            async with cache.browser() as second:
                pass

        assert second is not first
        assert "Error while shutting down Chromium" in caplog.text


class TestRenderHtmlToImage:
    """Turning HTML into a PNG."""

    @pytest.fixture(name="browser", autouse=True)
    def _fake_browser(self, monkeypatch):
        fake = FakeBrowser()

        @contextlib.asynccontextmanager
        async def shared_browser():
            yield fake

        monkeypatch.setattr("ui.bracket_renderer._browser_cache.browser", shared_browser)
        return fake

    @pytest.fixture(name="invalidate", autouse=True)
    def _fake_invalidate(self, monkeypatch):
        fake = mock.Mock()
        monkeypatch.setattr("ui.bracket_renderer._browser_cache.invalidate", fake)
        return fake

    async def test_returns_the_screenshot_ready_to_send(self):
        image = await render_html_to_image("<h1>Hi</h1>", width=800, height=600)

        assert isinstance(image, io.BytesIO)
        assert image.tell() == 0
        assert image.read() == b"PNGDATA"

    async def test_renders_at_the_requested_size_and_waits_for_the_page_to_settle(self, browser):
        await render_html_to_image("<h1>Hi</h1>", width=800, height=600)

        browser.new_page.assert_awaited_once_with(viewport={"width": 800, "height": 600})
        browser.page.set_content.assert_awaited_once_with("<h1>Hi</h1>", wait_until="networkidle")
        browser.page.screenshot.assert_awaited_once_with(type="png")

    async def test_the_default_size_suits_a_large_bracket(self, browser):
        await render_html_to_image("<p>")

        browser.new_page.assert_awaited_once_with(viewport={"width": 2100, "height": 950})

    async def test_the_page_is_closed_afterwards(self, browser):
        await render_html_to_image("<p>")

        browser.page.close.assert_awaited_once()

    async def test_a_failed_render_returns_none_and_forces_a_relaunch(self, browser, invalidate, caplog):
        browser.page.screenshot.side_effect = RuntimeError("crashed")

        with caplog.at_level(logging.ERROR, logger="iu-bot"):
            image = await render_html_to_image("<p>")

        assert image is None
        browser.page.close.assert_awaited_once()
        invalidate.assert_called_once()
        assert "Failed to render HTML to image" in caplog.text


class TestGenerateBracketImage:
    """Building the bracket picture for a tournament."""

    @pytest.fixture(autouse=True)
    def _tournaments(self, databases):
        databases(Database.TOURNAMENTS)

    @staticmethod
    def _make(entrant_count, name="Best Ballad"):
        return create_tournament(name, "d", [f"Song {i}" for i in range(1, entrant_count + 1)], 2)

    async def test_an_unknown_tournament_gives_no_image(self, fake_bracket_render, caplog):
        with caplog.at_level(logging.ERROR, logger="iu-bot"):
            assert await generate_bracket_image("nope") is None

        fake_bracket_render.assert_not_awaited()
        assert "No data found for tournament nope" in caplog.text

    async def test_renders_a_page_showing_the_title_and_entrants(self, fake_bracket_render):
        image = await generate_bracket_image(self._make(4))

        assert image.read().startswith(b"\x89PNG")
        html = fake_bracket_render.await_args.args[0]
        assert "Best Ballad" in html
        for entrant in ("Song 1", "Song 2", "Song 3", "Song 4"):
            assert entrant in html

    @pytest.mark.parametrize("entrants, width, height", [
        (2, 400, 950),        # 1 round: a single column
        (4, 940, 950),
        (8, 1480, 950),
        (16, 2020, 950),
        (32, 2560, 1400),     # 8 first-round matches stack on each side
        (64, 3100, 2600),     # 16 on each side
    ])
    async def test_the_picture_is_sized_to_the_bracket(self, fake_bracket_render, entrants, width, height):
        await generate_bracket_image(self._make(entrants))

        kwargs = fake_bracket_render.await_args.kwargs
        assert (kwargs["width"], kwargs["height"]) == (width, height)

    async def test_entrant_names_are_escaped_before_reaching_the_browser(self, fake_bracket_render):
        tournament_id = create_tournament("<script>alert(1)</script>", "d",
                                          ["<img src=x onerror=alert(1)>", "B", "C", "D"], 2)

        await generate_bracket_image(tournament_id)

        html = fake_bracket_render.await_args.args[0]
        assert "<script>alert(1)</script>" not in html
        assert "<img src=x" not in html
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html

    async def test_the_winner_is_shown_when_the_final_is_decided(self, fake_bracket_render, query):
        tournament_id = create_tournament("Two", "d", ["Alpha", "Beta"], 2)
        match = query(Database.TOURNAMENTS, "SELECT * FROM tournament_matches")[0]
        advance_winner(match["match_id"], tournament_id, 1, 1, match["entrant_b_id"])

        await generate_bracket_image(tournament_id)

        assert "Beta" in fake_bracket_render.await_args.args[0]

    async def test_a_rendering_failure_gives_no_image(self, monkeypatch, caplog):
        monkeypatch.setattr("ui.bracket_renderer.render_html_to_image",
                            mock.AsyncMock(side_effect=RuntimeError("boom")))

        with caplog.at_level(logging.ERROR, logger="iu-bot"):
            assert await generate_bracket_image(self._make(4)) is None

        assert "Failed to compile or render bracket image" in caplog.text
