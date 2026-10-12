import json
import re
from collections.abc import Mapping

from flask import request

from CTFd.utils.user import get_current_team, get_current_user, is_admin

from .config import get_config
from .tracks import resolve_track_id


class _TrackPrefixView(Mapping):
    """Read-only ``{track_id: category_prefix}`` view of the active config."""

    def _prefixes(self):
        return {t.id: t.category_prefix for t in get_config().tracks.values()}

    def __getitem__(self, track_id):
        return self._prefixes()[track_id]

    def __iter__(self):
        return iter(self._prefixes())

    def __len__(self):
        return len(self._prefixes())


TRACK_CATEGORY_PREFIX = _TrackPrefixView()

# Matches an optional "[Optional] " prefix before the track name
_OPTIONAL_RE = re.compile(r"^\[Optional\]\s*")


def _strip_optional(category):
    """Remove leading '[Optional] ' tag from a category string."""
    return _OPTIONAL_RE.sub("", category)


def get_current_track():
    """Return the effective Track of the current user, or None.

    The user's own track wins; otherwise the team's track is used when
    ``fallback_to_team`` is enabled.
    """
    user = get_current_user()
    team = get_current_team()
    track_id = resolve_track_id(
        getattr(user, "id", None), getattr(team, "id", None)
    )
    return get_config().get(track_id)


def current_category_filter():
    """Return None if the current user sees every challenge, else a predicate.

    The predicate takes a challenge category and tells whether the current
    user may see / act on it.  Admins are never filtered.  Users without a
    track see everything (``untracked: all``) or nothing (``untracked: none``).
    """
    if is_admin():
        return None
    track = get_current_track()
    if track is None:
        if get_config().untracked == "all":
            return None
        return lambda category: False
    return lambda category: track.matches(_strip_optional(category or ""))


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
    """Remove challenges whose category does not match the user's track."""
    allowed = current_category_filter()
    if allowed is None:
        return response

    try:
        data = response.get_json()
    except Exception:
        return response

    if not isinstance(data, dict) or not isinstance(data.get("data"), list):
        return response

    data["data"] = [c for c in data["data"] if allowed(c.get("category", ""))]
    response.set_data(json.dumps(data))
    response.content_type = "application/json"
    return response


def _not_found(response):
    response.status_code = 404
    response.set_data(json.dumps({"success": True, "data": None}))
    response.content_type = "application/json"
    return response


def _filter_challenge_detail(response):
    """Return 404 if a single challenge does not belong to the user's track."""
    allowed = current_category_filter()
    if allowed is None:
        return response

    try:
        data = response.get_json()
    except Exception:
        return response

    if not isinstance(data, dict) or not isinstance(data.get("data"), dict):
        return response

    if not allowed(data["data"].get("category", "")):
        return _not_found(response)

    return response


def register_filter(app):
    """Register the after_request hook on the Flask app."""
    app.after_request(filter_challenges_by_track)
