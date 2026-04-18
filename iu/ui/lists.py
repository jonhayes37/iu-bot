"""UI components and validation logic for list submissions."""

import logging
import discord
from db.lists import get_event_details, save_submission, get_user_submission
from db.merch import check_user_owns_item, consume_item
from utils.validation import sanitize_list

logger = logging.getLogger('iu-bot')

class DynamicListModal(discord.ui.Modal):
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
                        "Don't worry, your list isn't lost. Copy your text below:\n"
                        f"```{raw_list}```"
                    )
                    await interaction.response.send_message(fail_msg, ephemeral=True)
                    return

        # Validation with the dynamically adjusted target_count
        is_valid, error_msg, clean_text, urls = sanitize_list(raw_list, target_count)
        if not is_valid:
            # Echo their submission so they don't lose it
            fail_msg = (
                f"❌ **Submission Failed** ❌\n{error_msg}\n\n"
                "Don't worry, your list isn't lost! Copy your text from the box below, "
                "make sure you have the correct number of items, "
                "and click the submit button again!\n"
                f"```{raw_list}```"
            )
            await interaction.response.send_message(fail_msg, ephemeral=True)
            return

        # Consume the item if necessary
        if needs_burn:
            if not consume_item(interaction.user.id, "WAYLT"):
                await interaction.response.send_message(
                    "❌ Failed to consume your WAYLT bonus pick from inventory. Please try again or ping an admin.", 
                    ephemeral=True
                )
                return

        user_id = interaction.user.id
        username = interaction.user.display_name
        success = save_submission(self.event_id, user_id, username, raw_list, clean_text, urls)

        if success:
            msg = (
                "Your list has been submitted! You can click the button again anytime "
                "before the event closes to edit it."
            )
            if needs_burn:
                msg = f"🎟️ **What Are You Listening To Bonus Pick Consumed!**\n{msg}"

            await interaction.response.send_message(msg, ephemeral=True)
        else:
            logger.error("Database error when saving submission for user %s on event %s. Full submission:\n%s",
                         user_id, self.event_id, raw_list)
            await interaction.response.send_message(
                "Something went wrong saving your list to the database. Please ping an admin!",
                ephemeral=True)

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
