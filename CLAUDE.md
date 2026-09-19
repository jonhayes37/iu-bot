# IU bot

Discord bot (discord.py 2.x, Python 3.14) for the HallyU server. See [README.md](README.md) for the user-facing feature list; when you add, rename or change a slash command, update its README section too (every command should appear there).

## Layout

All code lives in `iu/` and imports are **relative to `iu/`** (`from db.lists import ...`, not `from iu.db.lists import ...`). `iu/` must be on `sys.path` to import anything.

- `config.py` — all configuration: env var accessors, the `Database` enum (path + schema per SQLite DB), `Channel` / `Role` name enums, Discord IDs, custom emoji, links, `MEDIA_DIR`. Import from here instead of hard-coding any of these.
- `main.py` — entry point, only `main()`: logging, SIGTERM handling, `initialize_databases()`, then `IUBot().run(...)`. Importing it has no side effects.
- `bot.py` — `IUBot(discord.Client)`: intents, command registration, `setup_hook` (persistent views + command sync, once per process), `on_ready` (starts background tasks, sets presence) and thin event routing to `triggers/`. Creating an `IUBot()` doesn't connect to anything.
- `commands/` — slash command handlers (`@app_commands.command`). Thin: validate, call `db/`, respond. **Every top-level command defined in a `commands/*.py` module is registered automatically** by `commands/registry.py` (no list to update).
- `db/` — one module per SQLite database, plain sync functions. `db/schema/*.sql` are the schemas (applied with `CREATE TABLE IF NOT EXISTS` on every startup). `db/connection.py` has `db_connection(Database.X)` and `ensure_column()`; `db/initialize.py` creates the databases from the schemas and holds `COLUMN_MIGRATIONS`.
- `ui/` — discord `View`/`Modal` classes, plus `bracket_renderer.py` (Playwright + Jinja2 -> PNG).
- `tasks/` — `tasks.loop` background jobs (listen game reminders, tournament resolution, scheduled events).
- `triggers/` — event-driven handlers called from `bot.py` (`on_message`, member join, reactions, ...).
- `services/youtube.py` — YouTube Data API client (one client per thread; the HTTP layer isn't thread-safe).
- `utils/` — pure helpers (`strings.py`, `validation.py`, `end_of_year.py`).

## Commands

```bash
pip install -e . && pip install -r requirements-dev.txt  # what CI does (runtime deps + dev tools)
pylint iu                                              # lint (config in .pylintrc, max line 120)
pytest --cov=iu                                        # tests; CI then requires coverage >= 80%
make build-push                                        # docker build (linux/amd64), tag, push jonhayes37/iu-bot
python iu/main.py                                      # run locally (needs env vars below)
```

CI ([.github/workflows/ci.yaml](.github/workflows/ci.yaml)) runs on every PR and every push to `main`: pylint, pytest with coverage, and `coverage report --fail-under=80` (which runs even if the tests fail).

Deploying, Unraid, logs and database access are covered in [docs/playbook.md](docs/playbook.md).

**After finishing any set of code changes, run `pylint iu` and fix everything it reports before calling the work done** (it must exit 0, since CI fails on any message). Don't silence a finding with `# pylint: disable` or by editing `.pylintrc` unless the user agrees; fix the code instead. The size/complexity checks (`too-many-*`) and `duplicate-code` are disabled in `.pylintrc` because existing handlers exceed them, so new code shouldn't rely on that as a reason to write sprawling functions.

## Environment

Read through `config.py` (never call `os.getenv` elsewhere): `DISCORD_TOKEN`, `DISCORD_GUILD`, `HALLYU_ID` (the admin's user ID), `TOKEN_DIR` (path to the YouTube OAuth `token.json`), and one `DB_PATH_<NAME>` per `Database` member (BIASES, BOT, HALL_OF_FAME, HMAS, LISTEN_GAME, LISTS, MERCH, RELEASES, ROLES, TOP_SONGS, TOURNAMENTS). The Dockerfile sets the DB paths under `/app/data`. `.env`, `credentials.json`, and `token.json` are gitignored; never commit them. Nothing loads `.env` inside the container; the values come from the container's environment.

## Conventions and gotchas

- **Blocking work must not run on the event loop.** sqlite and YouTube calls are synchronous; from async code wrap them in `asyncio.to_thread(...)` (see `triggers/releases.py`, `commands/listen_game_gm.py`). Don't call `time.sleep` or blocking I/O directly in a command or task.
- **DB error handling is inconsistent.** Most `db/` functions use `try: with db_connection(Database.X) as conn: ... except Exception: logger.error(...); return False/None/[]`, but `db/merch.py` and parts of `db/releases.py` / `db/hmas.py` let exceptions propagate. Check the function before assuming either. `db_connection()` commits on clean exit, rolls back on exception, and raises `DatabaseNotConfiguredError` when the path is unset. Returning `None` can mean "error" or "no result" (e.g. `skip_game_turn_db`).
- **Config is read when used, not at import.** `db_connection(Database.MERCH)` looks up `DB_PATH_MERCH` on every call, so tests just `monkeypatch.setenv("DB_PATH_MERCH", ...)`. Channel and role names (`Channel.LISTEN_GAME`, `Role.LISTEN_GAME_GM`) are `StrEnum`s: use them for `discord.utils.get(..., name=...)`, `validate_channel` and `has_role`, not string literals.
- **Adding a database:** add a member to `Database` in `config.py` (the value is the schema file name), create `db/schema/<value>.sql`, and set `DB_PATH_<NAME>` in the Dockerfile, the Unraid container and `.env`. `initialize_databases()` picks it up automatically; use `COLUMN_MIGRATIONS` for later column additions.
- **Schema changes:** `CREATE TABLE IF NOT EXISTS` won't alter existing tables. Add new columns by adding an entry to `COLUMN_MIGRATIONS` in `db/initialize.py` (see the `tournaments.description` example). Anything else (dropping or changing a constraint) needs a table rebuild inside one transaction; see `_allow_several_releases_per_message` in `db/initialize.py` for the pattern (detect, back up, rebuild, no-op afterwards) in addition to editing the `.sql`. New indexes can just be `CREATE INDEX IF NOT EXISTS` in the schema.
- **Channel-restricted commands** use `restricted = await validate_channel(interaction, 'name'); if restricted: return`. It returns `True` when it already sent the rejection.
- **Persistent views** (buttons that must survive a restart) need explicit `custom_id`s and a `self.add_view(...)` in `IUBot._register_persistent_views` (called from `setup_hook`). Only `JoinGameView`, the EOY/HMA hubs are registered. `ListenGameRankingView` is intentionally not; its in-progress state is in memory and lost on restart (host re-runs `/listen-game-submit-ranking`).
- **Background loops:** put `@keep_running` (from `tasks/common.py`) directly under `@tasks.loop(...)`. An unhandled exception otherwise stops a loop permanently. Keep per-item failures (a failed DM, one bad row) local so they don't skip the rest of the tick.
- **Money and rewards must be idempotent.** `db/merch.award_once(marker, ...)` pays only if no transaction with that marker exists (the marker is appended to the reason); `get_award_recipient(marker)` looks it up. Tournament voting rewards pay first, then call `mark_reward_claimed`; `process_user_vote` no longer writes the ledger, so a failed payment retries on the user's next vote. The tournament finale marks the tournament completed only after the announcement is posted, and reuses the raffle winner recorded under `[raffle:<tournament_id>]`.
- **Polls:** tournament votes go through `triggers/polls.py` (add and remove), which ignores polls outside `#tournaments`. Match tallying (`tasks/tournaments._process_expired_matches`) closes an open poll first and only reads final counts.
- **Return values that used to be ambiguous:** `services.youtube.get_playlist_video_ids` returns `None` when the playlist can't be read (never an empty set); `db.listen_game.skip_game_turn_db` and `get_next_host_id_db` raise on DB errors so `None` always means "game over"; `db.releases.add_new_release` returns an `AddResult` (a `PENDING` release is retried).
- **Foreign keys are enforced** (`db_connection` turns them on for every connection, and startup logs any existing rows that break them). That means `ON DELETE CASCADE` really cascades, so never use `INSERT OR REPLACE` on a table that other tables reference (it deletes the old row first and wipes its children); use `INSERT ... ON CONFLICT DO UPDATE`, as `register_new_role` does. Connections wait up to 10 seconds for a lock and are closed after each `with db_connection(...)` block. WAL mode was tried and not adopted (no gain with a connection per call).
- **Reactions are handled without network calls where possible** (`triggers/merch.py`): the heart reward uses `payload.message_author_id`, reaction counts come from `client.cached_messages`, and a message that isn't cached is fetched at most twice (once to learn its count, once at 5 reactions). Don't add a `fetch_message` per reaction.
- **YouTube lookups are batched:** use `get_video_snippets(ids)` (50 videos per request, 1 quota unit per request) whenever you have several videos; `get_video_title` is the single-video wrapper. Backfills process messages in batches of 50 for this reason.
- **Listen game round statuses:** `setting_theme` -> `submitting` -> `ranking` -> `revealing` -> `completed` (or `skipped`). Confirming rankings atomically saves points and moves the round to `revealing` (`save_round_results_db`), so points can only be applied once. `services/listen_game_reveal.py` then posts the reveal in the background and records progress in `listen_rounds.reveal_step`; if the bot restarts mid-reveal, the hourly `check_listen_game_reminders` task (or the listener/GM re-running `/listen-game-submit-ranking`) resumes it. Keep new round-status changes guarded with `WHERE status = ?`.
- `services/listen_game_playlist.py` is the one place that adds a submission to a round's YouTube playlist (used by both `submit_song` and GM `force-submit`). Its YouTube calls run via `asyncio.to_thread`, so both commands hold `SUBMISSION_LOCK` for the whole check-claimed / update-playlist / save sequence; keep any new code that writes submissions inside that lock.
- When a user's text may be long (list echoes, exports), attach it with `utils.discord_files.text_file` rather than pasting it into a message (2000 character limit).
- `ui/bracket_renderer.py` keeps one shared Chromium instance for the process lifetime; the Docker image needs Playwright's Chromium installed.
- `ui/test_render.py` is a manual script that builds `preview.html` from the Jinja template. It is **not** a pytest test.

## Testing

`pytest`, `pytest-asyncio` (`asyncio_mode = "auto"` in [pyproject.toml](pyproject.toml)), `pytest-cov`, and `parameterized` are the intended tools. There are no tests yet.

Setup already in place: `pytest`, `pytest-asyncio` and `pytest-cov` are in `requirements-dev.txt` (which includes `requirements.txt`; the Docker image installs only `requirements.txt`), and `pythonpath = ["iu"]` is set in [pyproject.toml](pyproject.toml) so `from db.x import ...` resolves in tests.

Still to do when adding the first tests:

- Create a `tests/` directory and add `testpaths = ["tests"]` to `[tool.pytest.ini_options]` (adding it before the directory exists only produces a warning).
- Add `addopts = "--import-mode=importlib"` to `[tool.pytest.ini_options]` (see layout below).
- Move `iu/ui/test_render.py` out of the package (e.g. `scripts/`): it is a manual script that pytest would try to collect.
- CI currently fails by design: with no tests pytest exits non-zero (no tests ran) and coverage is far below the 80% gate.

### Test layout

Tests live in a top-level `tests/` directory that **mirrors `iu/`**, not next to the source (unlike Go's `foo_test.go`):

```text
iu/db/lists.py          ->  tests/db/test_lists.py
iu/commands/merch.py    ->  tests/commands/test_merch.py
iu/utils/validation.py  ->  tests/utils/test_validation.py
                            tests/conftest.py            # shared fixtures (e.g. temp SQLite DB)
                            tests/db/conftest.py         # fixtures used only by that folder
```

- **Do not colocate tests inside `iu/`.** CI runs `pylint iu` and `pytest --cov=iu`, and the Docker build copies the tree, so colocated tests would be linted, counted in the coverage denominator and shipped in the image. `.dockerignore` already excludes a top-level `tests/`.
- **No `__init__.py` files in `tests/`, and use `--import-mode=importlib`.** Otherwise same-named files (`tests/db/test_lists.py` vs `tests/ui/test_lists.py`) collide, and a `tests/db/` package could shadow the real `db` package that the code imports as `from db.lists import ...`.
- Name files `test_<module>.py` and functions `test_<behaviour>`. Use `@pytest.mark.parametrize` (or `parameterized`) for table-driven cases, the closest match to Go table tests.
- Put fixtures shared across files in `tests/conftest.py`; folder-specific ones in that folder's `conftest.py`.

Guidelines for writing tests:

- **Test `bot.py` and `db/initialize.py` directly**, not `main.py`. `IUBot()` can be constructed without connecting; patch `tree.sync`, `add_view` and the task `.start` methods (or call handlers such as `triggers/polls.handle_poll_vote` with a mock client) rather than running the bot. `main.py` only wires things together, so it needs no tests.
- **DB tests use real SQLite, not mocks.** Use `tmp_path`, apply the matching `db/schema/<name>.sql` with `executescript`, then `monkeypatch.setenv("DB_PATH_X", str(path))` (config is read on each call, so no module attribute needs patching). Prefer this over mocking `sqlite3`; the schemas contain constraints and cascades worth exercising.
- **Pure logic is the easiest coverage:** `utils/*`, `utils/validation.sanitize_list`, `triggers/releases.get_eligible_year`, the `_process_release_url` / `_sync_missing_videos` sync workers, bracket data building. Use `parameterized` for table-driven cases.
- **Discord objects:** commands are `app_commands.Command` objects; call the underlying coroutine with `.callback(interaction, ...)` and a `unittest.mock.AsyncMock`/`MagicMock` interaction (`interaction.response.send_message`, `.followup.send`, `.channel.name`, `.user.id`). Assert on what was sent (and `ephemeral=`), and on DB state.
- **Mock external services, never hit them:** patch `services.youtube` functions (`add_video_to_playlist`, `get_video_publish_date`, ...) and never load `token.json`. `_browser_cache` in `bracket_renderer` should be patched so tests don't launch Chromium.
- Time-dependent logic (deadlines, reminders, award year) should take or patch `datetime` so tests are deterministic.
