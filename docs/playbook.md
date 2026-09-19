# IU bot maintainer playbook

Step-by-step procedures for changing, deploying and troubleshooting the bot. For what the bot
does, see the [README](../README.md). For code conventions, see [CLAUDE.md](../CLAUDE.md).

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
Persistent views successfully restored.
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
  (the server's ID). The image already provides defaults for `TOKEN_DIR`, `HALLYU_ID`, `DATA_DIR`
  and every `DB_PATH_*` variable, so only override those on purpose.
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
- `invalid_grant` or other authentication errors: the token has expired or been revoked. On your own
  computer with `credentials.json` in the repo folder, run `python iu/scripts/generate_token.py`,
  sign in when the browser opens, copy the new `token.json` into the data folder on the NAS, and
  restart the container. If this keeps happening within a week, check in the Google Cloud Console
  that the OAuth consent screen is published rather than in "Testing" (Google expires
  Testing-mode tokens after 7 days).

### A tournament bracket image did not appear

Search the log for `Failed to render HTML to image` or `Failed to compile or render bracket image`.
The bracket is drawn by a headless browser inside the container, which needs enough free memory.
Restart the container and use `/force-close-round` or wait for the next check to try again.

### A Listen Game round seems stuck after a restart

Check the log for `Resuming the reveal for round`. If it isn't there, have the listener run
`/listen-game-submit-ranking`, or a GM run it, which resumes the reveal.

### Look inside the databases from the container

Open the container's **Console** (Docker tab, container icon, Console). The image has no `sqlite3`
program, but Python is there:

```bash
python - <<'EOF'
import sqlite3
db = sqlite3.connect('/app/data/listen_game.db')
for row in db.execute("SELECT round_id, host_id, status, reveal_step FROM listen_rounds ORDER BY round_id DESC LIMIT 5"):
    print(row)
EOF
```

Only read (`SELECT`) in the console while the bot is running. To change data, stop the container
first and take a backup (see below).

## 5. View the databases in a Windows app

The `.db` files are created by the bot, which runs as `root` inside the container, so they usually
end up owned by `root` with permissions that let other users read but not write, or that block
your Windows login altogether. The usual symptom is that a viewer such as **DB Browser for
SQLite** can't see or open the files, or opens them read-only or with an error.

### Fix the permissions once

In the Unraid terminal (adjust the path to your data folder):

```bash
cd /mnt/user/appdata/iu-bot
ls -l                                   # look at the owner and permissions
chown -R nobody:users .                 # the account Unraid's SMB shares use
chmod -R u+rwX,g+rwX,o+rX .             # owner and group read/write, others read
```

(Unraid also has a built-in **Tools → New Permissions** page that resets ownership and permissions
on shares. It does the same job for the whole share; stop the Docker service or the container
first.) *(check)*

Make sure the `appdata` share is visible to Windows (**Shares → appdata → SMB**). For a private
share, use a Windows login that has read/write access to it.

**New databases need this again.** When you add a new database, the bot creates the file the next
time it starts, as `root`, so repeat the two commands above afterwards.

> **Don't run the container as a different user with `--user`.** It looks like a permanent fix, but
> the image installs its headless browser (used for tournament brackets) under `/root`, so a
> non-root user can't launch it and bracket images would break. A better permanent fix is a small
> code change so the bot creates its files with open permissions (setting a umask at startup);
> ask for that if the manual step becomes a chore.

### Open them safely

- **Prefer a copy.** In Windows, copy the `.db` file off the share (or copy it on the NAS) and open
  the copy. That way you can't lock or corrupt the live file, and the bot is never held up.
- If you must open the file on the share, open it **read-only** (in DB Browser for SQLite:
  File → Open Database Read Only) and close it when you're done.
- **Don't edit a live database from Windows.** Editing over the network while the bot is running
  risks locks and corruption. To change data, stop the container, edit a backed-up file, then
  start the container again.
- Only the `.db` file matters. If you see a `-journal` file next to it, that is SQLite working;
  leave it alone.

### Back up before changing anything

Stop the container, then copy the whole data folder, or copy a database while it's running using
SQLite's own backup, which is safe:

```bash
python - <<'EOF'
import sqlite3
src = sqlite3.connect('/app/data/merch.db')
dst = sqlite3.connect('/app/data/merch-backup.db')
src.backup(dst)
EOF
```

The databases hold the hearts economy, listen game, lists and awards data, so it's worth copying
the data folder somewhere off the NAS from time to time.
