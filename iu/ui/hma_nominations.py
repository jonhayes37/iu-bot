"""
HMA nominations: a private menu of pages (each family split into forms of up to 5 categories), where a
member types any number of nominees per category, one per line, and can come back to edit them.
"""

import re
from dataclasses import dataclass

import discord
from db.hmas import get_active_hma_categories, get_user_nominations, replace_user_nominations
from services.youtube import contains_youtube_url
from ui.base import SafeModal, report_interaction_error, reports_errors
from ui.end_of_year import refuse_if_closed

# A Discord form holds at most 5 boxes
CATEGORIES_PER_PAGE = 5
# What a form box's title can show
MAX_BOX_TITLE_LENGTH = 45
# Room for a few dozen nominees per category
MAX_BOX_LENGTH = 1000
# Long enough for a song title, artist and a YouTube link
MAX_NOMINEE_LENGTH = 300
# These categories are judged on the video, so every nominee needs its link
COVER_CATEGORIES = frozenset({'best_dance_cover', 'best_vocal_cover'})
# How many unsaved lines the menu lists before summarising the rest (a message holds 2000 characters)
MAX_PROBLEMS_SHOWN = 8

# "1. IVE - HEYA", "2) ...", "- ...", "• ..." -> "IVE - HEYA". A digit must be followed by . or ) and a space,
# so names like "2NE1" or "10CM" are left alone.
LINE_MARKER = re.compile(r"^(?:\d+[.)]\s+|[-•*]\s*)")


@dataclass(frozen=True)
class NominationPage:
    """One form: up to 5 categories of one family. `number` counts from 1 across all the pages."""
    number: int
    family: str
    part: int
    parts: int
    categories: tuple[tuple[str, str], ...]        # (category_id, name)

    @property
    def label(self) -> str:
        return self.family if self.parts == 1 else f"{self.family} {self.part}/{self.parts}"

    @property
    def category_ids(self) -> list[str]:
        return [category_id for category_id, _ in self.categories]


def nomination_pages(categories: list[dict]) -> list[NominationPage]:
    """
    Splits the active categories (in family order, then by name) into pages: each family starts a new
    page, and its pages are filled to 5 before the next begins (17 Bonsangs make pages of 5, 5, 5 and 2).
    """
    families: dict[str, list[tuple[str, str]]] = {}
    for category in categories:
        families.setdefault(category['family'], []).append((category['category_id'], category['name']))

    pages = []
    for family, members in families.items():
        chunks = [members[i:i + CATEGORIES_PER_PAGE] for i in range(0, len(members), CATEGORIES_PER_PAGE)]
        for part, chunk in enumerate(chunks, start=1):
            pages.append(NominationPage(len(pages) + 1, family, part, len(chunks), tuple(chunk)))
    return pages


def parse_nominees(text: str) -> list[str]:
    """One nominee per line: blank lines and repeats (ignoring case) are dropped, and list markers removed."""
    nominees, seen = [], set()
    for line in text.splitlines():
        nominee = LINE_MARKER.sub("", line.strip()).strip()
        if nominee and nominee.casefold() not in seen:
            seen.add(nominee.casefold())
            nominees.append(nominee)
    return nominees


def _page_count(page: NominationPage, nominations: dict[str, list[str]]) -> int:
    return sum(len(nominations.get(category_id, [])) for category_id in page.category_ids)


def _plural(count: int, word: str, plural: str | None = None) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {plural or word + 's'}"


def menu_text(year: int, pages: list[NominationPage], nominations: dict[str, list[str]],
              note: str | None = None) -> str:
    """The private menu: what was just saved (if anything), then each page and how far along it is."""
    lines = [note, ""] if note else []
    lines += [f"🏆 **{year} HMA Nominations**",
              "Open a page, type your nominees (one per line) and save. Skip any category you like, "
              "and come back any time before the deadline to change things.", ""]
    for page in pages:
        count = _page_count(page, nominations)
        if count:
            lines.append(f"✅ **{page.label}**: {_plural(count, 'nomination')}")
        else:
            lines.append(f"⏰ **{page.label}**: {' · '.join(name for _, name in page.categories)}")
    return "\n".join(lines)


def _next_page(pages: list[NominationPage], nominations: dict[str, list[str]], after: int = 0) -> int | None:
    """The first page with no nominations after page `after`, else the first anywhere (None when all have some)."""
    empty = [page.number for page in pages if not _page_count(page, nominations)]
    return next((number for number in empty if number > after), empty[0] if empty else None)


class NominationPageButton(discord.ui.DynamicItem[discord.ui.Button],
                           template=r"hma_nom_page:(?P<year>\d+):(?P<page>\d+)"):
    """Opens one page's form. The year and page are in the ID, so the menu works after a restart."""

    def __init__(self, year: int, page: int, label: str = "Page", style=discord.ButtonStyle.secondary,
                 done: bool = False, row: int | None = None):
        super().__init__(discord.ui.Button(
            label=label, style=style, emoji="✅" if done else None, row=row,
            custom_id=f"hma_nom_page:{year}:{page}"))
        self.year = year
        self.page = page

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Item, match, /):
        return cls(int(match["year"]), int(match["page"]))

    @reports_errors
    async def callback(self, interaction: discord.Interaction):
        if await refuse_if_closed(interaction, self.year):
            return

        pages = nomination_pages(get_active_hma_categories())
        if not 1 <= self.page <= len(pages):
            await interaction.response.send_message(
                "The categories have changed since this menu was opened. Press **HMA Nominations** again "
                "for the new pages.", ephemeral=True)
            return
        page = pages[self.page - 1]
        nominations = get_user_nominations(self.year, interaction.user.id)
        await interaction.response.send_modal(NominationPageModal(self.year, page, len(pages), nominations))


