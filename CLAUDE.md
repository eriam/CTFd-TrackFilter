# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A CTFd plugin that filters challenges by track. Tracks are configurable (default: red-team / blue-team) and attached to a **user** (`UserTrack`), falling back to the user's **team** (`TeamTrack`). Teams can therefore mix tracks (Valmont: `blue-team` + `cs-tip`). The plugin is designed to be mounted into CTFd's plugins directory via Docker volume — it is **not** installed alongside a local CTFd instance.

## Running tests

```bash
PYTHONPATH=. python3 -m pytest tests/ -v
```

Run a single test file:
```bash
PYTHONPATH=. python3 -m pytest tests/test_filter.py -v
```

Run a single test class or method:
```bash
PYTHONPATH=. python3 -m pytest tests/test_filter.py::TestFilterChallengeList::test_red_team_sees_only_red_challenges -v
```

Tests run standalone — no CTFd installation required. `conftest.py` stubs the entire `CTFd` package via `sys.modules` before any plugin import. Test deps: pytest, flask, flask-sqlalchemy. The target is CTFd 3.8.8, whose pins are Python 3.11, Flask 2.1.3, Werkzeug 2.2.3, Flask-SQLAlchemy 2.5.1 and SQLAlchemy 1.4.54. Werkzeug 2.2 does not run on Python ≥ 3.14; use e.g. `uv venv -p 3.11`.

## Architecture

The plugin entry point is `track_filter/__init__.py` `load(app)`, called by CTFd on startup. It loads the configuration (failing fast if invalid), creates tables, registers template overrides, blueprints, request hooks and a context processor.

- **`config.py`** — `TrackConfig` / `Track`, loaded from `config.json` + the JSON file named by `$TRACK_FILTER_CONFIG`. `get_config()` / `set_config()` hold the active config (module global). Track ids are validated (≤ 16 chars, `[a-z0-9][a-z0-9_-]*`, `none` reserved). Generates per-track CSS variables (`theme_css()`).
- **`models.py`** — `TeamTrack` (`team_id PK → teams.id`) and `UserTrack` (`user_id PK → users.id`), both `track String(16)`.
- **`tracks.py`** — resolution: own `UserTrack`, else `TeamTrack` if `fallback_to_team`, else none; unconfigured stored values are skipped. Assignment helpers and the user listing used by the admin page and API.
- **`filter.py`** — `get_current_track()` and `current_category_filter()` (None = sees everything: admins, or untracked with `untracked: all`). `after_request` filters `GET /api/v1/challenges` and 404s the detail; `before_request` `enforce_track_access` refuses attempts / unlocks (403) and per-challenge sub-resources, hints and solutions (404) outside the track. Matching strips an optional `[Optional] ` prefix, then `startswith(category_prefix)`.
- **`solves.py`** — `hide_foreign_solves`: masks team solves API responses and wraps `Teams.get_solves` for the `teams.private` / `teams.public` views (no blinker in CTFd, so no `before_render_template`).
- **`team_creation.py`** — `before_request` / `after_request` pair capturing a `track` posted to `/teams/new` into `TeamTrack`; ignored when `self_select` is false.
- **`admin.py`** — Blueprint at `/admin/track_filter`: users (own / effective track, filters by team or track, per-user assignment) and teams.
- **`api.py`** — admin JSON: `POST/GET /api/v1/track_filter/users` (bulk assign / export), `GET /api/v1/track_filter/scoreboard`. Admin check via `is_admin()` (JSON 403), not `admins_only`.

Tests patch `get_current_user`, `get_current_team` and `is_admin` **in the module that calls them** (`track_filter.filter`, `track_filter.team_creation`, `track_filter.api`); `tests/helpers.py` `logged_in()` does that.

## Configuration options

`tracks`, `fallback_to_team` (true), `self_select` (true), `untracked` (`all` | `none`), `hide_foreign_solves` (false). Without an override file the plugin behaves as the original red/blue version. Example: `track_filter/examples/valmont.json`.

## Category convention

Challenges must use the track's category prefix:
- `Red Team — <subcategory>`, `Blue Team · 01 — <subcategory>`, `CS-TIP — Site annexe`
- `[Optional] Red Team — <subcategory>` (optional prefix is stripped before matching)

CTFd evaluates prerequisites on team solves: a challenge must never require a challenge from another track.

## Deployment

Mount `track_filter/` into CTFd's plugins folder:
```yaml
volumes:
  - ./CTFd-TrackFilter/track_filter:/opt/CTFd/CTFd/plugins/track_filter
environment:
  - TRACK_FILTER_CONFIG=/opt/CTFd/CTFd/plugins/track_filter/examples/valmont.json  # optional
```

## Test infrastructure

`tests/conftest.py` builds a minimal Flask + SQLAlchemy environment with an in-memory SQLite DB. Key fixtures:
- `app` — Flask app with all CTFd stubs, SQLite DB, and a stub `admin/base.html` template
- `client` — test client for the app
- `teams_model` — the stub `Teams` SQLAlchemy model
- `models` — all stub models (`Teams`, `Users`, `Challenges`, `Hints`, `Solutions`, `Solves`, `Awards`)
- `track_config` (autouse) — resets the active config to the shipped default around each test; use `helpers.use_config(**options)` for the Valmont tracks

The admin blueprint is **not** registered in the base `app` fixture — `test_admin.py` has its own `admin_app` fixture that adds it; `test_api.py` registers `track_api`, `test_enforcement.py` / `test_solves.py` register hooks and stand-in CTFd routes, `test_plugin.py` calls `load(app)`.
