# IU bot

IU is the HallyU Discord server's bot. She welcomes new members, replies to keywords with GIFs,
runs the server's heart economy and Merch Booth, hosts the Listen Game, and runs the community's
lists, bracket tournaments and end-of-year awards.

Most features are used through Discord's `/` commands. A few only work in a particular channel
(noted in each section), and IU will tell you if you're in the wrong one. In the tables below,
**Admin** commands are visible only to server administrators, and **GM** commands need the
`Listen Game GM` role.

- [Welcoming members](#welcoming-members)
- [Keyword replies](#keyword-replies)
- [Roles](#roles)
- [Hearts and the Merch Booth](#hearts-and-the-merch-booth)
- [Listen Game](#listen-game)
- [Lists](#lists)
- [Tournaments](#tournaments)
- [End of year: Top 25, Hall of Fame and HMAs](#end-of-year-top-25-hall-of-fame-and-hmas)
- [Bias cards](#bias-cards)
- [New releases playlist](#new-releases-playlist)
- [Watch parties and events](#watch-parties-and-events)
- [Potpourri playlists](#potpourri-playlists)
- [Bot status](#bot-status)

## Welcoming members

When someone joins the server, IU gives them the `Trainee` role and posts a welcome message in
`#welcome`. The message points them to the rules, the roles channel, the introductions channel,
and an explanation of the heart economy.

## Keyword replies

IU replies to messages that contain certain words or phrases, usually with a GIF or image and
sometimes a line of text. Some replies only appear some of the time, some pick randomly between a
few variations, and a few only trigger in the right context (for example, "ballad" only when the
message includes a link). IU stays quiet in `#roles` and `#dispatch-news`. If you `@` her directly
she'll answer too.

## Roles

The `#roles` channel lists every self-assignable role, grouped by category, with any shorthand
names (aliases) you can use. To change your roles, type a message in that channel:

| Message | What it does |
| --- | --- |
| `add <role>` or `+<role>` | Gives you the role |
| `remove <role>` or `-<role>` | Takes the role away |

You can use the role's name or any of its aliases. IU deletes your message and confirms briefly
so the channel stays tidy.

| Command | Who | Description |
| --- | --- | --- |
| `/register-role role category [aliases]` | Admin | Adds a role to the list (aliases are comma-separated) and refreshes `#roles` |
| `/sync-roles` | Admin | Rebuilds the role list in `#roles` |

## Hearts and the Merch Booth

Hearts are the server's currency. Spend them on perks in the Merch Booth.

### Earning hearts

- **Daily heart:** react to someone's message with the heart emoji (`aGiveHeart` / `giveHeart`) to
  give them a heart. You can give one heart per day, and not to yourself.
- **Popular posts:** when a message gets reactions from 5 different people, its author earns 3 hearts.
- **Tournaments:** vote in every matchup of a round to earn a heart, and one voter wins a bonus
  in each tournament's raffle (see [Tournaments](#tournaments)).
- **Events and giveaways:** admins can award hearts directly or run a random draw.

IU announces heart rewards in `#dispatch-news`.

### Spending hearts

Each Merch Booth item has a short code (SKU), a price, and sometimes a limit
per person. Sold-out items (ones you've hit the limit on) are shown struck through.

| Command | Who | Where | Description |
| --- | --- | --- | --- |
| `/check-balance` | Everyone | `#merch-booth` | Shows how many hearts you have |
| `/view-merch` | Everyone | `#merch-booth` | Lists the perks for sale and what you can still buy |
| `/purchase item_id` | Everyone | `#merch-booth` | Buys one of an item using its code |
| `/purchase-history` | Everyone | `#merch-booth` | Shows everything you've bought |
| `/add-merch item_id name description price [max_per_user]` | Admin | `#dispatch-news` | Adds an item, or updates it if the code already exists |
| `/modify-balance member amount reason` | Admin | `#dispatch-news` | Adds or removes hearts (use a negative amount to remove) |
| `/random-award users amount reason` | Admin | `#dispatch-news` | Picks a random winner from the mentioned users and awards them hearts |
| `/draw-raffle` | Admin | `#dispatch-news` | Draws a winner from everyone holding `RAFFLE` items (more tickets, better odds), announces them, and resets the tickets |

## Listen Game

A turn-based music game. Everyone takes a turn as the **listener**. The listener sets a ruleset,
the other players each submit a YouTube song that fits it, and the listener ranks them all.
Rankings earn points, and whoever has the most points after everyone has had a turn wins.

All Listen Game commands work in `#listen-game`.

### How a game runs

1. **Registration.** A GM opens the game with `/listen-game-create`, choosing a substitute GM who
   runs the GM duties for the round when the GM is the listener. Players press **Join Listen Game!**
   (which gives them the `Listen Game Player` role) or **Leave**.
2. **Start.** The GM runs `/listen-game-start`. IU randomises the turn order and posts and pins it.
3. **Ruleset.** The current listener runs `/listen-game-post-ruleset` to write their ruleset. It
   can be edited while submissions are still open; IU announces any change.
4. **Submissions.** Players run `/listen-game-submit-song url` with a YouTube link. You can
   resubmit to swap your song. A video someone else has already submitted this round is rejected,
   and the listener doesn't submit. IU adds each song to that round's YouTube playlist (creating
   it automatically) and keeps a live "submissions so far" counter in the channel. The GM is
   notified of each submission.
5. **Approval.** When everyone has submitted, the GM gets a summary. They can reject duplicates
   or bad picks, then run `/listen-game-gm-approve-playlist` to close the round. The listener
   receives the playlist by DM.
6. **Ranking.** The listener runs `/listen-game-submit-ranking`. They choose songs one at a time,
   starting from last place and working up to first, writing commentary for each. Each pick is
   saved as it's made, so if the bot restarts (or the message is dismissed) the listener can run the
   command again and carry on, or press **Start over**. When the list is complete they press
   **Confirm & Publish Results**.
7. **Reveal.** IU counts the results down in the channel, one song every 15 seconds with the
   listener's commentary, then posts the round's points and the current standings, and announces
   the next listener. If the bot is restarted mid-reveal it picks up where it left off.
8. **Finish.** After the last turn IU posts the final leaderboard and links to every round's playlist.

**Scoring:** in a round with N songs, first place earns N points, second N-1, and so on down to 1.

**Reminders and deadlines.** Players who haven't submitted are sent a DM reminder after 48 hours,
then once a day. If the GM set `max_round_days`, submissions close automatically when the time is up
and the listener is told.

### Player commands

| Command | Who | Description |
| --- | --- | --- |
| `/listen-game-post-ruleset` | Listener | Post or update the ruleset for your round |
| `/listen-game-submit-song url` | Players | Submit or replace your song for the current round |
| `/listen-game-submit-ranking` | Listener | Rank the submissions and write commentary. If the reveal was interrupted, run it again to resume |

### GM commands

| Command | Description |
| --- | --- |
| `/listen-game-create substitute_gm [max_round_days]` | Open a new game for registration |
| `/listen-game-start` | Close registration and start the game |
| `/listen-game-gm-approve-playlist` | Approve the playlist once everyone has submitted and send it to the listener |
| `/listen-game-gm-reject-song player reason` | Remove a player's submission and DM them the reason |
| `/listen-game-gm-force-start-round skipped_users` | Move to ranking without waiting for late players. You must mention exactly the players who haven't submitted |
| `/listen-game-gm-force-submit player url` | Submit a song on a player's behalf, skipping the usual checks |
| `/listen-game-gm-sync-playlist` | Add any submitted songs that are missing from the YouTube playlist (for example after a YouTube quota limit) |
| `/listen-game-gm-skip-turn player reason` | Skip the current listener's turn |
| `/listen-game-gm-remove-player player reason` | Remove a player from the game (not the current listener; skip their turn first) |
| `/listen-game-gm-swap-players player1 player2` | Swap the turn order of two players who haven't been listener yet |

## Lists

Lists let members submit ranked lists (favourite songs of the year, "what are you listening to",
and so on) through a button and a form, and give admins a clean export.

**For members.** Click **Submit Your List** on an announcement. Enter one entry per line, in the
form `Artist // Song`, with an optional YouTube link:

```text
1. Berry Good // Don't Believe
2. IVE // All Night (https://youtu.be/xU8mQMLx0tk?t=27)
```

Numbering is optional and IU tidies up the formatting. You must enter exactly the number of entries
the event asks for. If something's wrong, IU explains and sends your text back as a file so you
don't lose it. Click the button again any time before the event closes to edit your list.

For "What Are You Listening To" events, you can add one bonus entry by owning the **What Are You
Listening To Bonus Pick** perk (`WAYLT`) from the Merch Booth, which is used up when you submit the extra pick.

| Command | Who | Description |
| --- | --- | --- |
| `/create-list-event event_id event_name [expected_count] [placeholder]` | Admin | Posts the announcement with a **Submit Your List** button in the current channel. The event ID can use letters, numbers, `-` and `_` |
| `/close-list-event event_id` | Admin | Closes the event and disables its button |
| `/export-lists event_id` | Admin | Uploads two text files: the cleaned lists, and a reference sheet of every entry's link with its start time |

## Tournaments

Bracket tournaments decided by community votes, using Discord's built-in polls in `#tournaments`.

1. An admin starts a tournament with a title, a description, and the entrants in seed order.
   The number of entrants must be a power of two (4, 8, 16, 32, ...).
2. IU posts the bracket image and one poll per Round 1 matchup. Each round lasts a set number of
   days (2 by default).
3. When the polls close, IU tallies the votes, advances the winners, posts the updated bracket,
   and opens the next round. Ties go to the higher seed.
4. After the final, IU announces the champion and posts the completed bracket.

**Rewards:** vote in every matchup of a round to earn a heart. Every vote across the tournament is
also a raffle ticket, and one voter wins 5 hearts when it finishes.

| Command | Who | Description |
| --- | --- | --- |
| `/new-tournament title description entrants [days_per_round]` | Admin | Creates the tournament. Entrants are separated by `\|`, from seed 1 to the lowest seed |
| `/force-close-round tournament_id` | Admin | Ends the current round's polls early so IU resolves them on her next check (within about 5 minutes) |

## End of year: Top 25, Hall of Fame and HMAs

The server's end-of-year activities run in phases. Admins post the buttons or run the commands
below, and members respond. Members can change their answers any time before the deadline.

### Phase 1: Nominations and suggestions

- **Top 25 Songs and Hall of Fame.** Admins post a hub with buttons for a member's ranked
  **Top 25 Songs** of the year (plus 3 honourable mentions, in the same `Artist // Song` format as
  [Lists](#lists)) and their **Hall of Fame** nominations.
- **HallyU Music Awards (HMAs).** Members nominate with `/hma-nomination`, picking every award
  category the nominee fits from three groups: **Daesang** (Album, Artist, Song and Music Video
  of the Year), **Bonsang** (best groups, soloists, choreography, covers and more) and **Fun**
  awards. Nominations for the Best Dance Cover and Best Vocal Cover categories must include a YouTube link.
- **Category suggestions.** Admins can open a button for members to suggest categories to add or drop.

### Phase 2: Voting

After admins set the finalists, `/end-of-year-voting` posts the voting buttons. Ballots are
ranked: 1st choice is worth 3 points, 2nd choice 2, and 3rd choice 1.

- **Hall of Fame:** rank your top 3 nominees.
- **HMAs:** choose a category and rank your top 3 finalists. Categories still waiting for your
  vote are marked with a clock, and finished ones with a tick. A category needs at least 3
  finalists before it can be voted on.

| Command | Who | Description |
| --- | --- | --- |
| `/hma-nomination nominee` | Everyone | Nominate someone or something for one or more HMA categories |
| `/end-of-year-nominations` | Admin | Posts the Top 25 and Hall of Fame nomination buttons |
| `/end-of-year-hma-suggestions` | Admin | Posts the category suggestions button |
| `/export-end-of-year-nominations` | Admin | Exports the Top 25 lists, honourable mentions and Hall of Fame nominations |
| `/hma-nomination-export [year]` | Admin | Exports the HMA nominations, grouped by category |
| `/hma-suggestions-export` | Admin | Exports the category suggestions |
| `/hma-set-nominees category_id nominees_pipe` | Admin | Sets the finalists for an HMA category (separated by `\|`) |
| `/hall-of-fame-set-nominees nominees_pipe` | Admin | Sets the Hall of Fame finalists (separated by `\|`) |
| `/end-of-year-voting` | Admin | Posts the voting buttons |

## Bias cards

Show off your favourites with a card once an admin has set yours up.

| Command | Who | Description |
| --- | --- | --- |
| `/my-ultimate-bias [member]` | Everyone | Shows your ultimate bias card (name, group, position, birthday, hometown and why), or another member's |
| `/my-bias-group [member]` | Everyone | Shows your bias group card (group info, your bias, title track, B-track, album and why), or another member's |
| `/create-ultimate-bias member ...` | Admin | Creates a member's ultimate bias card |
| `/update-ultimate-bias member ...` | Admin | Changes selected fields on a member's ultimate bias card |
| `/create-bias-group member ...` | Admin | Creates a member's bias group card |
| `/update-bias-group member ...` | Admin | Changes selected fields on a member's bias group card |

If a member's card doesn't exist yet, IU says they haven't unlocked one.

## New releases playlist

Post YouTube links in `#new-releases` and IU adds them to an unlisted YouTube playlist for that
award year, named like "2026 K-Pop Releases". She reacts to your message when a video
is added. A video only counts if it was published in the same award year as your post (an award year
runs from December 1 to November 30). Duplicates are ignored.

| Command | Who | Description |
| --- | --- | --- |
| `/backfill-new-releases start_date` | Admin | Scans `#new-releases` from a date (`YYYY-MM-DD`) and adds any links that were missed |

## Watch parties and events

IU adds some extras to Discord's scheduled events:

- **Custom length.** Start an event's description with a duration in square brackets, like
  `[1h 30m] Movie night`, and IU sets the event's end time and removes the bracket text.
- **Announcement.** When an event is created, IU announces it in `#community-events`, pings the
  `Watch Parties` role and links the RSVP page.
- **Start-of-event thread.** About 15 minutes before an event begins, IU opens a thread for it
  in `#community-events` and pings everyone who RSVP'd (if anyone did).

## Potpourri playlists

| Command | Who | Description |
| --- | --- | --- |
| `/create-potpourri-playlist file playlist_title` | Admin | Upload a CSV (a name column and a link column) and IU builds an unlisted YouTube playlist. Songs are interleaved so each person's picks are spread out, and repeated videos are skipped. Any link that couldn't be added is listed afterwards |

## Bot status

| Command | Who | Where | Description |
| --- | --- | --- | --- |
| `/set-status status_text [days]` | Admin | `#sandbox` | Sets IU's "Listening to" status for a number of days (7 by default) |
