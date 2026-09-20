# IU bot setup guide

Everything the bot needs from outside the code: the Discord application, the server layout it
expects, and the settings on the container. Use it to set the bot up on a new server, to recover
after losing the NAS, or to work out why a feature isn't doing anything.

Related guides: [YouTube credentials and quota](youtube.md), [databases](databases.md) and the
[maintainer playbook](playbook.md) (deploying, Unraid, logs).

## What has to exist

1. A **Discord application** with a bot user, the right intents, and the bot invited to the server
   with enough permissions.
2. A **server layout** that matches the names in [iu/config.py](../iu/config.py): channels, roles,
   emoji and a couple of Merch Booth items.
3. A **container** with the bot's token and server ID, plus a folder for its data.
4. **YouTube credentials**, for the features that build playlists (see [youtube.md](youtube.md)).

## 1. The Discord application

In the [Discord Developer Portal](https://discord.com/developers/applications):

1. **New Application**, then open **Bot**. Reset and copy the token. It is shown once and is the
   value for `DISCORD_TOKEN`. Treat it like a password.
2. Under **Bot → Privileged Gateway Intents**, turn on both of these, or the bot fails to start
   (`PrivilegedIntentsRequired` in the logs):
   - **Server Members Intent**: welcoming new members and fetching members to mention them.
   - **Message Content Intent**: keyword replies, the `#roles` channel and `#new-releases` links.
3. Under **OAuth2 → URL Generator**, tick the scopes **bot** and **applications.commands**, then the
   permissions below, and open the generated link to add the bot to your server.

### Permissions the bot uses

Granting **Administrator** works but gives far more than needed. These are the permissions the code
relies on, and what breaks without each:

| Permission | Used for |
| --- | --- |
| View Channels, Read Message History | Reading messages, fetching old ones, and `/backfill-new-releases` |
| Send Messages, Embed Links, Attach Files | Replies, embeds, GIFs and the exported text files |
| Add Reactions | The reaction on a release link that reached the playlist |
| Manage Messages (and Pin Messages, if your server lists it separately) | Deleting messages in `#roles`; pinning the Listen Game turn order |
| Manage Roles | Giving `Trainee` and `Listen Game Player`, and the self-assign roles in `#roles` |
| Manage Events | Setting an event's end time from the `[1h 30m]` prefix |
| Create Public Threads, Send Messages in Threads | The thread opened shortly before an event |
| Create Polls | The tournament matchup polls (the bot must also be able to end them, which it can for its own polls) |
| Mention @everyone, @here and All Roles | The `@everyone` in the welcome message and the `Listen Game Player` / `Watch Parties` pings |

If custom emoji show up as plain text such as `<:hallyu:...>`, also grant **Use External Emojis**.

### Role order matters

Discord only lets a bot assign roles that sit **below its own highest role**. Drag the bot's role
above `Trainee`, `Listen Game Player`, and every role that members can self-assign in `#roles`.
The channels below must also let the bot see and post in them.

## 2. The server layout the bot expects

The bot finds channels and roles **by exact name**. If a name doesn't exist, the feature that uses
it quietly does nothing (the logs say "Could not find #...").

### Channels

| Channel | What the bot does there |
| --- | --- |
| `welcome` | Posts the welcome message for new members |
| `introductions`, `rules`, `community` | Linked from the welcome message |
| `roles` | Members type `add ...` / `remove ...`; the bot keeps the role list here |
| `dispatch-news` | Heart announcements; where admin heart and raffle commands must be run |
| `merch-booth` | `/check-balance`, `/view-merch`, `/purchase`, `/purchase-history` only work here |
| `listen-game` | Every Listen Game command only works here |
| `tournaments` | Bracket images and matchup polls |
| `new-releases` | YouTube links posted here are added to the yearly playlist |
| `community-events` | Event announcements and the start-of-event threads |
| `sandbox` | `/set-status` only works here |

### Roles

| Role | Purpose |
| --- | --- |
| `Trainee` | Given to every new member |
| `Listen Game Player` | Given when someone joins a game; required for the player commands |
| `Listen Game GM` | Required for the GM commands |
| `Watch Parties` | Pinged when a scheduled event is created |

### Emoji

- **Hearts:** reacting with an emoji named `giveHeart` or `aGiveHeart` gives the message's author a
  daily heart. Both need to exist on the server for that to work.
- The welcome message, some keyword replies and the release reaction use this server's custom emoji
  by ID (the `EMOJI_*` values in [iu/config.py](../iu/config.py)). On a different server, replace
  those IDs with your own emoji.

### Merch Booth items

Two features look up a Merch Booth item by its code. Create them with `/add-merch` (in
`#dispatch-news`) or the features won't work:

- **`RAFFLE`**: the tickets that `/draw-raffle` draws from.
- **`WAYLT`**: the bonus pick for "What Are You Listening To" list events.

### Renaming a channel or role

Change the name in [iu/config.py](../iu/config.py) (the `Channel` and `Role` lists) and redeploy.
Renaming it in Discord alone breaks the feature.

## 3. Settings on the container

These are environment variables. The bot never reads a `.env` file itself; in the container the
values come from the container's settings, and for a local run you load `.env` into your shell (see
the playbook).

| Variable | Set it? | Default in the image | What it does |
| --- | --- | --- | --- |
| `DISCORD_TOKEN` | Yes | none | The bot token. Without it the bot can't log in |
| `DISCORD_GUILD` | Yes | none | The server's ID (enable Developer Mode in Discord, then right-click the server icon and choose Copy Server ID). Commands sync to that server immediately, and the background jobs and the saved status only start when it is set. Without it, commands sync globally and can take a long time to appear |
| `HALLYU_ID` | Optional | the admin's user ID | The person the bot pings and DMs: list submission notices, Merch Booth redemptions, raffle instructions and role errors |
| `TOKEN_DIR` | Optional | `/app/data/token.json` | The full path of the YouTube token file (despite the name, it is a file path) |
| `DB_PATH_<NAME>` | Optional | `/app/data/<name>.db` | Where each database lives (11 of them, listed in [databases.md](databases.md)). An unset one is skipped at startup and its features fail |
| `DATA_DIR` | No | `/app/data` | Only used by the image to build the paths above |
| `LOG_LEVEL` | Optional | `INFO` | `DEBUG` also shows the routine "checking..." lines the background loops write every minute, 5 minutes or hour. Use it only while investigating |
| `HEARTBEAT_PATH` | Optional | `/tmp/iu-bot-heartbeat` | The file the bot touches every minute while connected; the container healthcheck reads it. The image sets it, so leave it alone |
| `PYTHONUNBUFFERED` | No | `1` | Makes log lines appear immediately |

So in practice you set `DISCORD_TOKEN` and `DISCORD_GUILD`, and map a folder on the host to
`/app/data`. That folder holds every database and `token.json`.

## 4. First-run checklist

1. Start the container and read its logs. A healthy start shows the databases initialising, the
   commands syncing to your server, and the bot connecting (the exact lines are in the
   [playbook](playbook.md#17-verify-the-deploy)).
2. In Discord, check that the slash commands appear when you type `/`.
3. Run `/check-balance` in `#merch-booth` and `/set-status` in `#sandbox` (admin) as a quick test
   of the channel rules.
4. Post a message containing `2am` to see a keyword reply, and join a test Listen Game to check the
   roles and permissions.
5. Set up YouTube ([youtube.md](youtube.md)) and try a link in `#new-releases`.
