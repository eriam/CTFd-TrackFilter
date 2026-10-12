import json
import re
from collections.abc import Mapping

from flask import jsonify, request
from werkzeug.exceptions import NotFound

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


# --- Server-side enforcement ----------------------------------------------------

# Neutral message: does not say whether the challenge exists or which track
# it belongs to.
FORBIDDEN_MESSAGE = "This challenge is not available."

# /api/v1/challenges/<id> and its per-challenge sub-resources (CTFd 3.8).
_CHALLENGE_PATH_RE = re.compile(
    r"^/api/v1/challenges/(\d+)"
    r"(?:/(?:solves|files|hints|tags|topics|flags|requirements|ratings|solution))?$"
)
# Objects that belong to a challenge through their challenge_id column.
_OWNED_PATH_RE = re.compile(r"^/api/v1/(hints|solutions)/(\d+)$")

_SAFE_METHODS = ("GET", "HEAD", "OPTIONS")


def _to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _request_data():
    if request.is_json:
        data = request.get_json(silent=True)
    else:
        data = request.form
    return data if hasattr(data, "get") else {}


def _owner_challenge_id(tablename, object_id):
    """challenge_id of the hint / solution / ... row, or None."""
    from CTFd.models import get_class_by_tablename

    model = get_class_by_tablename(tablename)
    if model is None or not hasattr(model, "challenge_id") or object_id is None:
        return None
    obj = model.query.get(object_id)
    return getattr(obj, "challenge_id", None)


def _deny_not_found():
    # Same body as flask-restx gives for a challenge id that does not exist.
    resp = jsonify({"message": NotFound.description})
    resp.status_code = 404
    return resp


def _deny_forbidden(field):
    resp = jsonify({"success": False, "errors": {field: [FORBIDDEN_MESSAGE]}})
    resp.status_code = 403
    return resp


def _deny_attempt():
    # Same shape as CTFd's own refusals ("paused", "ratelimited") so the
    # challenge modal displays the message.
    resp = jsonify(
        {"success": True, "data": {"status": "forbidden", "message": FORBIDDEN_MESSAGE}}
    )
    resp.status_code = 403
    return resp


def _targeted_challenge():
    """Return ``(challenge_id, deny)`` for requests acting on one challenge.

    ``deny`` builds the refusal response.  Returns None for requests the
    guard does not care about.
    """
    path = request.path.rstrip("/")
    method = request.method

    if method == "POST" and path == "/api/v1/challenges/attempt":
        return _to_int(_request_data().get("challenge_id")), _deny_attempt

    if method == "POST" and path == "/api/v1/unlocks":
        data = _request_data()
        tablename = data.get("type")
        if not isinstance(tablename, str):
            return None
        challenge_id = _owner_challenge_id(tablename, _to_int(data.get("target")))
        return challenge_id, lambda: _deny_forbidden("target")

    match = _CHALLENGE_PATH_RE.match(path)
    if match:
        if method in _SAFE_METHODS:
            return int(match.group(1)), _deny_not_found
        return int(match.group(1)), lambda: _deny_forbidden("challenge_id")

    match = _OWNED_PATH_RE.match(path)
    if match and method in _SAFE_METHODS:
        challenge_id = _owner_challenge_id(match.group(1), int(match.group(2)))
        return challenge_id, _deny_not_found

    return None


def enforce_track_access():
    """before_request hook refusing actions on challenges outside the track.

    Unknown challenges are left to CTFd, which answers as usual.
    """
    target = _targeted_challenge()
    if target is None or target[0] is None:
        return None

    allowed = current_category_filter()
    if allowed is None:
        return None

    from CTFd.models import Challenges

    challenge = Challenges.query.get(target[0])
    if challenge is None or allowed(challenge.category):
        return None
    return target[1]()


def register_filter(app):
    """Register the request hooks on the Flask app."""
    app.before_request(enforce_track_access)
    app.after_request(filter_challenges_by_track)
