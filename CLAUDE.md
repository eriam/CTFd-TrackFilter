# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A CTFd plugin that filters challenges by team track (red-team / blue-team). The plugin is designed to be mounted into CTFd's plugins directory via Docker volume — it is **not** installed alongside a local CTFd instance.

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

Tests run standalone — no CTFd installation required. `conftest.py` stubs the entire `CTFd` package via `sys.modules` before any plugin import.

## Architecture

The plugin entry point is `track_filter/__init__.py` `load(app)`, called by CTFd on startup. It wires together three concerns:

- **`models.py`** — `TeamTrack` table (`team_id PK → teams.id`, `track` string). One row per team, values `"red-team"` or `"blue-team"`.
- **`filter.py`** — `after_request` hook registered on the Flask app. Intercepts `GET /api/v1/challenges` (list) and `GET /api/v1/challenges/<id>` (detail). Filters by comparing `challenge.category` against the team's expected prefix after stripping an optional `[Optional] ` prefix.
- **`admin.py`** — Flask Blueprint at `/admin/track_filter`. Lists all teams with their current track and allows reassignment or removal.

Track assignment happens in two places: at team creation time (via a `before_request` / `after_request` pair that stashes the track field from `/teams/new` POST and writes it once the redirect confirms team creation) and via the admin panel.

## Category convention

Challenges must use category prefixes matching the track:
- `Red Team — <subcategory>`
- `Blue Team — <subcategory>`
- `[Optional] Red Team — <subcategory>` (optional prefix is stripped before matching)

## Deployment

Mount `track_filter/` into CTFd's plugins folder:
```yaml
volumes:
  - ./CTFd-TrackFilter/track_filter:/opt/CTFd/CTFd/plugins/track_filter
```

## Test infrastructure

`tests/conftest.py` builds a minimal Flask + SQLAlchemy environment with an in-memory SQLite DB. Key fixtures:
- `app` — Flask app with all CTFd stubs, SQLite DB, and a stub `admin/base.html` template
- `client` — test client for the app
- `teams_model` — the stub `Teams` SQLAlchemy model

The admin blueprint is **not** registered in the base `app` fixture — `test_admin.py` has its own `admin_app` fixture that adds it.
