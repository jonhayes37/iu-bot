"""UI components and validation logic for list submissions."""

import re
import logging
import discord
from db.lists import get_event_details, save_submission, get_user_submission

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
        is_valid, error_msg, clean_text, urls = process_submission(raw_list, self.expected_count)
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

        user_id = interaction.user.id
        username = interaction.user.display_name
        success = save_submission(self.event_id, user_id, username, raw_list, clean_text, urls)

        if success:
            await interaction.response.send_message(
                "Your list has been submitted! You can click the button again anytime "
                "before the event closes to edit it.",
                ephemeral=True)
        else:
            logger.error("Database error when saving submission for user %s on event %s. Full submission:\n%s",
                         user_id, self.event_id, raw_list)
            await interaction.response.send_message(
                "Something went wrong saving your list to the database. Please ping an admin!",
                ephemeral=True)

def process_submission(raw_text: str, expected_count: int) -> tuple[bool, str, str, str]:
    """
    Parses the raw modal text. 
    Returns: (is_valid, error_msg, cleaned_text, comma_separated_urls)
    """
    # Split by line break and remove completely empty lines
    lines = [line.strip() for line in raw_text.split('\n') if line.strip()]

    # Hard validation: Check the line count
    if expected_count > 0 and len(lines) != expected_count:
        return False, f"Oops! This event requires exactly {expected_count} items, but I counted {len(lines)}.", "", ""

    cleaned_lines = []
    extracted_urls = []
    for i, line in enumerate(lines, start=1):
        url_match = re.search(r'(https?://[^\s()]+)', line)
        if url_match:
            url = url_match.group(1)
            extracted_urls.append(url)
            # Remove the URL from the text, including optional surrounding parentheses
            line = re.sub(r'\s*\(\s*https?://[^\s()]+\s*\)\s*', '', line)
            line = re.sub(r'\s*https?://[^\s()]+\s*', '', line)
        else:
            extracted_urls.append("")

        # Normalize varying slashes like "// ", " //", or "//" to exactly " // "
        line = re.sub(r'\s*//\s*', ' // ', line)

        # If there is no "//" but they used a spaced hyphen, convert only the first one
        if ' // ' not in line and ' - ' in line:
            line = line.replace(' - ', ' // ', 1)

        # Normalize starting numbers from 1., 1), 1, etc
        line = re.sub(r'^\d+[\.\)\-]?\s*', '', line)
        cleaned_lines.append(f"{i}. {line}")

    # 3. Reassemble the final strings for the database
    final_text = "\n".join(cleaned_lines)
    final_urls = ",".join(extracted_urls)

    return True, "", final_text, final_urls

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
