from flask import Blueprint, render_template, request, redirect, url_for, flash, session

from CTFd.models import db
from CTFd.utils.decorators import admins_only

from .models import TeamTrack

track_admin = Blueprint(
    "track_admin",
    __name__,
    template_folder="templates",
)


@track_admin.route("/admin/track_filter")
@admins_only
def config_view():
    from CTFd.models import Teams

    teams = Teams.query.order_by(Teams.id).all()
    tracks = {t.team_id: t.track for t in TeamTrack.query.all()}
    return render_template(
        "admin/track_filter/config.html",
        teams=teams,
        tracks=tracks,
        nonce=session.get("nonce", ""),
    )


@track_admin.route("/admin/track_filter/assign", methods=["POST"])
@admins_only
def assign_track():
    team_id = request.form.get("team_id", type=int)
    track = request.form.get("track", "").strip()

    if team_id is None or track not in ("red-team", "blue-team", ""):
        flash("Invalid team or track value.", "danger")
        return redirect(url_for("track_admin.config_view"))

    existing = TeamTrack.query.get(team_id)

    if track == "":
        # Remove track assignment
        if existing:
            db.session.delete(existing)
            db.session.commit()
    elif existing:
        existing.track = track
        db.session.commit()
    else:
        db.session.add(TeamTrack(team_id=team_id, track=track))
        db.session.commit()

    flash(f"Track updated for team {team_id}.", "success")
    return redirect(url_for("track_admin.config_view"))
