# CTFd-TrackFilter

A CTFd plugin that filters challenges by team track (red-team / blue-team).

Designed for Operation Vercors where two parallel tracks exist:
- **Red Team** (GRANITE STORM) — 50 attacker challenges
- **Blue Team** (VEM-CERT) — 45 defender challenges

## How it works

1. Teams choose their track at creation time via an extended team creation form
2. An `after_request` hook filters `GET /api/v1/challenges` to show only challenges whose category starts with the team's track prefix (`"Red Team"` or `"Blue Team"`)
3. Direct access to individual challenges (`/api/v1/challenges/<id>`) from the wrong track returns 404
4. CSS theming changes the navbar and accent colors based on the team's track
5. An admin page at `/admin/track_filter` lets admins view and reassign team tracks

## Installation

Mount the `track_filter/` directory into CTFd's plugins folder:

```yaml
# docker-compose.yml
ctfd:
  volumes:
    - ./CTFd-TrackFilter/track_filter:/opt/CTFd/CTFd/plugins/track_filter
```

The plugin auto-creates its database table (`team_tracks`) on first load.

## Category convention

Challenges must use category prefixes matching the track:

- `Red Team — reconnaissance`
- `Blue Team — forensics`
- `[Optional] Red Team — bonus` (optional prefix is stripped before matching)

## Testing

```bash
cd CTFd-TrackFilter
PYTHONPATH=. python3 -m pytest tests/ -v
```

Tests run standalone with a minimal Flask+SQLAlchemy environment (no CTFd installation required).
