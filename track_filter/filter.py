import json
import re

from flask import request

from CTFd.utils.user import get_current_team

from .models import TeamTrack

TRACK_CATEGORY_PREFIX = {
    "red-team": "Red Team",
    "blue-team": "Blue Team",
}

# Matches an optional "[Optional] " prefix before the track name
_OPTIONAL_RE = re.compile(r"^\[Optional\]\s*")


def _strip_optional(category):
    """Remove leading '[Optional] ' tag from a category string."""
    return _OPTIONAL_RE.sub("", category)


def _get_team_prefix():
    """Return the category prefix for the current user's team, or None."""
    team = get_current_team()
    if team is None:
        return None
    team_track = TeamTrack.query.get(team.id)
    if team_track is None:
        return None
    return TRACK_CATEGORY_PREFIX.get(team_track.track)


def filter_challenges_by_track(response):
    """after_request hook that filters GET /api/v1/challenges responses."""
    if request.method != "GET":
        return response

    # Only intercept the challenges API
    path = request.path.rstrip("/")

    if path == "/api/v1/challenges":
        return _filter_challenge_list(response)

    if re.match(r"^/api/v1/challenges/\d+$", path):
        return _filter_challenge_detail(response)

    return response


def _filter_challenge_list(response):
    """Remove challenges whose category does not match the team's track."""
    prefix = _get_team_prefix()
    if prefix is None:
        return response

    try:
        data = response.get_json()
    except Exception:
        return response

    if not isinstance(data, dict) or "data" not in data:
        return response

    data["data"] = [
        c
        for c in data["data"]
        if _strip_optional(c.get("category", "")).startswith(prefix)
    ]
    response.set_data(json.dumps(data))
    response.content_type = "application/json"
    return response


def _filter_challenge_detail(response):
    """Return 404 if a single challenge does not belong to the team's track."""
    prefix = _get_team_prefix()
    if prefix is None:
        return response

    try:
        data = response.get_json()
    except Exception:
        return response

    if not isinstance(data, dict) or "data" not in data:
        return response

    category = data["data"].get("category", "")
    if not _strip_optional(category).startswith(prefix):
        response.status_code = 404
        response.set_data(json.dumps({"success": True, "data": None}))
        response.content_type = "application/json"

    return response


def register_filter(app):
    """Register the after_request hook on the Flask app."""
    app.after_request(filter_challenges_by_track)
