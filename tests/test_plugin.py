"""Tests for load(): team creation capture, self_select and theming."""

import json
import os
import sys
from unittest.mock import patch

import pytest
from flask import redirect, render_template_string

from CTFd.models import db

import track_filter
from track_filter.models import TeamTrack, UserTrack

from .helpers import MIXED_CONFIG, logged_in, make_team, make_user

BASE_INJECT = os.path.join(
    os.path.dirname(track_filter.__file__), "templates", "overrides", "base_inject.html"
)


@pytest.fixture()
def load_plugin(app, models, monkeypatch, tmp_path):
    """Return a function calling load(app) with optional config overrides."""
    override_template = sys.modules["CTFd.plugins"].override_template

    def _load(**overrides):
        if overrides:
            path = tmp_path / "override.json"
            path.write_text(json.dumps(overrides))
            monkeypatch.setenv("TRACK_FILTER_CONFIG", str(path))
        else:
            monkeypatch.delenv("TRACK_FILTER_CONFIG", raising=False)
        override_template.reset_mock()
        app.db = db

        @app.route("/teams/new", methods=["POST"])
        def new_team():
            from flask import request

            team = models.Teams(name=request.form["name"])
            db.session.add(team)
            db.session.commit()
            return redirect("/challenges")

        @app.route("/register", methods=["POST"])
        def register():
            return redirect("/challenges")

        track_filter.load(app)
        return override_template

    return _load


def _newest_team(models):
    return lambda: models.Teams.query.order_by(models.Teams.id.desc()).first()


def _overridden(override_template):
    return [c.args[0] for c in override_template.call_args_list]


class TestSelfSelect:
    def test_default_config_captures_track(self, app, models, load_plugin):
        override_template = load_plugin()
        assert "teams/new.html" in _overridden(override_template)
        with patch(
            "track_filter.team_creation.get_current_team", side_effect=_newest_team(models)
        ):
            resp = app.test_client().post(
                "/teams/new", data={"name": "Red", "track": "red-team"}
            )
        assert resp.status_code == 302
        team = models.Teams.query.filter_by(name="Red").one()
        assert TeamTrack.query.get(team.id).track == "red-team"

    def test_unknown_track_ignored(self, app, models, load_plugin):
        load_plugin()
        with patch(
            "track_filter.team_creation.get_current_team", side_effect=_newest_team(models)
        ):
            app.test_client().post("/teams/new", data={"name": "P", "track": "purple"})
        assert TeamTrack.query.count() == 0

    def test_self_select_false_ignores_submitted_track(self, app, models, load_plugin):
        override_template = load_plugin(**dict(MIXED_CONFIG, self_select=False))
        assert "teams/new.html" not in _overridden(override_template)
        with patch(
            "track_filter.team_creation.get_current_team", side_effect=_newest_team(models)
        ):
            resp = app.test_client().post(
                "/teams/new", data={"name": "Sneaky", "track": "blue-team"}
            )
        assert resp.status_code == 302
        assert TeamTrack.query.count() == 0

    def test_track_on_registration_is_ignored(self, app, models, load_plugin):
        load_plugin(**dict(MIXED_CONFIG, self_select=False))
        app.test_client().post("/register", data={"name": "u", "track": "support"})
        assert UserTrack.query.count() == 0
        assert TeamTrack.query.count() == 0

    def test_form_options_come_from_config(self, app, load_plugin):
        load_plugin(**MIXED_CONFIG)
        template = os.path.join(
            os.path.dirname(track_filter.__file__),
            "templates", "overrides", "team_creation.html",
        )
        with open(template) as f:
            source = f.read().replace('{% extends "teams/new.html" %}', "")
        with app.test_request_context():
            app.add_url_rule("/teams/new", "teams.new")
            html = render_template_string(source, nonce="n")
        assert 'value="blue-team"' in html
        assert 'value="support"' in html
        assert "red-team" not in html


class TestTheme:
    def _body_class(self, app, user=None, team=None):
        with app.test_request_context(), logged_in(user, team):
            return render_template_string("{{ track_body_class }}")

    def test_body_class_follows_user_track_not_team(self, app, models, load_plugin):
        load_plugin(**MIXED_CONFIG)
        team = make_team(models, "Mixed", track="blue-team")
        agent = make_user(models, "Agent", team, track="support")
        defender = make_user(models, "Defender", team)
        assert self._body_class(app, agent, team) == "track-themed track-support"
        assert self._body_class(app, defender, team) == "track-themed track-blue-team"

    def test_legacy_body_class(self, app, models, load_plugin):
        load_plugin()
        team = make_team(models, "Alpha", track="red-team")
        assert self._body_class(app, None, team) == "track-themed track-red"

    def test_no_track_no_class(self, app, models, load_plugin):
        load_plugin()
        assert self._body_class(app) == ""

    def test_base_inject_renders_generated_theme(self, app, models, load_plugin):
        load_plugin()
        team = make_team(models, "Alpha", track="blue-team")
        with open(BASE_INJECT) as f:
            source = f.read()
        with app.test_request_context(), logged_in(None, team):
            html = render_template_string(source)
        assert "body.track-blue {" in html
        assert "--track-accent: #2563eb;" in html
        assert '"track-themed track-blue".split' in html


class TestInvalidConfig:
    def test_load_fails_fast(self, app, load_plugin):
        from track_filter.config import ConfigError

        with pytest.raises(ConfigError):
            load_plugin(tracks=[{"id": "Bad Id", "category_prefix": "X"}])
