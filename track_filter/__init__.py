import os

from CTFd.plugins import register_plugin_assets_directory

from .admin import track_admin
from .api import track_api
from .config import get_config, load_config, set_config
from .filter import get_current_track, register_filter
from .solves import register_solve_masking
from .team_creation import register_team_creation_hooks


def load(app):
    # Fail fast on an invalid configuration rather than filter wrongly.
    config = set_config(load_config())

    app.db.create_all()

    # --- Template overrides ---------------------------------------------------
    dir_path = os.path.dirname(os.path.realpath(__file__))

    from CTFd.plugins import override_template

    # Without self-selection CTFd's own team creation form is left untouched.
    if config.self_select:
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
    app.register_blueprint(track_api)

    # --- Challenge API filter -------------------------------------------------
    register_filter(app)
    register_solve_masking(app)

    # --- Static assets --------------------------------------------------------
    register_plugin_assets_directory(app, base_path="/plugins/track_filter/assets/")

    # --- Context processor for body class and templates -----------------------
    @app.context_processor
    def inject_track_context():
        cfg = get_config()
        context = {
            "track_filter_tracks": list(cfg.tracks.values()),
            "track_filter_self_select": cfg.self_select,
            "track_theme_css": cfg.theme_css(),
            "track_body_class": "",
        }
        try:
            track = get_current_track()
        except Exception:
            return context
        if track is not None:
            context["track_body_class"] = f"track-themed {track.css_class}"
        return context

    # --- Intercept team creation to capture track field -----------------------
    register_team_creation_hooks(app)
