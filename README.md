# IU bot

IU bot is a Discord bot used to enrich the HallyU discord server. IU has many
functionalities which are outlined below.

## Welcoming members

When a new member joins the server, IU will welcome them with an informational message
about the server. She will also assign the new member the `Trainee` role, which is part of
the new member process for the server.

## Message replies

IU has a predefined list of special triggers, which when found in a message will trigger a
reply. Some replies are just text, some are just GIFs, and some are text with GIF
attachments! IU also responds to direct pings (except the global `@everyone` ping).

## Commands

IU has several helpful commands which can be triggered via Discord's new `/` command
framework. The commands are described in detail below.

### `/hallyu-calendar`

Usage: `/hallyu-calendar`

This command will prompt IU to respond with a message explaining how to add the server's
Google Calendar to your account, so you can always see the server events going on.

### `/rankdown-turn`

Usage:
`/rankdown-turn song_to_eliminate reason_to_eliminate song_to_nominate reason_to_nominate next_message`

This command will allow you to take your Rankdown turn by automatically creating &
formatting the message based on your chosen nomination and elimination.

### `/poll`

Usage: `/poll question answers`

This command lets you ask a question with a predefined set of possible answers to poll the
server. The `answers` input uses `|` to separate the possible answers, e.g. `yes|no`.

### `/add-hma-pick`

Usage: `/add-hma-pick pick`

This command lets you store a brief message with IU, which is useful for remembering
things throughout the year you want to nominate for the year-end activities like the
HallyU Music Awards (HMAs).

Along with this command, you can also trigger:

- `/delete-hma-picks`, which resets all picks you've saved (i.e. starting a new year's
  nominations)
- `/my-hma-picks`, which gets IU to send you a DM with the list of picks you've saved thus
  far.

### `/my-bias-group`

Usage `/my-bias-group member`

This command lets you see the bias group embed of a member, if it's been unlocked. If
`member` is not specified, it will show your embed.

### `/my-ultimate-bias`

Usage `/my-ultimate-bias member`

This command lets you see the ultimate bias embed of a member, if it's been unlocked. If
`member` is not specified, it will show your embed.

## Getting releases

1. Open console for IU Bot docker image in UnraidOS
2. cd `iu/releases`
3. `cat file.txt`
4. Copy here
