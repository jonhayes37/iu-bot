# IU bot

Discord bot (discord.py 2.x, Python 3.14) for the HallyU server. See [README.md](README.md) for the user-facing feature list; when you add, rename or change a slash command, update its README section too (every command should appear there).

## Layout

All code lives in `iu/` and imports are **relative to `iu/`** (`from db.lists import ...`, not `from iu.db.lists import ...`). `iu/` must be on `sys.path` to import anything.

- `config.py` — all configuration: env var accessors, the `Database` enum (path + schema per SQLite DB), `Channel` / `Role` name enums, Discord IDs, custom emoji, links, `MEDIA_DIR`. Import from here instead of hard-coding any of these.
- `main.py` — entry point, only `main()`: logging, SIGTERM handling, `initialize_databases()`, then `IUBot().run(...)`. Importing it has no side effects.
- `bot.py` — `IUBot(discord.Client)`: intents, command registration, `setup_hook` (persistent views + command sync, once per process), `on_ready` (starts background tasks, sets presence) and thin event routing to `triggers/`. Creating an `IUBot()` doesn't connect to anything.
- `commands/` — slash command handlers (`@app_commands.command`). Thin: validate, call `db/`, respond. **Every top-level command defined in a `commands/*.py` module is registered automatically** by `commands/registry.py` (no list to update).
- `db/` — one module per SQLite database, plain sync functions. `db/schema/*.sql` are the schemas (applied with `CREATE TABLE IF NOT EXISTS` on every startup). `db/connection.py` has `db_connection(Database.X)` (whose docstring defines the error contract) and `ensure_column()`; `db/errors.py` has `InvalidStateError`; `db/initialize.py` creates the databases from the schemas and holds `COLUMN_MIGRATIONS`.
- `ui/` — discord `View`/`Modal` classes and dynamic buttons, plus `bracket_renderer.py` (Playwright + Jinja2 -> PNG). `ui/base.py` has `SafeView`, `SafeModal`, `reports_errors` and `report_interaction_error`, the one place errors are reported to users.
- `tasks/` — `tasks.loop` background jobs (listen game reminders, tournament resolution, scheduled events).
- `triggers/` — event-driven handlers called from `bot.py` (`on_message`, member join, reactions, ...).
- `services/` — `youtube.py` (YouTube Data API client, one client per thread; the HTTP layer isn't thread-safe), and the listen game helpers: `listen_game.py` (`require_active_round`, `send_dm`, `update_submission_tracker`), `listen_game_playlist.py`, `listen_game_reveal.py`.
- `utils/` — pure helpers (`strings.py`, `validation.py`, `end_of_year.py`).

## Commands

```bash
uv sync                    # create .venv from uv.lock (runtime deps + dev tools); install uv: https://docs.astral.sh/uv/
uv run pylint iu tests     # lint the code and the tests (config in .pylintrc, max line 120; run from the repo root)
uv run pytest --cov=iu     # tests; CI then requires coverage >= 80%
uv add <package>           # add a runtime dependency (edits pyproject.toml and uv.lock); add --dev for a dev tool
uv lock --upgrade          # refresh every locked version (review the diff, run the checks)
make build-push           # docker build (linux/amd64), tag, push jonhayes37/iu-bot (:latest and :<commit>)
uv run python iu/main.py   # run locally (needs env vars below)
```

Dependencies are managed with uv: direct dependencies live in [pyproject.toml](pyproject.toml) (`[project] dependencies`, and the `dev` group for pylint/pytest/etc.), and `uv.lock` pins every transitive version. **Commit `uv.lock` with any change to `pyproject.toml`.** There is no `requirements.txt`. The Docker image installs only the runtime dependencies from the lock (`uv sync --frozen --no-dev`). `playwright` is pinned by hand because the wheel and the Chromium the image downloads must match; Dependabot ([.github/dependabot.yml](.github/dependabot.yml)) proposes the other updates weekly.

CI ([.github/workflows/ci.yaml](.github/workflows/ci.yaml)) runs on every PR and every push to `main`: `uv sync --frozen`, pylint, pytest with coverage, `coverage report --fail-under=80` (which runs even if the tests fail), and a `pip-audit` scan of the locked runtime dependencies.

Deploying, Unraid and logs are covered in [docs/playbook.md](docs/playbook.md). Setup facts (Discord app, required channels/roles, settings) are in [docs/setup.md](docs/setup.md), YouTube credentials and quota in [docs/youtube.md](docs/youtube.md), and database inspection, permissions, backups and adding a new database in [docs/databases.md](docs/databases.md). Keep them in step with changes: a new channel or role name goes in `config.py` and `docs/setup.md`; a new database goes in `docs/databases.md`.

**After finishing any set of code changes, run `pylint iu tests` and fix everything it reports before calling the work done** (it must exit 0, since CI fails on any message). Don't silence a finding with `# pylint: disable` or by editing `.pylintrc` unless the user agrees; fix the code instead. The size/complexity checks (`too-many-*`) and `duplicate-code` are disabled in `.pylintrc` because existing handlers exceed them, so new code shouldn't rely on that as a reason to write sprawling functions.

## Environment

Read through `config.py` (never call `os.getenv` elsewhere): `DISCORD_TOKEN`, `DISCORD_GUILD`, `HALLYU_ID` (the admin's user ID), `TOKEN_DIR` (path to the YouTube OAuth `token.json`), optional `LOG_LEVEL` (default INFO), `HEARTBEAT_PATH` (the healthcheck's heartbeat file, set by the Dockerfile), and one `DB_PATH_<NAME>` per `Database` member (BIASES, BOT, HALL_OF_FAME, HMAS, LISTEN_GAME, LISTS, MERCH, RELEASES, ROLES, TOP_SONGS, TOURNAMENTS). The Dockerfile sets the DB paths under `/app/data`. `.env`, `credentials.json`, and `token.json` are gitignored; never commit them. Nothing loads `.env` inside the container; the values come from the container's environment.

## Conventions and gotchas

- **Blocking work must not run on the event loop.** sqlite and YouTube calls are synchronous; from async code wrap them in `asyncio.to_thread(...)` (see `triggers/releases.py`, `commands/listen_game_gm.py`). Don't call `time.sleep` or blocking I/O directly in a command or task.
- **Error contract for `db/`** (documented in `db/connection.py`): a function returns normally when it ran and its result describes the outcome (`None`/`[]` for nothing found, a bool for "did a row change", an enum when there are several outcomes). When the database can't be read or written it **raises** `sqlite3.Error` (`DatabaseNotConfiguredError` is one) instead of logging and returning a fallback. Expected constraint violations ("already registered") are caught inside the function and returned as an outcome. Don't wrap `db/` calls in `try/except` to show `Database error: {ex}`: errors are reported once, by the global command error handler (`bot.on_app_command_error`), `SafeView`/`SafeModal.on_error`, or `@reports_errors` on dynamic-item callbacks, which log the traceback and tell the user. A form that holds text the user typed overrides `on_error` and passes `keep_text=` so the text is handed back. Event handlers and background tasks are the other boundary (`@keep_running`, per-item try/except)."
- **All views and modals subclass `SafeView` / `SafeModal`** (`ui/base.py`) so their errors are reported. discord.py only logs errors from dynamic items and drops them, so their callbacks are decorated with `@reports_errors`.
- **Cross-feature transactions:** `db_connection(Database.A, attach=(Database.B,))` opens B in the same connection (query it as `b.table`), so one transaction can change both files and is all-or-nothing (see `db/lists.save_submission` with a perk, and `db/tournaments.claim_round_reward`). This only works in the default rollback-journal mode, so **do not switch the databases to WAL**. Take the write lock first with `conn.execute("BEGIN IMMEDIATE")` when you read then write.
- **Config is read when used, not at import.** `db_connection(Database.MERCH)` looks up `DB_PATH_MERCH` on every call, so tests just `monkeypatch.setenv("DB_PATH_MERCH", ...)`. Channel and role names (`Channel.LISTEN_GAME`, `Role.LISTEN_GAME_GM`) are `StrEnum`s: use them for `discord.utils.get(..., name=...)`, `validate_channel` and `has_role`, not string literals.
- **Adding a database:** add a member to `Database` in `config.py` (the value is the schema file name), create `db/schema/<value>.sql`, and set `DB_PATH_<NAME>` in the Dockerfile, the Unraid container and `.env`. `initialize_databases()` picks it up automatically; use `COLUMN_MIGRATIONS` for later column additions.
- **Schema changes:** `CREATE TABLE IF NOT EXISTS` won't alter existing tables. Add new columns by adding an entry to `COLUMN_MIGRATIONS` in `db/initialize.py` (see the `tournaments.description` example). Anything else (dropping or changing a constraint) needs a table rebuild inside one transaction; see `_allow_several_releases_per_message` in `db/initialize.py` for the pattern (detect, back up, rebuild, no-op afterwards) in addition to editing the `.sql`. New indexes can just be `CREATE INDEX IF NOT EXISTS` in the schema.
- **Respond within 3 seconds.** Discord drops a slash command that hasn't been answered in 3 seconds (the user sees "The application did not respond" and any later reply fails with 10062). Do the quick checks first and reply to those directly (so errors can be ephemeral), but `await interaction.response.defer(...)` *before* anything that touches the network: a file upload (`commands/biases._send_with_image`), YouTube, several Discord API calls, or the browser. Then answer with `interaction.followup.send`. Every command must send some reply; don't defer everything, since a deferred response can't change between public and ephemeral.
- **Channel-restricted commands** use `restricted = await validate_channel(interaction, 'name'); if restricted: return`. It returns `True` when it already sent the rejection.
- **Persistent buttons:** a button whose ID carries state (a year, an event) is a `discord.ui.DynamicItem` with a regex template (`ui/lists.SubmitListButton`, the end-of-year buttons); register the class once in `IUBot._register_persistent_views` and it handles every year/event, including messages posted before a restart. Static buttons (`JoinGameView`) are added with `add_view`. The listener's in-progress ranking is saved to `listen_round_rankings` as they go, so a restart loses nothing: they re-run `/listen-game-submit-ranking` and carry on.
- **Background loops:** put `@keep_running` (from `tasks/common.py`) directly under `@tasks.loop(...)`. An unhandled exception otherwise stops a loop permanently. Keep per-item failures (a failed DM, one bad row) local so they don't skip the rest of the tick.
- **Money and rewards must be idempotent.** `db/merch.get_award_recipient(marker)` finds who a one-off award (marked in the transaction's reason, e.g. `[raffle:<tournament_id>]`) was already paid to. Tournament voting rewards are paid and recorded in one cross-database transaction (`claim_round_reward`), so they can't be paid twice or lost; a failed payment retries on the user's next vote. The tournament finale marks the tournament completed only after the announcement is posted, and reuses the raffle winner recorded under its marker.
- **Polls:** tournament votes go through `triggers/polls.py` (add and remove), which ignores polls outside `#tournaments`. Match tallying (`tasks/tournaments._process_expired_matches`) closes an open poll first and only reads final counts.
- **Return values that used to be ambiguous:** `services.youtube.get_playlist_video_ids` returns `None` when the playlist can't be read (never an empty set); `db.listen_game.skip_game_turn_db` and `get_next_host_id_db` raise on DB errors so `None` always means "game over"; `db.releases.add_new_release` returns an `AddResult` (a `PENDING` release is retried).
- **Foreign keys are enforced** (`db_connection` turns them on for every connection, and startup logs any existing rows that break them). That means `ON DELETE CASCADE` really cascades, so never use `INSERT OR REPLACE` on a table that other tables reference (it deletes the old row first and wipes its children); use `INSERT ... ON CONFLICT DO UPDATE`, as `register_new_role` does. Connections wait up to 10 seconds for a lock and are closed after each `with db_connection(...)` block. WAL mode was tried and not adopted (no gain with a connection per call).
- **The awards year runs December 1 to November 30 on purpose** (the videos are made in December): `utils.end_of_year.get_current_award_year()` is the single source, and every end-of-year feature uses it. Hubs carry the year they were posted for in their button IDs.
- **Reactions are handled without network calls where possible** (`triggers/merch.py`): the heart reward uses `payload.message_author_id`, reaction counts come from `client.cached_messages`, and a message that isn't cached is fetched at most twice (once to learn its count, once at 5 reactions). Don't add a `fetch_message` per reaction.
- **YouTube lookups are batched:** use `get_video_snippets(ids)` (50 videos per request, 1 quota unit per request) whenever you have several videos; `get_video_title` is the single-video wrapper. Backfills process messages in batches of 50 for this reason.
- **Listen game state** (`db/listen_game.py`): `GameStatus` (`registration` -> `playing` -> `finished`) and `RoundStatus` (`setting_theme` -> `submitting` -> `ranking` -> `revealing` -> `completed`, or `skipped`) are `StrEnum`s, and rows come back as dataclasses (`Game`, `Round`, `Submission`, `Standing`, ...), not dicts. Every status change is one guarded `UPDATE ... WHERE status IN (...)`; functions return whether the state moved, and `skip_game_turn_db` raises `InvalidStateError` (reported to users as "things have moved on"). Commands load the round with `require_active_round`, DM people with `send_dm`, and refresh the counter with `update_submission_tracker`. Confirming rankings atomically saves points and moves the round to `revealing` (`save_round_results_db`), so points can only be applied once. `services/listen_game_reveal.py` then posts the reveal in the background and records progress in `listen_rounds.reveal_step`; if the bot restarts mid-reveal, the hourly `check_listen_game_reminders` task (or the listener/GM re-running `/listen-game-submit-ranking`) resumes it.
- Admin slash commands take `@admin_only` (from `utils/validation.py`) directly under `@app_commands.command`. It hides the command from non-admins **and** rejects them at run time; `default_permissions` alone is only a UI default that server admins can override in Integrations. GM and Player commands use `@app_commands.checks.has_role(Role.X)`.
- `services/listen_game_playlist.py` is the one place that adds a submission to a round's YouTube playlist (used by both `submit_song` and GM `force-submit`). Its YouTube calls run via `asyncio.to_thread`, so both commands hold `SUBMISSION_LOCK` for the whole check-claimed / update-playlist / save sequence; keep any new code that writes submissions inside that lock.
- When a user's text may be long (list echoes, exports), attach it with `utils.discord_files.text_file` rather than pasting it into a message (2000 character limit).
- `ui/bracket_renderer.py` launches Chromium on demand, shares it between overlapping renders and closes it after 5 idle minutes (`BROWSER_IDLE_SECONDS`), so it uses no memory between tournament renders. The Docker image needs Playwright's Chromium installed.
- **Healthcheck:** `tasks/heartbeat.py` touches `HEARTBEAT_PATH` every minute while the client `is_ready()`, and the Dockerfile's `HEALTHCHECK` (every 2 minutes) reports the container unhealthy when the file is over 5 minutes old. It proves the event loop and gateway are alive, not that every other loop is; the other loops are covered by `@keep_running`.
- **Logging:** routine per-tick lines in background loops are `DEBUG`; log at `INFO` only when something happens (a reminder sent, a match resolved). `LOG_LEVEL=DEBUG` on the container shows the routine lines again.
- `scripts/render_bracket_preview.py` (outside the package, so it isn't linted, covered or shipped) builds a git-ignored `preview.html` from the bracket template for a look in a browser. It is **not** a pytest test.
- **Validate what admins type.** Hex colours go through `utils.validation.parse_colour` (range-checked), and image file names must be plain names of files in `iu/media/images` (`commands/biases._check_style`); never join user text into a path. The bracket template is rendered with `autoescape=True`. Free-text slash command options that users can fill should have a length limit (`app_commands.Range[str, 1, N]`).

## Testing

`pytest`, `pytest-asyncio` (`asyncio_mode = "auto"`, so `async def test_...` just works), `pytest-cov`, `freezegun` and `parameterized` are the tools, all in the `dev` group. **Every package under `iu/` is tested** (about 1,800 tests, near 100% coverage), mirroring the layout below. [pyproject.toml](pyproject.toml) sets `testpaths = ["tests"]`, `--import-mode=importlib`, `pythonpath = ["iu", "tests"]` (so `from db.x import ...` and `from testsupport.fakes import ...` both resolve) and the coverage settings (`source = iu`, omitting `main.py` and `scripts/`).

An unclosed SQLite connection or file surfaces as an unraisable `ResourceWarning`, which `filterwarnings` in [pyproject.toml](pyproject.toml) turns into a test failure, so leaks in `db/` code can't slip in. (`with sqlite3.connect(...)` only commits; wrap it in `contextlib.closing(...)` or use `db_connection`.)

CI should be green: it runs the whole suite (about 20 seconds) and requires 80% coverage. **When you add or change behaviour, add or update its tests in the same change.** Tests describe intended behaviour; if a test uncovers a bug, fix the code rather than encoding the bug (or mark it `xfail(strict=True)` with the reason until it is fixed).

### Shared fixtures and helpers

[tests/conftest.py](tests/conftest.py) holds the fixtures and [tests/testsupport/fakes.py](tests/testsupport/fakes.py) the fake Discord objects. Check them before writing new helpers.

**Safety nets (autouse, nothing to ask for):** every test starts with the bot's environment variables cleared (no real `.env`, no real database paths); using the real YouTube API raises `AssertionError`; launching Chromium is refused (`render_html_to_image` then returns `None`, like a render failure).

**Tools to ask for by name:**

| Fixture | Gives you |
| --- | --- |
| `databases(Database.MERCH, ...)` | Real empty SQLite files in `tmp_path`, created by the same `initialize_databases()` as production, with the env vars set. Databases you don't request stay unconfigured. Returns the paths |
| `all_databases` | All eleven of them |
| `query(Database.X, sql, *params)` / `execute(Database.X, sql, *params)` | Read rows back / seed rows directly, to assert on stored state without using the code under test |
| `frozen_time("2026-12-01 05:00:00")` | Freezes `datetime.now()` at a UTC moment; call again to move the clock. SQLite's `CURRENT_TIMESTAMP` is not frozen, so insert explicit timestamps |
| `interaction`, `admin_interaction`, `make_interaction(channel=..., user=..., guild=..., administrator=...)` | A fake slash command/button/modal interaction. `await command.callback(interaction, ...)`, then assert on `interaction.sent` (a list of `Sent` with `.text`, `.content`, `.embed`, `.ephemeral`, `.via`) |
| `make_member`, `make_channel`, `make_guild`, `make_message`, `make_client` | Fakes limited to the real discord.py classes (`spec=`). Members and channels record what they are sent on `.sent` |
| `fake_bracket_render` | Bracket rendering returns a fake PNG; returns the mock to assert on |

`tests/services/conftest.py` adds `youtube_client` (a fake YouTube API client installed as the one `services.youtube` uses; set results with `client.playlistItems.return_value.insert.return_value.execute.return_value = ...`) and `http_error("quotaExceeded")` (the errors the Google client raises). `testsupport/listen_game.py` has `start_game(players)` and `reveal_ready_round(game_id)` to build a Listen Game situation in a real temporary database.

For commands, call the handler with `await some_command.callback(interaction, ...)` (this skips the permission checks, which `test_registry.py` verifies separately for every command). `tests/commands/conftest.py` has `listen_server`, a server set up for the Listen Game: members 1 (GM), 2 (substitute GM) and 101-103, `listen_server.interaction(user_id)`, `.dms(user_id)` and `.blocked(user_id)`. Patch the YouTube functions a command imports in the command's own module (`monkeypatch.setattr("commands.listen_game.get_video_title", ...)`).

For background tasks, call the loop body with `await some_task.coro(client, guild_id)` (bypassing the timer), build the server with `make_guild(channels=(...))` and `make_client(guild=guild)`, and use `make_scheduled_event` / `make_poll_message`. SQLite's `CURRENT_TIMESTAMP` ignores `frozen_time`, so set stored timestamps explicitly with `execute` when a test moves the clock. The waits inside a task (`asyncio.sleep`) are patched out in the tests that reach them.

`testsupport/ui.py` has helpers for views and modals: `fill(text_input, value)` types into a modal box, `choose(select, *values)` picks menu options, `match_custom_id(ButtonClass, id)` gives the regex match `from_custom_id` receives, and `button_labels(view)`. Build views and modals inside `async def` tests (they need a running event loop), press buttons with `await view.some_button.callback(interaction)`, and read the result from `interaction.sent`. Bracket rendering tests use a fake Playwright (see `tests/ui/test_bracket_renderer.py`).

Patch other external calls (`services.youtube` functions) in the module that imports them (`monkeypatch.setattr("triggers.releases.add_video_to_playlist", ...)`), not in `services.youtube`. Fixtures that only one folder needs go in that folder's `conftest.py`.

### Test layout

Tests live in a top-level `tests/` directory that **mirrors `iu/`**, not next to the source (unlike Go's `foo_test.go`):

```text
iu/db/lists.py          ->  tests/db/test_lists.py
iu/commands/merch.py    ->  tests/commands/test_merch.py
iu/utils/validation.py  ->  tests/utils/test_validation.py
                            tests/conftest.py            # shared fixtures (e.g. temp SQLite DB)
                            tests/db/conftest.py         # fixtures used only by that folder
```

- **Do not colocate tests inside `iu/`.** the Docker build copies `iu/`, and coverage measures `iu/`, so colocated tests would be shipped in the image and counted in the coverage denominator. `.dockerignore` already excludes a top-level `tests/`.
- **No `__init__.py` files in `tests/`, and use `--import-mode=importlib`.** Otherwise same-named files (`tests/db/test_lists.py` vs `tests/ui/test_lists.py`) collide, and a `tests/db/` package could shadow the real `db` package that the code imports as `from db.lists import ...`.
- Tests are linted like the code (`pylint iu tests`). Fixtures from `conftest.py` are fine as parameters; if a fixture is defined and used in the same file, give the function a different name with `@pytest.fixture(name="thing")` instead of disabling `redefined-outer-name`.
- Name files `test_<module>.py` and functions `test_<behaviour>`. Use `@pytest.mark.parametrize` (or `parameterized`) for table-driven cases, the closest match to Go table tests.
- Put fixtures shared across files in `tests/conftest.py`; folder-specific ones in that folder's `conftest.py`. Importable helpers live in `tests/testsupport/` (the only package under `tests/`; its name is unique so it can't clash with the code).

Guidelines for writing tests:

- **Test `bot.py` and `db/initialize.py` directly**, not `main.py`. `IUBot()` can be constructed without connecting; patch `tree.sync`, `add_view` and the task `.start` methods (or call handlers such as `triggers/polls.handle_poll_vote` with a mock client) rather than running the bot. `main.py` only wires things together; `tests/test_main.py` just checks the order of startup.
- **DB tests use real SQLite, not mocks.** Use the `databases(...)` fixture (temp files, real schemas and migrations, env vars set) with `query`/`execute` for checking and seeding state. Prefer this over mocking `sqlite3`; the schemas contain constraints and cascades worth exercising.
- **Pure logic is the easiest coverage:** `utils/*`, `utils/validation.sanitize_list`, `triggers/releases.get_eligible_year`, the `_process_release_url` / `_sync_missing_videos` sync workers, bracket data building. Use `parameterized` for table-driven cases.
- **Discord objects:** commands are `app_commands.Command` objects; call the underlying coroutine with `.callback(interaction, ...)` and an interaction from the `make_interaction` fixture. Assert on `interaction.sent` (and `.ephemeral`), and on DB state.
- **Mock external services, never hit them:** patch `services.youtube` functions (`add_video_to_playlist`, `get_video_publish_date`, ...) and never load `token.json`. `_browser_cache` in `bracket_renderer` should be patched so tests don't launch Chromium.
- Time-dependent logic (deadlines, reminders, award year) use the `frozen_time` fixture so tests are deterministic.
