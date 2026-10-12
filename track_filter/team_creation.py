"""Capture the track chosen on the team creation form (self_select only)."""

from flask import request

from CTFd.models import db
from CTFd.utils.user import get_current_team

from .config import get_config
from .models import TeamTrack


def capture_track_on_team_create():
    """before_request: stash a valid track posted to /teams/new.

    With ``self_select: false`` any submitted track is ignored: only an
    admin assigns tracks.
    """
    if request.path != "/teams/new" or request.method != "POST":
        return None

    cfg = get_config()
    if not cfg.self_select:
        return None

    # Stash track value; the actual team creation is handled by CTFd.
    # We pick it up in after_request once the team exists.
    track = request.form.get("track", "").strip()
    if cfg.is_valid(track):
        request._track_filter_track = track
    return None


def store_track_after_team_create(response):
    """after_request: store the stashed track once CTFd created the team."""
    track = getattr(request, "_track_filter_track", None)
    if track is None:
        return response

    # Only act on a successful redirect (team was created)
    if response.status_code not in (301, 302, 303):
        return response

    team = get_current_team()
    if team is None:
        return response

    existing = TeamTrack.query.get(team.id)
    if existing is None:
        db.session.add(TeamTrack(team_id=team.id, track=track))
        db.session.commit()

    return response


def register_team_creation_hooks(app):
    app.before_request(capture_track_on_team_create)
    app.after_request(store_track_after_team_create)
