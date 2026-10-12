# CTFd-TrackFilter

A CTFd plugin that shows each player only the challenges of **their track**,
and refuses any action on challenges from another track.

Tracks are declared in the configuration. A track can be attached to a
**user**, so a team can mix members of different tracks: each member sees and
solves only their own track's challenges, and all points go to the team as in
CTFd's native teams mode. A track can still be attached to a whole **team**,
which members inherit.

The plugin holds no scenario: tracks, category prefixes, colours and options
all come from a JSON configuration. Two typical setups are described in
[Example configurations](#example-configurations).

## How it works

1. Each track has a **category prefix**. A challenge belongs to a track when
   its category starts with that prefix, after stripping an optional
   `[Optional] ` tag.
2. The **effective track** of a user is:
   1. their own track (`UserTrack`), if set;
   2. otherwise, if `fallback_to_team` is `true` (default), their team's track
      (`TeamTrack`);
   3. otherwise none. Users without a track see every challenge
      (`untracked: "all"`, default) or none (`untracked: "none"`).
3. `GET /api/v1/challenges` is filtered and `GET /api/v1/challenges/<id>` from
   another track returns 404.
4. A `before_request` hook refuses every action on another track's challenge:
   flag submission, hint/solution unlocks, sub-resources and hints (see
   [Server-side enforcement](#server-side-enforcement)).
5. **Admins are never filtered**, whatever their own track.
6. The `<body>` gets the theme class of the user's effective track
   (navbar and accent colours, generated from the configuration).
7. `/admin/track_filter` lists users and teams and lets admins assign tracks;
   a JSON API allows bulk assignment.

## Installation

Mount the `track_filter/` directory into CTFd's plugins folder:

```yaml
# docker-compose.yml
ctfd:
  volumes:
    - ./CTFd-TrackFilter/track_filter:/opt/CTFd/CTFd/plugins/track_filter
```

To use a configuration other than the default one, point
`TRACK_FILTER_CONFIG` at a JSON file (see [Configuration](#configuration)):

```yaml
ctfd:
  volumes:
    - ./CTFd-TrackFilter/track_filter:/opt/CTFd/CTFd/plugins/track_filter
    - ./tracks.json:/opt/CTFd/tracks.json:ro
  environment:
    - TRACK_FILTER_CONFIG=/opt/CTFd/tracks.json
```

Keep the deployment's configuration next to its `docker-compose.yml`, or point
`TRACK_FILTER_CONFIG` at one of the files in `track_filter/examples/`.

The plugin creates its tables (`team_tracks`, `user_tracks`) on load with
`create_all()`. Existing `team_tracks` rows keep working unchanged through the
team fallback. No migration is needed.

An invalid configuration makes the plugin fail at startup instead of filtering
wrongly. Check `docker compose logs ctfd` after a change.

## Configuration

Defaults live in `track_filter/config.json`. That is also the file CTFd reads
for the admin menu entry (`name`, `route`). Keys found in the file named by
`TRACK_FILTER_CONFIG` replace the defaults. `tracks` is replaced as a whole,
and keys absent from the override keep their default value.

| Key | Default | Meaning |
|---|---|---|
| `tracks` | red-team, blue-team | List of track definitions (below). |
| `fallback_to_team` | `true` | Users without their own track inherit their team's track. |
| `self_select` | `true` | Teams pick their track on the team creation form. With `false`, no track field is offered, any posted `track` is ignored and only admins assign tracks. |
| `untracked` | `"all"` | Users without an effective track see every challenge (`"all"`) or none, with every action refused (`"none"`). |
| `hide_foreign_solves` | `false` | On the team pages (`/team`, `/teams/<id>`) and in `GET /api/v1/teams/{me,<id>}/solves`, a member sees `Hidden challenge` (and the owning track's label as category) for solves outside their track. |

Track definition:

| Field | Required | Meaning |
|---|---|---|
| `id` | yes | Identifier stored in the database: 1 to 16 characters, lowercase letters, digits, `-`, `_`. `none` is reserved. |
| `category_prefix` | yes | Challenges whose category starts with it belong to the track. |
| `label` | no (prefix) | Display name (admin page, team form, masked solves). |
| `description` | no | Shown after the label on the team creation form. |
| `theme` | no | A CSS class name, or an object: `class` (default `track-<id>`), `accent`, `accent_light`, `accent_dark`, `bg`, `bg_subtle` (`#rgb` / `#rrggbb` colours) and `banner` (text above the navbar brand). |

The default configuration defines two tracks, `red-team` → `Red Team`
(`track-red`) and `blue-team` → `Blue Team` (`track-blue`), without banner.
Any team may pick its track, and untracked teams see everything.

When a stored track is no longer in the configuration, it is ignored: resolution
moves on to the next rule. The admin page flags such a track in yellow.

## Example configurations

`track_filter/examples/` holds complete configurations from past events.
Copy one and adapt the tracks, prefixes and colours.

| File | Setup |
|---|---|
| `vercors.json` | One track per team (`red-team`, `blue-team`), inherited by every member, with navbar banners. |
| `valmont.json` | Mixed teams (`blue-team`, `cs-tip`): tracks are per user and assigned by admins only. |

### One track per team

Keep the defaults (`fallback_to_team: true`, `self_select: true`): a team
picks its track when it is created, or an admin sets it on
`/admin/track_filter`, and every member inherits it.

### Mixed teams

Members of the same team play different tracks and their points add up in
the team score. Typical options:

```json
{
    "tracks": [
        {"id": "blue-team", "label": "Blue Team", "category_prefix": "Blue Team",
         "theme": {"class": "track-blue", "accent": "#2563eb"}},
        {"id": "support", "label": "Support", "category_prefix": "Support",
         "theme": {"accent": "#0d9488"}}
    ],
    "fallback_to_team": false,
    "self_select": false,
    "untracked": "none",
    "hide_foreign_solves": true
}
```

- `self_select: false`: players cannot pick their own track. Only admins
  assign tracks, with the bulk API below.
- `untracked: none` + `fallback_to_team: false`: until a player has been
  assigned a track, they see nothing. This holds even if their team had a
  team track.
- `hide_foreign_solves: true`: team pages do not reveal the other track's
  challenge names.
- `GET /api/v1/track_filter/scoreboard` shows each team's points split by
  track.

Deployment:

1. Mount the volume and set `TRACK_FILTER_CONFIG` as shown in
   [Installation](#installation), then restart CTFd.
2. Logged in as an admin, create an access token (Settings → Access Tokens).
3. Assign tracks in bulk:

   ```bash
   curl -X POST https://ctfd.example/api/v1/track_filter/users \
        -H "Authorization: Token $CTFD_TOKEN" \
        -H "Content-Type: application/json" \
        -d '[{"email": "player01@example.org", "track": "blue-team"},
             {"name": "player02", "track": "support"},
             {"user_id": 42, "track": ""}]'
   ```

4. Check that nobody is left without a track (`Content-Type:
   application/json` is needed for CTFd token authentication, even on GET):

   ```bash
   curl https://ctfd.example/api/v1/track_filter/users?track=none \
        -H "Authorization: Token $CTFD_TOKEN" -H "Content-Type: application/json"
   ```

## Server-side enforcement

For non-admin users, when the targeted challenge exists and is outside the
user's track:

| Request | Response |
|---|---|
| `POST /api/v1/challenges/attempt` (`challenge_id` in the JSON or form body) | 403 `{"success": true, "data": {"status": "forbidden", "message": "This challenge is not available."}}`, the same shape as CTFd's own refusals (`paused`), so the modal shows the message |
| `POST /api/v1/unlocks` (`{"type": "hints" \| "solutions", "target": <id>}`, resolved to the challenge) | 403 |
| `GET /api/v1/challenges/<id>` and `/solves`, `/files`, `/hints`, `/tags`, `/topics`, `/flags`, `/requirements`, `/ratings`, `/solution` | 404, same body as an unknown id |
| `PUT /api/v1/challenges/<id>/ratings` | 403 |
| `GET /api/v1/hints/<id>`, `GET /api/v1/solutions/<id>` | 404 |

Requests for unknown challenges are passed through to CTFd unchanged. In CTFd 3.8,
`/files`, `/tags`, `/topics`, `/hints`, `/flags`, `/requirements` and the GET
`/ratings` are already admin-only. The check on them is defence in depth.

## Admin

- `/admin/track_filter`: users (team, own track, effective track), filterable
  by team or effective track, with per-user assignment; teams with their
  team track.
- `POST /api/v1/track_filter/users`: bulk assignment. Body:
  `[{"user_id"|"email"|"name": …, "track": "<id>" | ""}]`. The user is looked up
  by the first key present, in that order (email is case-insensitive). An
  empty track removes the user's own track. Each row is applied independently.
  The response details every row:

  ```json
  {"success": false,
   "data": [{"index": 0, "status": "applied", "user_id": 12, "name": "ais01", "track": "blue-team", "previous": null},
            {"index": 1, "status": "error", "error": "user not found"}],
   "meta": {"applied": 1, "errors": 1}}
  ```

- `GET /api/v1/track_filter/users[?team_id=&track=<id>|none]`: export of
  assignments (`track`, `team_track`, `effective_track`).
- `GET /api/v1/track_filter/scoreboard`: each team's points split by the
  effective track of the members who scored them (`none` for members
  without a track). As in CTFd's team score, a team counts its current
  members' solves and awards, hint unlocks being negative awards. Freeze time
  is ignored.

These routes are admin-only, through the session or a CTFd access token.
Non-admins get a JSON 403. With a session, POST needs the `CSRF-Token` header,
like any CTFd API call.

## Category convention and prerequisites

Challenges must use category prefixes matching the track, for example:

- `Red Team — reconnaissance`, `Blue Team — forensics`
- `Blue Team · 01 — Recon`, `Support — Helpdesk`
- `[Optional] Red Team — bonus` (optional prefix is stripped before matching)

When one prefix starts another one (`Blue` and `Blue Team`), the longest
prefix decides which track owns a challenge in masked solves. Prefer
prefixes that do not overlap.

**Prerequisites:** CTFd evaluates challenge requirements on the **team's**
solves. A challenge must never depend on a challenge from another track.
Otherwise, in a mixed team, one member would unlock challenges for the
other, and a single-track team would never unlock it.

## CTFd version

Developed and checked against **CTFd 3.8.8**, the latest tag when this was
written: route shapes, token authentication, CSRF and the team page
templates. The test suite also passes with the libraries CTFd 3.8.8 pins
(Python 3.11, Flask 2.1.3, Werkzeug 2.2.3, Flask-SQLAlchemy 2.5.1,
SQLAlchemy 1.4.54).

Check the deployed version with
`docker compose exec ctfd python -c "import CTFd; print(CTFd.__version__)"`.
With another version, check the routes listed in
[Server-side enforcement](#server-side-enforcement). `/solution`,
`/api/v1/solutions/<id>` and the `solutions` unlock type only exist since 3.8.

## Known limitations

- The team creation override is registered as `teams/new.html`, but CTFd
  (2.0 and later) renders `teams/new_team.html`. The track selector is
  therefore not shown by CTFd's team form, while a `track` field posted to
  `/teams/new` is still honoured when `self_select` is `true`. Use
  `self_select: false` and admin assignment when the choice must not be left
  to players.
- `hide_foreign_solves` covers the team pages and team solves routes, not
  `/api/v1/users/<id>/solves`, `/fails` or `/awards` (awards for hint unlocks
  carry the challenge category, hence the track name).
- Filtering applies to the API. The challenge board page itself carries no
  challenge data.

## Testing

```bash
cd CTFd-TrackFilter
PYTHONPATH=. python3 -m pytest tests/ -v
```

Tests run standalone with a minimal Flask+SQLAlchemy environment. No CTFd
installation is required: `tests/conftest.py` stubs the `CTFd` package.
