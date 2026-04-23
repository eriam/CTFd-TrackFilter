import os

from flask import request

from CTFd.models import db
from CTFd.plugins import register_plugin_assets_directory
from CTFd.utils.user import get_current_team

from .admin import track_admin
from .filter import register_filter
from .models import TeamTrack


def load(app):
    app.db.create_all()

    # --- Template overrides ---------------------------------------------------
    dir_path = os.path.dirname(os.path.realpath(__file__))

    from CTFd.plugins import override_template

    team_creation_path = os.path.join(
        dir_path, "templates", "overrides", "team_creation.html"
    )
    with open(team_creation_path) as f:
        override_template("teams/new.html", f.read())

    # Inject track theme CSS + body class into base template.
    # CTFd's base.html ends with </body></html>.  We inject our
    # snippet just before </body> so the CSS loads on every page.
    base_inject_path = os.path.join(
        dir_path, "templates", "overrides", "base_inject.html"
    )
    try:
        from CTFd.utils.config import get_theme

        theme = get_theme()
        base_tpl_path = os.path.join(
            app.root_path, "themes", theme, "templates", "base.html"
        )
        with open(base_tpl_path) as f:
            base_html = f.read()
        with open(base_inject_path) as f:
            inject_html = f.read()

        if "track_theme.css" not in base_html:
            patched = base_html.replace("</body>", inject_html + "\n</body>")
            override_template("base.html", patched)
    except Exception:
        # Graceful fallback — theme may not exist yet during setup
        pass

    # --- Blueprints -----------------------------------------------------------
    app.register_blueprint(track_admin)

    # --- Challenge API filter -------------------------------------------------
    register_filter(app)

    # --- Static assets --------------------------------------------------------
    register_plugin_assets_directory(app, base_path="/plugins/track_filter/assets/")

    # --- Context processor for body class -------------------------------------
    @app.context_processor
    def inject_track_class():
        try:
            team = get_current_team()
        except Exception:
            return {"track_body_class": ""}
        if team is None:
            return {"track_body_class": ""}
        tt = TeamTrack.query.get(team.id)
        if tt is None:
            return {"track_body_class": ""}
        side = tt.track.split("-")[0]  # "red" or "blue"
        return {"track_body_class": f"track-{side}"}

    # --- Intercept team creation to capture track field -----------------------
    @app.before_request
    def capture_track_on_team_create():
        if request.path != "/teams/new" or request.method != "POST":
            return None

        # Stash track value; the actual team creation is handled by CTFd.
        # We pick it up in after_request once the team exists.
        track = request.form.get("track", "").strip()
        if track in ("red-team", "blue-team"):
            request._track_filter_track = track
        return None

    @app.after_request
    def store_track_after_team_create(response):
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
