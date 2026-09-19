# YouTube credentials and quota

The bot uses the YouTube Data API to build and maintain playlists: the yearly releases playlist,
each Listen Game round's playlist, and potpourri playlists. It needs two things: a one-time
sign-in that produces `token.json`, and an awareness of the daily quota.

Playlists are created as **unlisted** playlists on the YouTube account that signed in.

## One-time setup

You do this on your own computer, not on the NAS.

### 1. Create the Google Cloud project

1. Go to the [Google Cloud Console](https://console.cloud.google.com/) and create a project (any
   name, for example `iu-bot`).
2. Open **APIs & Services → Library**, find **YouTube Data API v3** and click **Enable**.

### 2. Configure the consent screen

1. Open **APIs & Services → OAuth consent screen** (called **Google Auth Platform** in newer
   consoles) and choose the user type **External**.
2. Fill in the app name and your email. On the **Test users** step, add the Google account that
   owns the YouTube channel the playlists should live on.
3. **Publish the app** (switch its status from *Testing* to *In production*). This matters: as
   Google documents it, refresh tokens issued to an app that is still in *Testing* stop working
   after **7 days**, and the bot's YouTube features die a week after every sign-in. A published app
   for your own use will show an "unverified app" warning when you sign in. That is expected;
   continue past it.

### 3. Create the OAuth client

1. Open **APIs & Services → Credentials → Create credentials → OAuth client ID**.
2. Choose the application type **Desktop app**, give it a name, and create it.
3. Download the JSON file and save it as `credentials.json` in the repo folder. It is git-ignored
   and excluded from the Docker image. Keep it private, and don't send it to anyone.

### 4. Generate the token

From the repo root, with the project's virtual environment active:

```bash
python iu/scripts/generate_token.py
```

A browser window opens. Sign in with the account you added as a test user, approve access to
"manage your YouTube account", and continue past the unverified-app warning. The script writes
`token.json` in the folder you ran it from.

### 5. Put the token on the NAS

Copy `token.json` into the folder that is mapped to `/app/data` on the container (for example
`/mnt/user/appdata/iu-bot/token.json`), then restart the container. The bot reads it from the path in
`TOKEN_DIR`, which defaults to `/app/data/token.json`. It only needs `token.json`; `credentials.json`
stays on your computer.

## Renewing the token

Run steps 4 and 5 again. Do this when the logs show `invalid_grant` or authentication errors from
YouTube. A token stops working when:

- the consent screen was left in *Testing* (after 7 days, see above);
- the Google account's password was changed or access was revoked;
- the token went unused for a long time (Google can expire tokens after about six months of
  inactivity).

The bot refreshes its short-lived access token by itself and does not need a restart for that; only
a dead refresh token needs a new `token.json`.

## Quota

The API gives the project **10,000 units per day** by default, and the count **resets at midnight
Pacific time**. Different calls cost different amounts, and the expensive ones are anything that
changes a playlist (50 units each):

| Call | Cost |
| --- | --- |
| `videos.list` (look up titles and publish dates) | 1 per request, however many videos it covers (the bot sends up to 50 at once) |
| `playlistItems.list` (read a playlist) | 1 per request (50 items per page) |
| `playlistItems.insert` (add a video) | 50 |
| `playlistItems.delete` (remove a video) | 50 |
| `playlists.insert` (create a playlist) | 50 |

### What each feature spends

| Action | Calls | Units |
| --- | --- | --- |
| A new link in `#new-releases` | look up + add | about 51 (plus 50 the first time each year, to create the playlist) |
| Submitting a song in the Listen Game | look up + add | about 51 (about 101 for the first song of a round, which creates its playlist) |
| Replacing your submitted song | the above + find and remove the old one | about 102 |
| A GM rejecting a song, or removing a player who had submitted | find + remove | about 51 |
| `/listen-game-gm-sync-playlist` | read the playlist + add each missing song | 1 + 50 for each missing song |
| `/create-potpourri-playlist` | create + add every video | 50 + 50 per video |
| `/backfill-new-releases` | one look-up per 50 messages + add each new video | about 1 per 50 messages + 50 per new video |

The practical limit is **about 190 playlist changes per day**. For example, a potpourri playlist
with 150 videos uses about 7,550 units, three quarters of a day's quota.

### When the quota runs out

Nothing is lost, and nothing needs fixing tonight:

- **Listen Game songs** are still saved and the player is told. The GM gets a DM, and runs
  `/listen-game-gm-sync-playlist` after midnight Pacific to add the missing songs.
- **Release links** that couldn't be added are recorded and retried the next time that link is
  processed, for example by `/backfill-new-releases`.
- **A potpourri playlist** stops partway and reports which videos were not added.

### Checking usage

In the Cloud Console, open **APIs & Services → YouTube Data API v3 → Quotas & System limits** to see
today's usage. If you regularly hit the limit, you can ask Google for more through the quota
increase form linked from that page.

## Troubleshooting

| Log line | Meaning | Fix |
| --- | --- | --- |
| `token.json missing at ...` | The file isn't at the `TOKEN_DIR` path | Put `token.json` in the mapped data folder and restart |
| `invalid_grant` or other authentication errors | The refresh token is dead | Renew it, above |
| `YouTube API Quota exceeded` | The day's quota is used up | Wait for midnight Pacific; sync afterwards |
| `The request cannot be completed because you have exceeded your quota` (HTTP 403) | Same as above | Same as above |
| Songs saved but not on the playlist | A quota hit or a private or deleted video | `/listen-game-gm-sync-playlist` |

More on reading logs is in the [playbook](playbook.md#3-read-the-logs).
