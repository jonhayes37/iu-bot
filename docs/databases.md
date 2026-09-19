# Databases

The bot keeps everything it remembers in eleven small SQLite files. This guide covers what is in
them, how to look inside, how to fix their file permissions, how to back them up and restore them,
and how to add a new one. Settings and paths are in the [setup guide](setup.md); deploying and
Unraid are in the [playbook](playbook.md).

## What is stored where

All files live in the container's `/app/data` folder, which is mapped to a folder on the NAS (for
example `/mnt/user/appdata/iu-bot`).

| File | Holds | Main tables |
| --- | --- | --- |
| `merch.db` | Hearts, transactions and the Merch Booth | `users`, `transactions`, `merch_items`, `user_inventory`, `milestone_messages` |
| `listen_game.db` | The Listen Game: games, players, rounds, songs and rankings | `listen_games`, `listen_players`, `listen_rounds`, `listen_submissions`, `listen_round_rankings` |
| `tournaments.db` | Bracket tournaments, votes and voting rewards | `tournaments`, `tournament_entrants`, `tournament_matches`, `tournament_votes`, `tournament_rewards_ledger` |
| `lists.db` | List events and members' submissions | `list_events`, `list_submissions` |
| `releases.db` | Links posted in `#new-releases` and the yearly playlists | `new_releases`, `youtube_playlists` |
| `roles.db` | The self-assign roles, their aliases and the `#roles` messages | `role_categories`, `assignable_roles`, `role_aliases`, `display_messages` |
| `top_songs.db` | End of year Top 25 lists and honourable mentions | `eoy_top_songs` |
| `hall_of_fame.db` | Hall of Fame nominations, finalists and votes | `hall_of_fame_nominations`, `hof_official_nominees`, `hall_of_fame_votes` |
| `hmas.db` | HallyU Music Awards categories, nominations, finalists, votes and suggestions | `hma_categories`, `hma_nominations`, `hma_final_nominees`, `hma_votes`, `hma_category_suggestions` |
| `biases.db` | Members' bias cards | `ultimate_biases`, `artist_biases` |
| `bot.db` | The saved status message | `statuses` |

Next to them is `token.json`, the YouTube sign-in ([youtube.md](youtube.md)). Losing the folder loses
all of this, which is why the [backups](#back-up-and-restore) below matter.

The databases are created and brought up to date automatically each time the bot starts. You never
create them by hand.

## Look inside the databases

### From Windows (DB Browser for SQLite or similar)

1. **Fix the file permissions** first, if the files aren't visible or won't open (next section).
2. **Work on a copy.** Copy the `.db` file off the share and open the copy. That way you can't lock
   or corrupt the live file, and the bot is never held up.
3. If you must open the file on the share, open it **read-only** (in DB Browser for SQLite:
   File → Open Database Read Only) and close it when you're done.
4. **Don't edit a live database from Windows.** Editing over the network while the bot runs risks
   locks and corruption. To change data, stop the container, edit a backed-up copy, put it back and
   start the container.
5. A `-journal` file next to a database is SQLite working. Leave it alone.

### From the container's console

The image has no `sqlite3` program, but it has Python. Open the container's **Console** in the
Docker tab and run:

```bash
python - <<'EOF'
import sqlite3
db = sqlite3.connect("/app/data/merch.db")
for row in db.execute("SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT 10"):
    print(row)
EOF
```

Only read (`SELECT`) while the bot is running.

### Useful queries

| Question | Database | Query |
| --- | --- | --- |
| Who has the most hearts? | `merch.db` | `SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT 10;` |
| What happened to a balance recently? | `merch.db` | `SELECT timestamp, sender_id, receiver_id, amount, reason FROM transactions ORDER BY id DESC LIMIT 20;` |
| Where is the Listen Game up to? | `listen_game.db` | `SELECT round_id, host_id, status, reveal_step FROM listen_rounds ORDER BY round_id DESC LIMIT 5;` |
| Listen Game scores | `listen_game.db` | `SELECT user_id, score FROM listen_players WHERE game_id = (SELECT MAX(game_id) FROM listen_games) ORDER BY score DESC;` |
| Tournaments and their state | `tournaments.db` | `SELECT tournament_id, name, status FROM tournaments;` |
| Release links not yet on the playlist | `releases.db` | `SELECT video_id, original_url FROM new_releases WHERE processed = 0;` |
| The saved status | `bot.db` | `SELECT * FROM statuses ORDER BY id DESC LIMIT 3;` |

Discord user IDs are stored as numbers. In Discord, right-click a member with Developer Mode on and
choose Copy User ID to look one up.

## Fix the file permissions

The bot runs as `root` inside the container, so the files it creates are owned by `root`. Windows
then can't see or open them, or opens them read-only. Fix it in the Unraid terminal (adjust the
path to your data folder):

```bash
cd /mnt/user/appdata/iu-bot
ls -l                                   # look at the owner and permissions
chown -R nobody:users .                 # the account Unraid's SMB shares use
chmod -R u+rwX,g+rwX,o+rX .             # owner and group read/write, others read
```

Unraid also has a built-in **Tools → New Permissions** page that resets ownership and permissions
on shares. It does the same job for the whole share; stop the Docker service or the container first.
*(Check the exact wording on your version.)*

