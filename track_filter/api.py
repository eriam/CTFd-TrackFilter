"""Admin JSON API: bulk track assignment, export and per-track scoreboard.

All routes require an admin, authenticated by session (with the CSRF-Token
header on POST) or by a CTFd access token (``Authorization: Token ...`` and
``Content-Type: application/json``, as CTFd requires for token auth).
"""

import functools

from flask import Blueprint, jsonify, request

from CTFd.models import db
from CTFd.utils.user import is_admin

from .config import get_config
from .tracks import effective_track_id, load_assignments, set_user_track, user_rows

track_api = Blueprint("track_api", __name__)

_USER_KEYS = ("user_id", "email", "name")
UNTRACKED_BUCKET = "none"


def _admin_json(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if not is_admin():
            resp = jsonify({"success": False, "errors": {"auth": ["Admins only"]}})
            resp.status_code = 403
            return resp
        return f(*args, **kwargs)

    return wrapper


def _error(message, status=400):
    resp = jsonify({"success": False, "errors": {"body": [message]}})
    resp.status_code = status
    return resp


def _find_user(row):
    """Return ``(user, error)`` for one row of the bulk request."""
    from CTFd.models import Users

    key = next((k for k in _USER_KEYS if k in row), None)
    if key is None:
        return None, "missing user_id, email or name"
    value = row[key]

    if key == "user_id":
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            return None, "invalid user_id"
        try:
            matches = [Users.query.get(int(value))]
        except ValueError:
            return None, "invalid user_id"
        matches = [u for u in matches if u is not None]
    else:
        if not isinstance(value, str) or not value.strip():
            return None, f"invalid {key}"
        if key == "email":
            column = Users.email
            matches = Users.query.filter(
                db.func.lower(column) == value.strip().lower()
            ).all()
        else:
            matches = Users.query.filter(Users.name == value).all()

    if not matches:
        return None, "user not found"
    if len(matches) > 1:
        return None, f"several users match this {key}"
    return matches[0], None


@track_api.route("/api/v1/track_filter/users", methods=["GET"])
@_admin_json
def export_assignments():
    team_id = request.args.get("team_id", type=int)
    track = request.args.get("track", "").strip() or None
    rows = user_rows(team_id=team_id, track=track)
    return jsonify({"success": True, "data": rows, "meta": {"count": len(rows)}})


@track_api.route("/api/v1/track_filter/users", methods=["POST"])
@_admin_json
def bulk_assign():
    """Body: ``[{"user_id"|"email"|"name": ..., "track": "<id>" | ""}, ...]``.

    Each row is applied independently; the response details every row.
    An empty track removes the user's own track.
    """
    rows = request.get_json(silent=True)
    if not isinstance(rows, list):
        return _error("expected a JSON list of assignments")

    cfg = get_config()
    results = []
    for index, row in enumerate(rows):
        result = {"index": index}
        results.append(result)

        if not isinstance(row, dict):
            result.update(status="error", error="row must be an object")
            continue

        track = row.get("track")
        if not isinstance(track, str) or not (track == "" or cfg.is_valid(track)):
            result.update(
                status="error",
                error=f"invalid track (expected one of {cfg.track_ids()} or \"\")",
            )
            continue

        user, error = _find_user(row)
        if error:
            result.update(status="error", error=error)
            continue

        previous = set_user_track(user.id, track)
        # Flush so a later row for the same user sees this one.
        db.session.flush()
        result.update(
            status="applied",
            user_id=user.id,
            name=user.name,
            track=track or None,
            previous=previous,
        )

    db.session.commit()
    applied = sum(1 for r in results if r["status"] == "applied")
    return jsonify(
        {
            "success": applied == len(results),
            "data": results,
            "meta": {"applied": applied, "errors": len(results) - applied},
        }
    )


@track_api.route("/api/v1/track_filter/scoreboard", methods=["GET"])
@_admin_json
def scoreboard_by_track():
    """Each team's points split by the effective track of its members.

    Like CTFd's team score, a team scores its current members' solves and
    awards (hint unlocks are negative awards).  Freeze time is ignored.
    Members without a track are counted under "none".
    """
    from CTFd.models import Awards, Challenges, Solves, Teams, Users

    cfg = get_config()
    user_tracks, team_tracks = load_assignments()
    members = {
        u.id: (u.team_id, effective_track_id(u.id, u.team_id, user_tracks, team_tracks, cfg))
        for u in Users.query.filter(Users.team_id.isnot(None)).all()
    }

    buckets = cfg.track_ids() + [UNTRACKED_BUCKET]
    board = {
        t.id: {
            "team_id": t.id,
            "name": t.name,
            "hidden": bool(getattr(t, "hidden", False)),
            "banned": bool(getattr(t, "banned", False)),
            "total": 0,
            "by_track": {b: 0 for b in buckets},
        }
        for t in Teams.query.order_by(Teams.id).all()
    }

    solve_points = db.session.query(Solves.user_id, Challenges.value).join(
        Challenges, Solves.challenge_id == Challenges.id
    )
    award_points = db.session.query(Awards.user_id, Awards.value)
    for user_id, value in list(solve_points) + list(award_points):
        if user_id not in members:
            continue
        team_id, track = members[user_id]
        entry = board.get(team_id)
        if entry is None:
            continue
        entry["by_track"][track or UNTRACKED_BUCKET] += value or 0
        entry["total"] += value or 0

    data = sorted(board.values(), key=lambda e: (-e["total"], e["team_id"]))
    return jsonify({"success": True, "data": data, "meta": {"tracks": buckets}})
