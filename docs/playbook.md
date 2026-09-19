# IU bot maintainer playbook

Step-by-step procedures for changing, deploying and troubleshooting the bot. For what the bot
does, see the [README](../README.md). For code conventions, see [CLAUDE.md](../CLAUDE.md).

Other guides:

- [Setup guide](setup.md): the Discord application, the server layout, and every setting.
- [YouTube credentials and quota](youtube.md).
- [Databases](databases.md): inspecting, permissions, backups and adding a new one.

> **A note on the Unraid steps.** The commands and the repo details below were checked against the
> project. The Unraid menu names and paths are written from general Unraid knowledge and may differ
> slightly on your version. The first time you follow a step, confirm it matches what you see, and
> fix this file if it doesn't. Steps marked *(check)* are the ones most worth confirming.

Setup at a glance:

- **Image:** `jonhayes37/iu-bot` on Docker Hub (a private repo), built for `linux/amd64`.
- **Runs on:** the Unraid NAS as a Docker container.
- **Data:** SQLite files in `/app/data` inside the container, which is mapped to a folder on the NAS.
- **Config:** environment variables set on the container (see [Container settings](#container-settings)).

## 1. Author and deploy a change

### 1.1 Make a branch

```bash
git switch main
git pull
git switch -c short-description-of-change
```

### 1.2 Make and check the change

Set up once:

```bash
python3 -m venv venv && source venv/bin/activate
pip install -e . && pip install -r requirements-dev.txt
```

Before every commit:

```bash
pylint iu        # must exit 0, CI fails on any message
pytest --cov=iu  # once tests exist; CI requires 80% coverage
```

If you added or changed a slash command, update its section in the README too. If you added a
database column, add it to `COLUMN_MIGRATIONS` in `iu/db/initialize.py` as well as the `.sql`
schema (see CLAUDE.md).

To try the change locally, export the settings and run the bot. The bot does **not** read `.env`
by itself, so load it into the shell first:

```bash
set -a; source .env; set +a
python iu/main.py
```

> **Never run a local bot with the production token while the container is running.** Both would
> connect as IU at once, so every message and command would be answered twice. Stop the container
> first, or use a separate test bot token in your `.env`.

### 1.3 Commit, push and open a pull request

```bash
git add <the files you changed>
git commit -m "Describe what changed and why"
git push -u origin short-description-of-change
```

Open a pull request on GitHub (or run `gh pr create` if you have the GitHub CLI). CI runs
automatically and checks three things: `pylint iu`, the tests, and the 80% coverage minimum.

> **Current state:** there are no tests yet, so the test and coverage steps fail by design and CI is
> red. Until the first tests land, decide deliberately whether to merge with CI red, and re-read
> the lint result on its own. Once tests exist this should stay green.

### 1.4 Merge

When CI is green (and lint always must be), merge the pull request on GitHub, then update your
local copy:

```bash
git switch main
git pull
```

CI also runs on `main` after the merge. Check that it passed.

### 1.5 Build and push the Docker image

Prerequisites:

- Docker must be running. The Makefile starts Colima for you if it isn't (`colima start`).
- Log in to Docker Hub once (Docker remembers it afterwards): `docker login -u jonhayes37`.

From the repo root on `main`:

```bash
make build-push
```

This builds the image for `linux/amd64` (slower on an Apple-silicon Mac, since it runs under
emulation), tags it `jonhayes37/iu-bot` (the `latest` tag) and pushes it. The `.dockerignore` keeps
your `.env`, `credentials.json`, `token.json`, `.git` and `venv` out of the image.

**Recommended: keep a tag you can roll back to.** The Makefile only pushes `latest`, so each push
overwrites the previous version. Before pushing, also tag the build with the commit:

```bash
docker tag iu-bot jonhayes37/iu-bot:$(git rev-parse --short HEAD)
docker push jonhayes37/iu-bot:$(git rev-parse --short HEAD)
```

Write the tag down (in the PR or a note) so you can go back to it. See [Rolling back](#18-roll-back).

### 1.6 Update the container in Unraid

Choose a quiet moment: avoid a Listen Game reveal in progress (see
[Restarts and the Listen Game](#restarts-and-the-listen-game)).

1. Open the Unraid web UI and go to the **Docker** tab.
2. Find the IU container. Since the Docker Hub repo is private, Unraid may not be able to check
   for updates on its own. Log in to Docker Hub from the Unraid terminal first *(check)*:

   ```bash
   docker login -u jonhayes37
   ```

   Unraid runs from RAM, so this login is forgotten after a reboot. Repeat it after a reboot.
3. Click the container's icon and choose **Force Update** *(check)* (this pulls the newest image and
   recreates the container with the same settings). If that isn't offered, pull it by hand and
   then use **Restart** or **Edit → Apply**:

   ```bash
   docker pull jonhayes37/iu-bot
   ```

4. Wait for the container to show as started.

### 1.7 Verify the deploy

Open the container's logs (see [Read the logs](#3-read-the-logs)) and look for this sequence
near the top of a healthy start:

```text
Initializing databases...
All databases initialized successfully.
Persistent buttons registered.
Command tree synced to guild <your guild id>
<bot name> has connected to Discord!
Event notifier task started.
Tournament resolution task started.
Listen game reminder task started.
```

Then try something small in Discord, such as `/check-balance` in `#merch-booth`. If you added a
new command, confirm that it appears (press Ctrl/Cmd+R in Discord if it doesn't).

If a line is missing or you see errors, go to [Troubleshooting](#4-troubleshooting).

### 1.8 Roll back

If the new version misbehaves and you tagged the previous build (step 1.5):

1. In Unraid, click the container, choose **Edit**, and change the **Repository** from
   `jonhayes37/iu-bot` to `jonhayes37/iu-bot:<old tag>`.
2. Click **Apply**. Unraid recreates the container from that tag.
3. When you're ready to move forward again, change the repository back to `jonhayes37/iu-bot`.

Without a saved tag, you must revert the change in git, rebuild and push again.

Database changes are not undone by a rollback. New columns stay, which is harmless because older
code ignores them.

## 2. Unraid

### Container settings

In the Docker tab, choose the container and then **Edit**. Turn on **Advanced View** (top right)
to see every field. The settings that matter:

- **Repository:** `jonhayes37/iu-bot`.
- **Environment variables you must set:** `DISCORD_TOKEN` (the bot token) and `DISCORD_GUILD`
  (the server's ID). The image provides defaults for everything else; what each variable does is
  in the [setup guide](setup.md#3-settings-on-the-container).
- **Path mapping:** container path `/app/data` to a folder on the NAS (for example
  `/mnt/user/appdata/iu-bot`). Everything the bot remembers lives there. **If this mapping is
  missing or wrong, the bot loses its data every time the container is recreated.**
- **YouTube token:** `token.json` must be inside that data folder (the bot looks for
  `/app/data/token.json`).
- **Extra Parameters:** `--init --stop-timeout 30`. `--init` makes `docker stop` shut the bot down
  promptly, and the timeout gives it up to 30 seconds to finish.
- **Autostart:** turn on so the bot returns after a reboot.

### Restarts and the Listen Game

The bot does not lose Listen Game progress when it restarts. Rankings are saved when the listener
confirms them, and if a restart interrupts the reveal, the bot resumes it from where it stopped:
automatically within a moment of starting, or by the listener (or GM) running
`/listen-game-submit-ranking` again. A listener who is halfway through choosing songs in the
ranking screen (before pressing **Confirm**) does lose that screen and must run the command again.

### Keep appdata on fast storage

SQLite writes are slow on an array disk protected by parity. Keep the data folder on the SSD/cache
pool *(check)*, and make sure the share is not set to be moved off it by Unraid's mover.

### Times are UTC in the logs

Container logs and stored timestamps are UTC. The bot uses Eastern time for the daily heart reset
and for the December 1 start of the awards year, so those roll over at midnight Eastern, not UTC.

## 3. Read the logs

In the Unraid Docker tab, click the container's icon and choose **Logs**. Or use the Unraid
terminal:

```bash
docker ps                                  # find the container's name
docker logs --tail 200 <container>         # the last 200 lines
docker logs -f --tail 50 <container>       # follow live; Ctrl+C to stop
docker logs --since 1h <container> | grep -i error
```

The bot logs at INFO level. Problems appear as `ERROR` or `WARNING` lines, and a crash ends with a
Python traceback. Docker rotates old log lines, so if something happened days ago the evidence may
be gone. Note the time an issue happened while it's fresh.

If the container keeps restarting, its state in the Docker tab flips between started and stopped.
Read the last lines of the log, which show why it exited.

## 4. Troubleshooting

### The container starts then stops immediately

- `LoginFailure: Improper token has been passed`: `DISCORD_TOKEN` is missing or wrong. Fix it in
  Edit → Apply.
- `PrivilegedIntentsRequired`: in the Discord Developer Portal, open the bot's settings and turn
  on the **Message Content** and **Server Members** intents.
- Errors mentioning `unable to open database file` or `Failed to initialize DB`: the data folder
  is missing, not mapped, or not writable. Check the path mapping.

### Slash commands are missing or out of date

- Check the log for `Command tree synced to guild`. If you see `Failed to sync commands`, Discord
  rejected or rate-limited the sync. Restart the container to retry.
- If `DISCORD_GUILD` is not set, commands sync globally and can take a long time to appear.
- Refresh the Discord app with Ctrl/Cmd+R.

### A command says an unexpected error occurred

Find `Global App Command Error:` or a nearby `Failed to ...` line in the log, at the time you ran
the command. That line names the cause. The bot does not currently log a full traceback for
command errors, so note the command, the time and the log lines when asking for help.

### A command says it can only be used in a channel

That is expected: several commands are limited to certain channels (`#merch-booth`,
`#dispatch-news`, `#listen-game` and `#sandbox`). It is not an error.

### YouTube playlists are not updating

- `token.json missing at ...`: the token file isn't in the mapped data folder.
- `YouTube API Quota exceeded`: the daily quota is used up. It resets at midnight Pacific time.
  Songs are still saved; a Listen Game GM catches the playlist up the next day with
  `/listen-game-gm-sync-playlist`.
- `invalid_grant` or other authentication errors: the token has expired or been revoked. Renew it
  by following [YouTube credentials and quota](youtube.md#renewing-the-token). If it keeps dying
  after a week, the Google consent screen is probably still in "Testing" (see that guide).

### A tournament bracket image did not appear

Search the log for `Failed to render HTML to image` or `Failed to compile or render bracket image`.
The bracket is drawn by a headless browser inside the container, which needs enough free memory.
Restart the container and use `/force-close-round` or wait for the next check to try again.

### A Listen Game round seems stuck after a restart

Check the log for `Resuming the reveal for round`. If it isn't there, have the listener run
`/listen-game-submit-ranking`, or a GM run it, which resumes the reveal.

To look inside a database from the container's console, see [Databases](databases.md#look-inside-the-databases).

## 5. Databases

Everything about the database files is in [Databases](databases.md):

- [Looking inside them](databases.md#look-inside-the-databases), from Windows or the container.
- [Fixing their file permissions](databases.md#fix-the-file-permissions) so Windows can open them.
- [Backing up and restoring](databases.md#back-up-and-restore).
- [Adding a new database](databases.md#adding-a-new-database) and
  [changing an existing one](databases.md#changing-an-existing-database).
