"""hide_foreign_solves: mask titles of team solves outside the viewer's track.

Covers the team solves API routes (JSON, after_request) and the team pages
``/team`` and ``/teams/<id>``.  Those pages are rendered server side from
``team.get_solves()``; Flask's before_render_template signal needs blinker,
which CTFd does not install, so ``Teams.get_solves`` is wrapped instead and
returns masked proxies for those two views only.
"""

import functools
import json
import re

from flask import has_request_context, request

from .config import get_config
from .filter import _strip_optional, current_category_filter

HIDDEN_NAME = "Hidden challenge"
OTHER_TRACK_LABEL = "Other track"

TEAM_PAGE_ENDPOINTS = ("teams.private", "teams.public")
_TEAM_SOLVES_RE = re.compile(r"^/api/v1/teams/(?:me|\d+)/solves$")


def _masked_category(category):
    track = get_config().track_for_category(_strip_optional(category or ""))
    return track.label if track else OTHER_TRACK_LABEL


def _foreign_filter():
    """Predicate telling whether a category is hidden, or None to show all."""
    if not get_config().hide_foreign_solves:
        return None
    allowed = current_category_filter()
    if allowed is None:
        return None
    return lambda category: not allowed(category)


def mask_team_solves(response):
    """after_request: mask foreign challenges in team solves API responses."""
    if request.method != "GET" or not _TEAM_SOLVES_RE.match(request.path.rstrip("/")):
        return response

    is_foreign = _foreign_filter()
    if is_foreign is None:
        return response

    try:
        data = response.get_json()
    except Exception:
        return response
    if not isinstance(data, dict) or not isinstance(data.get("data"), list):
        return response

    for solve in data["data"]:
        challenge = solve.get("challenge") if isinstance(solve, dict) else None
        if isinstance(challenge, dict) and is_foreign(challenge.get("category")):
            challenge["name"] = HIDDEN_NAME
            challenge["category"] = _masked_category(challenge.get("category"))

    response.set_data(json.dumps(data))
    response.content_type = "application/json"
    return response


class _Proxy:
    """Read-only stand-in overriding some attributes of a model instance."""

    def __init__(self, wrapped, **overrides):
        self.__dict__["_wrapped"] = wrapped
        self.__dict__.update(overrides)

    def __getattr__(self, name):
        return getattr(self.__dict__["_wrapped"], name)

    def __setattr__(self, name, value):
        raise AttributeError("masked solve is read-only")


def mask_solve_objects(solves, is_foreign):
    """Wrap foreign solves so templates see a hidden name and category."""
    masked = []
    for solve in solves:
        challenge = getattr(solve, "challenge", None)
        if challenge is not None and is_foreign(challenge.category):
            challenge = _Proxy(
                challenge,
                name=HIDDEN_NAME,
                category=_masked_category(challenge.category),
            )
            solve = _Proxy(solve, challenge=challenge)
        masked.append(solve)
    return masked


def _wrap_get_solves(teams_model):
    original = teams_model.get_solves
    if getattr(original, "_track_filter_wrapped", False):
        return

    @functools.wraps(original)
    def get_solves(self, *args, **kwargs):
        solves = original(self, *args, **kwargs)
        if not has_request_context() or request.endpoint not in TEAM_PAGE_ENDPOINTS:
            return solves
        is_foreign = _foreign_filter()
        if is_foreign is None:
            return solves
        return mask_solve_objects(solves, is_foreign)

    get_solves._track_filter_wrapped = True
    teams_model.get_solves = get_solves


def register_solve_masking(app):
    from CTFd.models import Teams

    _wrap_get_solves(Teams)
    app.after_request(mask_team_solves)