Make sure the `appdata` share is visible to Windows (**Shares → appdata → SMB**). For a private
share, use a Windows login that has read/write access to it.

**A new database needs this again.** The bot creates its file the next time it starts, as `root`, so
repeat the two commands afterwards.

> **Don't run the container as a different user with `--user`.** It looks like a permanent fix, but
> the image installs its headless browser (used for tournament brackets) under `/root`, so a
> non-root user can't launch it and bracket images would break. A better permanent fix is a small
> code change so the bot creates its files with open permissions (setting a umask at startup).

## Back up and restore

Back up **the whole data folder**: all eleven `.db` files, and `token.json`.

### One consistent copy (recommended)

Some changes span two files at once (a tournament vote reward changes both `tournaments.db` and
`merch.db`, and a list with a bonus pick changes both `lists.db` and `merch.db`). The bot makes those
all-or-nothing, but a backup only keeps them consistent if the files are copied at the same moment.
So for a backup you can rely on, stop the container, copy the folder, and start it again:

```bash
docker stop iu-bot
cp -a /mnt/user/appdata/iu-bot /mnt/user/backups/iu-bot-$(date +%F)
docker start iu-bot
```

Use your container's name and your own backup location. The Listen Game reveal resumes by itself
after a restart, so this is safe, but it is kinder not to do it in the middle of one.

### Copy while the bot is running

This uses SQLite's own backup, which is safe to do on a live database. Each file is a consistent
snapshot, but the files are taken a moment apart. The snapshots go into a dated folder inside the
data folder:

```bash
docker exec -i iu-bot python - <<'EOF'
import datetime, pathlib, sqlite3

data = pathlib.Path("/app/data")
target = data / "backups" / datetime.date.today().isoformat()
target.mkdir(parents=True, exist_ok=True)

for path in sorted(data.glob("*.db")):
    source = sqlite3.connect(path)
    backup = sqlite3.connect(target / path.name)
    source.backup(backup)
    backup.close()
    source.close()
    print("backed up", path.name)
EOF
```

Delete old ones so they don't pile up (this removes backup folders older than 14 days):

```bash
find /mnt/user/appdata/iu-bot/backups -mindepth 1 -maxdepth 1 -type d -mtime +14 -exec rm -r {} +
```

### Schedule it and keep a copy elsewhere

Backups that live on the same disk as the data don't survive that disk failing. In Unraid, a common
way to run the commands above every night is the **User Scripts** plugin (from Community
Applications), and the **Appdata Backup** plugin can copy the whole appdata folder on a schedule.
Whatever you use, also copy the result to somewhere off the NAS from time to time. *(Both are
optional add-ons; check their current names in Community Applications.)*

### Restore

1. Stop the container.
2. Copy the backed-up `.db` files (and `token.json`) back into the data folder, replacing the
   current ones. Restore all the databases from the same backup.
3. Fix the file permissions if you use Windows tools, then start the container.
4. Check the logs for the usual healthy start.

## Adding a new database

For a new feature that needs its own file:

1. Add a member to the `Database` list in [iu/config.py](../iu/config.py). Its value is the schema
   file name (`EXAMPLE = "example"` means `iu/db/schema/example.sql`, and the environment variable is
   `DB_PATH_EXAMPLE`).
2. Write the schema in `iu/db/schema/example.sql`, using `CREATE TABLE IF NOT EXISTS`.
3. Add `ENV DB_PATH_EXAMPLE=${DATA_DIR}/example.db` to the Dockerfile. If you override paths on the
   Unraid container or in your local `.env`, add it there too.
4. Write the data functions in `iu/db/example.py` using `db_connection(Database.EXAMPLE)`. They
   raise on failure and return `None`, `[]` or a bool for real outcomes (the contract is in
   `iu/db/connection.py`).
5. Build and deploy. The bot creates the file on its first start.
6. [Fix the permissions](#fix-the-file-permissions) of the new file if you use Windows tools.
7. Add the file to the table at the top of this page.

A feature that must change several databases at once can attach the others to one connection
(`db_connection(Database.A, attach=(Database.B,))`); see `iu/db/lists.py` for an example.

## Changing an existing database

The schema files use `CREATE TABLE IF NOT EXISTS`, which does nothing to a table that already
exists, so a change to a live database needs a migration that runs at startup:

- **A new table or index:** add it to the schema file. It is created the next time the bot starts.
- **A new column:** add it to the schema file for new installs, and add an entry to
  `COLUMN_MIGRATIONS` in `iu/db/initialize.py` so existing databases get it.
- **Anything else** (removing or changing a constraint, changing a column's type): SQLite can't do
  this in place. Rebuild the table inside one transaction, and only when needed. See
  `_allow_several_releases_per_message` in `iu/db/initialize.py` for the pattern: it detects the
  old shape, saves a copy of the database first, rebuilds, and does nothing afterwards.

That migration leaves a safety copy named `releases.db.before-release-migration` in the data
folder. Once the bot has run fine for a while, you can delete it.

Some rules for anyone writing queries:

- Foreign keys are enforced and `ON DELETE CASCADE` really cascades, so never use
  `INSERT OR REPLACE` on a table that other tables refer to (it deletes the old row first and wipes
  its children); use `INSERT ... ON CONFLICT DO UPDATE`.
- Keep the default journal mode. Don't switch the databases to WAL, which would make transactions
  across two files no longer all-or-nothing.
