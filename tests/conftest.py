"""
Test fixtures for CTFd-TrackFilter plugin.

Since CTFd is not installed locally (it runs in Docker), we create a
minimal Flask + SQLAlchemy environment that mirrors CTFd's core models
just enough to test the plugin logic.
"""

import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

# ---------------------------------------------------------------------------
# Stub the CTFd package so plugin imports resolve without a real CTFd install
# ---------------------------------------------------------------------------

db = SQLAlchemy()

# Minimal CTFd models matching the columns the plugin relies on
_teams_model = None
_models = {}


def _build_teams_model():
    global _teams_model
    if _teams_model is not None:
        return _teams_model

    class Teams(db.Model):
        __tablename__ = "teams"
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.String(128))

        def get_solves(self, admin=False):
            Users, Solves = _models["Users"], _models["Solves"]
            member_ids = [u.id for u in Users.query.filter_by(team_id=self.id)]
            return Solves.query.filter(Solves.user_id.in_(member_ids)).all()

    _teams_model = Teams
    return Teams


def _build_models():
    """Build (once) the stub CTFd models and return them by class name."""
    if _models:
        return _models

    Teams = _build_teams_model()

    class Users(db.Model):
        __tablename__ = "users"
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.String(128), unique=True)
        email = db.Column(db.String(128), unique=True)
        team_id = db.Column(db.Integer, db.ForeignKey("teams.id"))

    class Challenges(db.Model):
        __tablename__ = "challenges"
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.String(80))
        category = db.Column(db.String(80))
        value = db.Column(db.Integer, default=0)

    class Hints(db.Model):
        __tablename__ = "hints"
        id = db.Column(db.Integer, primary_key=True)
        challenge_id = db.Column(db.Integer, db.ForeignKey("challenges.id"))

    class Solutions(db.Model):
        __tablename__ = "solutions"
        id = db.Column(db.Integer, primary_key=True)
        challenge_id = db.Column(db.Integer, db.ForeignKey("challenges.id"))

    class Solves(db.Model):
        __tablename__ = "solves"
        id = db.Column(db.Integer, primary_key=True)
        challenge_id = db.Column(db.Integer, db.ForeignKey("challenges.id"))
        user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
        team_id = db.Column(db.Integer, db.ForeignKey("teams.id"))
        challenge = db.relationship("Challenges", lazy="joined")

    class Awards(db.Model):
        __tablename__ = "awards"
        id = db.Column(db.Integer, primary_key=True)
        user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
        team_id = db.Column(db.Integer, db.ForeignKey("teams.id"))
        value = db.Column(db.Integer, default=0)

    for model in (Teams, Users, Challenges, Hints, Solutions, Solves, Awards):
        _models[model.__name__] = model
    return _models


def _get_class_by_tablename(tablename):
    for model in _models.values():
        if model.__tablename__ == tablename:
            return model
    return None


def _setup_ctfd_stubs():
    """Install fake CTFd modules into sys.modules."""
    # CTFd.models
    models_mod = types.ModuleType("CTFd.models")
    models_mod.db = db
    models_mod.Teams = None  # patched after app context
    models_mod.get_class_by_tablename = _get_class_by_tablename

    # CTFd.plugins
    plugins_mod = types.ModuleType("CTFd.plugins")
    plugins_mod.override_template = MagicMock()
    plugins_mod.register_plugin_assets_directory = MagicMock()

    # CTFd.utils.user
    utils_mod = types.ModuleType("CTFd.utils")
    utils_user_mod = types.ModuleType("CTFd.utils.user")
    utils_user_mod.get_current_team = MagicMock(return_value=None)
    utils_user_mod.get_current_user = MagicMock(return_value=None)
    utils_user_mod.is_admin = MagicMock(return_value=False)

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
        # Patch CTFd.models.<Model> for use by the plugin's lazy imports
        for name, model in _build_models().items():
            setattr(sys.modules["CTFd.models"], name, model)
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


@pytest.fixture()
def models():
    """Stub CTFd models by class name (Teams, Users, Challenges, Hints, ...)."""
    return SimpleNamespace(**_build_models())


@pytest.fixture(autouse=True)
def track_config():
    """Run every test against the shipped default configuration.

    Tests that need other tracks or options call ``set_config(...)``; the
    default is restored afterwards.
    """
    from track_filter.config import load_config, reset_config, set_config

    cfg = set_config(load_config(override_path=""))
    yield cfg
    reset_config()
