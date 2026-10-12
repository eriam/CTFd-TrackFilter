"""Shared helpers for the track filter tests."""

from contextlib import contextmanager
from unittest.mock import patch

from flask import jsonify

from CTFd.models import db

from track_filter.config import parse_config, set_config
from track_filter.models import TeamTrack, UserTrack

VALMONT_CONFIG = {
    "tracks": [
        {"id": "blue-team", "label": "Blue Team", "category_prefix": "Blue Team"},
        {"id": "cs-tip", "label": "CS-TIP", "category_prefix": "CS-TIP"},
    ],
}

VALMONT_CHALLENGES = [
    {"id": 1, "name": "Ports ouverts", "category": "Blue Team · 01 — Exposition"},
    {"id": 2, "name": "Journaux", "category": "Blue Team · 02 — Détection"},
    {"id": 3, "name": "Badge", "category": "CS-TIP — Site annexe"},
    {"id": 4, "name": "Bonus", "category": "[Optional] CS-TIP — Site annexe"},
]


def use_config(**options):
    """Activate the Valmont tracks with the given option overrides."""
    return set_config(parse_config(dict(VALMONT_CONFIG, **options)))


def make_team(models, name, track=None):
    team = models.Teams(name=name)
    db.session.add(team)
    db.session.flush()
    if track:
        db.session.add(TeamTrack(team_id=team.id, track=track))
    db.session.commit()
    return team


def make_user(models, name, team=None, track=None, email=None):
    user = models.Users(
        name=name,
        email=email or f"{name.lower()}@example.org",
        team_id=team.id if team else None,
    )
    db.session.add(user)
    db.session.flush()
    if track:
        db.session.add(UserTrack(user_id=user.id, track=track))
    db.session.commit()
    return user


def make_challenge(models, name, category, value=100):
    chal = models.Challenges(name=name, category=category, value=value)
    db.session.add(chal)
    db.session.commit()
    return chal


@contextmanager
def logged_in(user=None, team=None, admin=False, module="track_filter.filter"):
    """Pretend ``user`` (member of ``team``) is the current CTFd user."""
    with patch(f"{module}.get_current_user", return_value=user), patch(
        f"{module}.get_current_team", return_value=team
    ), patch(f"{module}.is_admin", return_value=admin):
        yield


def json_response(app, data, status=200):
    with app.test_request_context():
        resp = jsonify(data)
        resp.status_code = status
        return resp