class NominationMenuView(discord.ui.View):
    """
    The menu's buttons: a row per family and a button per page. Pages with nominations get a tick, and
    the next page to fill in is green.
    """

    def __init__(self, year: int, pages: list[NominationPage], nominations: dict[str, list[str]],
                 next_page: int | None):
        super().__init__(timeout=None)
        families = list(dict.fromkeys(page.family for page in pages))
        for page in pages:
            style = discord.ButtonStyle.success if page.number == next_page else discord.ButtonStyle.secondary
            self.add_item(NominationPageButton(
                year, page.number, page.label, style, done=bool(_page_count(page, nominations)),
                row=min(families.index(page.family), 4)))


def nomination_menu(year: int, user_id: int, note: str | None = None,
                    after: int = 0) -> tuple[str, NominationMenuView | None]:
    """The menu's text and buttons for a member, with the next empty page after `after` highlighted."""
    pages = nomination_pages(get_active_hma_categories())
    if not pages:
        return "There are no HMA categories yet, so there's nothing to nominate for.", None
    nominations = get_user_nominations(year, user_id)
    view = NominationMenuView(year, pages, nominations, _next_page(pages, nominations, after))
    return menu_text(year, pages, nominations, note), view


class NominationPageModal(SafeModal):
    """One page's form: a box per category, filled in with what the member saved before."""

    def __init__(self, year: int, page: NominationPage, total_pages: int, nominations: dict[str, list[str]]):
        super().__init__(title=f"{page.label} nominations ({page.number} of {total_pages})")
        self.year = year
        self.page = page
        self.boxes: dict[str, discord.ui.TextInput] = {}
        for category_id, name in page.categories:
            box = discord.ui.TextInput(
                style=discord.TextStyle.paragraph, required=False, max_length=MAX_BOX_LENGTH,
                default="\n".join(nominations.get(category_id, [])) or None)
            hint = ("One per line, each with its YouTube link. Leave blank to skip." if category_id in COVER_CATEGORIES
                    else "One nominee per line. Leave blank to skip.")
            self.add_item(discord.ui.Label(text=name[:MAX_BOX_TITLE_LENGTH], description=hint, component=box))
            self.boxes[category_id] = box

    # pylint: disable=arguments-differ
    async def on_submit(self, interaction: discord.Interaction):
        if await refuse_if_closed(interaction, self.year):
            return

        names = dict(self.page.categories)
        to_save: dict[str, list[str]] = {}
        problems = []
        for category_id, box in self.boxes.items():
            kept = []
            for nominee in parse_nominees(box.value):
                if len(nominee) > MAX_NOMINEE_LENGTH:
                    problems.append(f"{names[category_id]}: too long ({len(nominee)} characters, "
                                    f"at most {MAX_NOMINEE_LENGTH}): {nominee[:60]}…")
                elif category_id in COVER_CATEGORIES and not contains_youtube_url(nominee):
                    problems.append(f"{names[category_id]} needs a YouTube link: {nominee[:100]}")
                else:
                    kept.append(nominee)
            to_save[category_id] = kept
        replace_user_nominations(self.year, interaction.user.id, to_save)

        saved = sum(len(nominees) for nominees in to_save.values())
        filled = sum(1 for nominees in to_save.values() if nominees)
        note = (f"✅ Saved **{self.page.label}**: {_plural(saved, 'nomination')} in "
                f"{_plural(filled, 'category', 'categories')}.")
        if problems:
            shown = problems[:MAX_PROBLEMS_SHOWN]
            if len(problems) > len(shown):
                shown.append(f"…and {len(problems) - len(shown)} more")
            note += "\n⚠️ Not saved (fix these and save the page again):\n" + "\n".join(f"• {p}" for p in shown)

        content, view = nomination_menu(self.year, interaction.user.id, note, after=self.page.number)
        await interaction.response.edit_message(content=content, view=view)

    # pylint: disable=arguments-differ
    async def on_error(self, interaction: discord.Interaction, error: Exception):
        # Hand the boxes back so a failed save never costs the member what they typed
        await report_interaction_error(interaction, error, keep_text={
            f"{category_id}.txt": box.value for category_id, box in self.boxes.items()})


class HMANominationsButton(discord.ui.DynamicItem[discord.ui.Button], template=r"btn_nom_hma_(?P<year>\d+)"):
    """The nominations hub's HMA button: opens the member's private menu of pages."""

    def __init__(self, year: int):
        super().__init__(discord.ui.Button(
            label=f"{year} HMA Nominations", style=discord.ButtonStyle.primary,
            custom_id=f"btn_nom_hma_{year}", emoji="🏆"))
        self.year = year

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Item, match, /):
        return cls(int(match["year"]))

    @reports_errors
    async def callback(self, interaction: discord.Interaction):
        if await refuse_if_closed(interaction, self.year):
            return

        content, view = nomination_menu(self.year, interaction.user.id)
        if view is None:
            await interaction.response.send_message(content, ephemeral=True)
        else:
            await interaction.response.send_message(content, view=view, ephemeral=True)
