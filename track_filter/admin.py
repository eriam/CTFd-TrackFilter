from flask import Blueprint, render_template, request, redirect, url_for, flash, session

from CTFd.models import db
from CTFd.utils.decorators import admins_only

from .config import get_config
from .models import TeamTrack
from .tracks import set_team_track, set_user_track, user_rows

track_admin = Blueprint(
    "track_admin",
    __name__,
    template_folder="templates",
)


def _filters(source):
    """The (team_id, track) list filters found in ``source``."""
    team_id = source.get("filter_team_id", type=int)
    track = source.get("filter_track", "").strip() or None
    return team_id, track


def _back(team_id=None, track=None):
    args = {}
    if team_id is not None:
        args["filter_team_id"] = team_id
    if track:
        args["filter_track"] = track
    return redirect(url_for("track_admin.config_view", **args))


@track_admin.route("/admin/track_filter")
@admins_only
def config_view():
    from CTFd.models import Teams

    team_id, track = _filters(request.args)
    teams = Teams.query.order_by(Teams.id).all()
    tracks = {t.team_id: t.track for t in TeamTrack.query.all()}
    return render_template(
        "admin/track_filter/config.html",
        teams=teams,
        tracks=tracks,
        users=user_rows(team_id=team_id, track=track),
        tf_config=get_config(),
        filter_team_id=team_id,
        filter_track=track,
        nonce=session.get("nonce", ""),
    )


@track_admin.route("/admin/track_filter/assign", methods=["POST"])
@admins_only
def assign_track():
    team_id = request.form.get("team_id", type=int)
    track = request.form.get("track", "").strip()

    if team_id is None or not (track == "" or get_config().is_valid(track)):
        flash("Invalid team or track value.", "danger")
        return _back(*_filters(request.form))

    set_team_track(team_id, track)
    db.session.commit()

    flash(f"Track updated for team {team_id}.", "success")
    return _back(*_filters(request.form))


@track_admin.route("/admin/track_filter/assign_user", methods=["POST"])
@admins_only
def assign_user_track():
    from CTFd.models import Users

    user_id = request.form.get("user_id", type=int)
    track = request.form.get("track", "").strip()

    if (
        user_id is None
        or Users.query.get(user_id) is None
        or not (track == "" or get_config().is_valid(track))
    ):
        flash("Invalid user or track value.", "danger")
        return _back(*_filters(request.form))

    set_user_track(user_id, track)
    db.session.commit()

    flash(f"Track updated for user {user_id}.", "success")
    return _back(*_filters(request.form))
