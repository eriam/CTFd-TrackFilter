"""
Test fixtures for CTFd-TrackFilter plugin.

Since CTFd is not installed locally (it runs in Docker), we create a
minimal Flask + SQLAlchemy environment that mirrors CTFd's core models
just enough to test the plugin logic.
"""

import sys
import types
from unittest.mock import MagicMock

import pytest
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

# ---------------------------------------------------------------------------
# Stub the CTFd package so plugin imports resolve without a real CTFd install
# ---------------------------------------------------------------------------

db = SQLAlchemy()

# Minimal Teams model matching CTFd's schema
_teams_model = None


def _build_teams_model():
    global _teams_model
    if _teams_model is not None:
        return _teams_model

    class Teams(db.Model):
        __tablename__ = "teams"
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.String(128))

    _teams_model = Teams
    return Teams


def _setup_ctfd_stubs():
    """Install fake CTFd modules into sys.modules."""
    # CTFd.models
    models_mod = types.ModuleType("CTFd.models")
    models_mod.db = db
    models_mod.Teams = None  # patched after app context

    # CTFd.plugins
    plugins_mod = types.ModuleType("CTFd.plugins")
    plugins_mod.override_template = MagicMock()
    plugins_mod.register_plugin_assets_directory = MagicMock()

    # CTFd.utils.user
    utils_mod = types.ModuleType("CTFd.utils")
    utils_user_mod = types.ModuleType("CTFd.utils.user")
    utils_user_mod.get_current_team = MagicMock(return_value=None)

    # CTFd.utils.decorators
    utils_decorators_mod = types.ModuleType("CTFd.utils.decorators")

    def admins_only(f):
        return f

    utils_decorators_mod.admins_only = admins_only

    # Wire up the package hierarchy
    ctfd_mod = types.ModuleType("CTFd")
    ctfd_mod.models = models_mod
    ctfd_mod.plugins = plugins_mod

    sys.modules["CTFd"] = ctfd_mod
    sys.modules["CTFd.models"] = models_mod
    sys.modules["CTFd.plugins"] = plugins_mod
    sys.modules["CTFd.utils"] = utils_mod
    sys.modules["CTFd.utils.user"] = utils_user_mod
    sys.modules["CTFd.utils.decorators"] = utils_decorators_mod


# Install stubs before any plugin import
_setup_ctfd_stubs()

# Now we can import plugin modules
from track_filter.models import TeamTrack  # noqa: E402


@pytest.fixture()
def app():
    """Create a minimal Flask app with SQLite in-memory DB."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite://"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret"

    db.init_app(app)

    # Enable FK constraints in SQLite (required for CASCADE)
    from sqlalchemy import event as sa_event, engine as sa_engine

    @sa_event.listens_for(sa_engine.Engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Provide a minimal admin/base.html so templates that extend it render
    import os
    import tempfile

    import jinja2

    templates_dir = tempfile.mkdtemp()
    admin_dir = os.path.join(templates_dir, "admin")
    os.makedirs(admin_dir, exist_ok=True)
    with open(os.path.join(admin_dir, "base.html"), "w") as f:
        f.write(
            "{% block content %}{% endblock %}"
        )

    # Combine test stubs with the app's default loader
    app.jinja_loader = jinja2.ChoiceLoader([
        jinja2.FileSystemLoader([templates_dir]),
        app.jinja_loader,
    ])

    with app.app_context():
        Teams = _build_teams_model()
        # Patch CTFd.models.Teams for use in admin.py
        sys.modules["CTFd.models"].Teams = Teams
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def teams_model():
    return _build_teams_model()
