"""UI components and validation logic for list submissions."""

import logging
import discord
from config import admin_user_id
from db.lists import SaveOutcome, get_event_details, save_submission, get_user_submission
from db.merch import check_user_owns_item
from ui.base import SafeModal, report_interaction_error, reports_errors
from utils.discord_files import text_file
from utils.validation import sanitize_list

logger = logging.getLogger('iu-bot')

class DynamicListModal(SafeModal):
    """
    A dynamic modal for list submissions that adjusts its placeholder
    and expected line count based on the event configuration.
    """
    def __init__(self,
                 event_id: str,
                 event_name: str,
                 expected_count: int,
                 placeholder_format: str,
                 default_text: str = None):
        super().__init__(title=event_name[:45])
        self.event_id = event_id
        self.event_name = event_name
        self.expected_count = expected_count
        self.submission_text = discord.ui.TextInput(
            label='Your List',
            style=discord.TextStyle.paragraph,
            placeholder=placeholder_format,
            default=default_text,
            required=True,
            max_length=4000
        )
        self.add_item(self.submission_text)

    # pylint: disable=arguments-differ
    async def on_submit(self, interaction: discord.Interaction):
        raw_list = self.submission_text.value

        # Pre-parse lines to see if they are trying to use the extra slot perk
        lines = [line.strip() for line in raw_list.split('\n') if line.strip()]

        # Figure out how many lines they had before editing
        previous_lines = []
        if self.submission_text.default:
            previous_lines = [line.strip() for line in self.submission_text.default.split('\n') if line.strip()]

        target_count = self.expected_count
        needs_burn = False
        is_waylt_event = "listening to" in self.event_name.lower()

        # If it's a valid WAYLT event, expects a fixed number, and they submitted exactly one extra
        if is_waylt_event and self.expected_count > 0 and len(lines) == self.expected_count + 1:
            # Did they already have the extra slot unlocked from a previous submission?
            if len(previous_lines) == self.expected_count + 1:
                target_count = self.expected_count + 1
            else:
                # This is a new request for an extra slot. Check inventory.
                if check_user_owns_item(interaction.user.id, "WAYLT"):
                    needs_burn = True
                    target_count = self.expected_count + 1
                else:
                    fail_msg = (
                        "❌ **Missing Item** ❌\n"
                        f"You submitted {self.expected_count + 1} items, but this event only allows "
                        f"{self.expected_count}.\n\nTo unlock an extra slot, you need to purchase "
                        "the **What Are You Listening To Bonus Pick** (`WAYLT`) item from the Merch Booth! "
                        "Don't worry, your list isn't lost. It's attached as `your_list.txt`."
                    )
                    await interaction.response.send_message(
                        fail_msg, file=text_file(raw_list, "your_list.txt"), ephemeral=True)
                    return

        # Validation with the dynamically adjusted target_count
        is_valid, error_msg, clean_text, urls = sanitize_list(raw_list, target_count)
        if not is_valid:
            # Echo their submission so they don't lose it
            fail_msg = (
                f"❌ **Submission Failed** ❌\n{error_msg}\n\n"
                "Don't worry, your list isn't lost! It's attached as `your_list.txt`. "
                "Copy your text from it, make sure you have the correct number of items, "
                "and click the submit button again!"
            )
            await interaction.response.send_message(
                fail_msg, file=text_file(raw_list, "your_list.txt"), ephemeral=True)
            return

        user_id = interaction.user.id
        username = interaction.user.display_name

        # The list and the bonus pick are saved together: either both change or neither does
        outcome = save_submission(self.event_id, user_id, username, raw_list, clean_text, urls,
                                  use_item="WAYLT" if needs_burn else None)
        if outcome is SaveOutcome.ITEM_MISSING:
            await interaction.response.send_message(
                "❌ **Missing Item** ❌\nYour WAYLT bonus pick is no longer in your inventory, so nothing was saved. "
                "Your list is attached as `your_list.txt`.",
                file=text_file(raw_list, "your_list.txt"), ephemeral=True)
            return

        msg = (
            "Your list has been submitted! You can click the button again anytime "
            "before the event closes to edit it."
        )
        if needs_burn:
            msg = f"🎟️ **What Are You Listening To Bonus Pick Consumed!**\n{msg}"

        await interaction.response.send_message(msg, ephemeral=True)

        # Notify admin
        try:
            admin_user = interaction.client.get_user(admin_user_id()) or \
                await interaction.client.fetch_user(admin_user_id())
            if admin_user:
                action = "updated" if previous_lines else "submitted"
                await admin_user.send(f"📥 **{username}** {action} their list for **{self.event_name}**!")
        except discord.Forbidden:
            logger.warning("Could not DM admin (ID: %s) about list submission. DMs might be closed.",
                           admin_user_id())
        except discord.HTTPException as ex:
            logger.error("Failed to send admin notification DM: %s", ex)

    # pylint: disable=arguments-differ
    async def on_error(self, interaction: discord.Interaction, error: Exception):
        # Hand the text back so a failed save never costs the user their list
        await report_interaction_error(interaction, error, keep_text={"your_list.txt": self.submission_text.value})

class SubmitListButton(discord.ui.DynamicItem[discord.ui.Button],
                       template=r"submit_list:(?P<event_id>[^:]+?)(?P<closed>_closed)?"):
    """
    The button on a list announcement. The event is part of the button's ID
    (`submit_list:<event_id>`, with `_closed` added once the event is closed), so one class handles
    every event's button, on messages posted before a restart or before this class existed.
    """

    def __init__(self, event_id: str, closed: bool = False):
        super().__init__(discord.ui.Button(
            label="Submissions Closed" if closed else "Submit Your List",
            style=discord.ButtonStyle.secondary if closed else discord.ButtonStyle.primary,
            custom_id=f"submit_list:{event_id}{'_closed' if closed else ''}",
            disabled=closed,
            emoji="🔒" if closed else "📥"
        ))
        self.event_id = event_id
        self.closed = closed

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Item, match, /):
        return cls(match["event_id"], closed=bool(match["closed"]))

    @reports_errors
    async def callback(self, interaction: discord.Interaction):
        if self.closed:
            await interaction.response.send_message("Submissions for this event are closed!", ephemeral=True)
            return
        await handle_list_button_click(interaction, self.event_id)


async def handle_list_button_click(interaction: discord.Interaction, event_id: str):
    """Triggered when a user clicks the 'Submit' button on an announcement."""
    event_details = get_event_details(event_id)

    if not event_details:
        await interaction.response.send_message("This event no longer exists in the database.", ephemeral=True)
        return

    if not event_details.get("is_active"):
        await interaction.response.send_message("Submissions for this event are officially closed!", ephemeral=True)
        return

    # Check if they have submitted before so we can pre-fill the form
    previous_text = get_user_submission(event_id, interaction.user.id)
    modal = DynamicListModal(
        event_id=event_id,
        event_name=event_details.get("event_name", "Submit List"),
        expected_count=event_details.get("expected_count", 0),
        placeholder_format=event_details.get("placeholder_text", "1. Artist // Song"),
        default_text=previous_text
    )

    await interaction.response.send_modal(modal)
