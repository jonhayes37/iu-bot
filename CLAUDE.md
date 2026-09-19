# IU bot

Discord bot (discord.py 2.x, Python 3.14) for the HallyU server. See [README.md](README.md) for the user-facing feature list.

## Layout

All code lives in `iu/` and imports are **relative to `iu/`** (`from db.lists import ...`, not `from iu.db.lists import ...`). `iu/` must be on `sys.path` to import anything.

- `main.py` — entry point. Creates the client, registers every slash command on the `CommandTree`, wires events, initializes DBs, then calls `client.run()`. **Runs everything at import time**, so it cannot be imported in tests.
- `commands/` — slash command handlers (`@app_commands.command`). Thin: validate, call `db/`, respond.
- `db/` — one module per SQLite database, plain sync functions. `db/schema/*.sql` are the schemas (applied with `CREATE TABLE IF NOT EXISTS` on every startup). `db/connection.py` has `db_connection()` and `ensure_column()`.
- `ui/` — discord `View`/`Modal` classes, plus `bracket_renderer.py` (Playwright + Jinja2 -> PNG).
- `tasks/` — `tasks.loop` background jobs (listen game reminders, tournament resolution, scheduled events).
- `triggers/` — event-driven handlers called from `main.py` (`on_message`, member join, reactions, ...).
- `services/youtube.py` — YouTube Data API client (cached, thread-safe build).
- `utils/` — pure helpers (`strings.py`, `validation.py`, `end_of_year.py`).

## Commands

```bash
pip install -e . && pip install -r requirements.txt    # what CI does
pylint iu                                              # lint (config in .pylintrc, max line 120)
pytest --cov=iu                                        # tests; CI then requires coverage >= 45%
make build-push                                        # docker build (linux/amd64), tag, push jonhayes37/iu-bot
python iu/main.py                                      # run locally (needs env vars below)
```

CI ([.github/workflows/ci.yaml](.github/workflows/ci.yaml)) runs pylint, pytest with coverage, and `coverage report --fail-under=45` on every PR. Keep `pylint iu` clean.

## Environment

Read via `os.getenv`: `DISCORD_TOKEN`, `DISCORD_GUILD`, `HALLYU_ID`, `TOKEN_DIR` (YouTube OAuth `token.json`), and one `DB_PATH_<NAME>` per database (BIASES, BOT, HALL_OF_FAME, HMAS, LISTEN_GAME, LISTS, MERCH, RELEASES, ROLES, TOP_SONGS, TOURNAMENTS). The Dockerfile sets the DB paths under `/app/data`. `.env`, `credentials.json`, and `token.json` are gitignored; never commit them.

## Conventions and gotchas

- **Blocking work must not run on the event loop.** sqlite and YouTube calls are synchronous; from async code wrap them in `asyncio.to_thread(...)` (see `triggers/releases.py`, `commands/listen_game_gm.py`). Don't call `time.sleep` or blocking I/O directly in a command or task.
- **DB functions swallow errors.** Pattern: `try: with db_connection(DB_PATH_X) as conn: ... except Exception: logger.error(...); return False/None/[]`. `db_connection()` commits on clean exit, rolls back on exception, and raises `DatabaseNotConfiguredError` when the path is unset (caught by the same `except`).
- **DB path constants are read at import time** (`DB_PATH_X = os.getenv(...)` at module level). Changing the env var afterwards has no effect.
- **Schema changes:** `CREATE TABLE IF NOT EXISTS` won't alter existing tables. Add new columns via `ensure_column()` in `initialize_databases()` (see the `tournaments.description` example) in addition to editing the `.sql`. New indexes can just be `CREATE INDEX IF NOT EXISTS` in the schema.
- **Channel-restricted commands** use `restricted = await validate_channel(interaction, 'name'); if restricted: return`. It returns `True` when it already sent the rejection.
- **Persistent views** (buttons that must survive a restart) need explicit `custom_id`s and a `client.add_view(...)` in `on_ready`. Only `JoinGameView`, the EOY/HMA hubs are registered. `ListenGameRankingView` is intentionally not; its in-progress state is in memory and lost on restart (host re-runs `/listen-game-submit-ranking`).
- `ui/bracket_renderer.py` keeps one shared Chromium instance for the process lifetime; the Docker image needs Playwright's Chromium installed.
- `ui/test_render.py` is a manual script that builds `preview.html` from the Jinja template. It is **not** a pytest test.

## Testing

`pytest`, `pytest-asyncio` (`asyncio_mode = "auto"` in [pyproject.toml](pyproject.toml)), `pytest-cov`, and `parameterized` are the intended tools. There are no tests yet.

Prerequisites still to sort out when adding the first tests:

- `pytest`, `pytest-asyncio`, and `pytest-cov` are installed in the local venv but **not in `requirements.txt`**, so CI would fail at the test step. Add them.
- Put `iu/` on the import path (e.g. `pythonpath = ["iu"]` under `[tool.pytest.ini_options]`) so `from db.x import ...` resolves. Add a `tests/` dir and `testpaths`.
- CI runs `pytest`, which exits non-zero if zero tests are collected.

Guidelines for writing tests:

- **Never import `iu/main.py`.** It connects to Discord and runs `initialize_databases()` at import. If startup logic needs coverage, extract it into a function first.
- **DB tests use real SQLite, not mocks.** Use `tmp_path`, apply the matching `db/schema/<name>.sql` with `executescript`, then `monkeypatch.setattr(db.module, "DB_PATH_X", str(path))` (module-level constant, so patch the attribute rather than the env var). Prefer this over mocking `sqlite3`; the schemas contain constraints and cascades worth exercising.
- **Pure logic is the easiest coverage:** `utils/*`, `utils/validation.sanitize_list`, `triggers/releases.get_eligible_year`, the `_process_release_url` / `_sync_missing_videos` sync workers, bracket data building. Use `parameterized` for table-driven cases.
- **Discord objects:** commands are `app_commands.Command` objects; call the underlying coroutine with `.callback(interaction, ...)` and a `unittest.mock.AsyncMock`/`MagicMock` interaction (`interaction.response.send_message`, `.followup.send`, `.channel.name`, `.user.id`). Assert on what was sent (and `ephemeral=`), and on DB state.
- **Mock external services, never hit them:** patch `services.youtube` functions (`add_video_to_playlist`, `get_video_publish_date`, ...) and never load `token.json`. `_browser_cache` in `bracket_renderer` should be patched so tests don't launch Chromium.
- Time-dependent logic (deadlines, reminders, award year) should take or patch `datetime` so tests are deterministic.
