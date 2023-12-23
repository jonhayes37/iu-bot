"""/hallyu-calendar command"""

import discord

CALENDAR_LINK = "https://calendar.google.com/calendar/ical/b6a7d2e436aed7053f51b4d88c92cef589362f4"
"05319da47db22396c2909cf94%40group.calendar.google.com/public/basic.ics"

async def send_calendar(interaction):
    calendar_gif = discord.File('iu/media/gifs/calendar_tutorial.gif',
                                filename='calendar_tutorial.gif')
    await interaction.response.send_message(
        "Here's the <:hallyu:795848873910206544> calendar with all of our events! " \
        f"{CALENDAR_LINK}\nHow to add to your calendar:",
        file=calendar_gif
    )
