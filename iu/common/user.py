"""Helper functions relating to users"""

from common.discord_ids import USERNAMES


def user_info_from_interaction(interaction, member_name):
    invalid_member_name = False
    user_id = interaction.user.id
    username = interaction.user.nick if interaction.user.nick else \
        interaction.user.display_name if interaction.user.display_name else \
        interaction.user.global_name

    if member_name:
        for display, username_id in USERNAMES.items():
            if display.lower() == member_name.lower():
                return username_id, display, True
        invalid_member_name = True

    return user_id, username, invalid_member_name
