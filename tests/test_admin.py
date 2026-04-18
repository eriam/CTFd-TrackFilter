"""Tests for the admin blueprint."""

from unittest.mock import patch

import pytest

from CTFd.models import db

from track_filter.admin import track_admin
from track_filter.models import TeamTrack


@pytest.fixture()
def admin_app(app, teams_model):
    """App with admin blueprint registered."""
    app.register_blueprint(track_admin)
    return app


@pytest.fixture()
def admin_client(admin_app):
    return admin_app.test_client()


class TestConfigView:
    def test_lists_teams_with_tracks(self, admin_app, admin_client, teams_model):
        with admin_app.app_context():
            t1 = teams_model(name="Alpha")
            t2 = teams_model(name="Bravo")
            db.session.add_all([t1, t2])
            db.session.flush()

            db.session.add(TeamTrack(team_id=t1.id, track="red-team"))
            db.session.commit()

            resp = admin_client.get("/admin/track_filter")
            assert resp.status_code == 200
            html = resp.data.decode()
            assert "Alpha" in html
            assert "Bravo" in html
            assert "red-team" in html or "Red Team" in html


class TestAssignTrack:
    def test_assign_red_team(self, admin_app, admin_client, teams_model):
        with admin_app.app_context():
            team = teams_model(name="Target")
            db.session.add(team)
            db.session.flush()
            db.session.commit()

            resp = admin_client.post(
                "/admin/track_filter/assign",
                data={"team_id": team.id, "track": "red-team"},
                follow_redirects=False,
            )
            assert resp.status_code in (301, 302, 303)

            tt = TeamTrack.query.get(team.id)
            assert tt is not None
            assert tt.track == "red-team"

    def test_change_track(self, admin_app, admin_client, teams_model):
        with admin_app.app_context():
            team = teams_model(name="Switcher")
            db.session.add(team)
            db.session.flush()
            db.session.add(TeamTrack(team_id=team.id, track="red-team"))
            db.session.commit()

            admin_client.post(
                "/admin/track_filter/assign",
                data={"team_id": team.id, "track": "blue-team"},
                follow_redirects=False,
            )

            tt = TeamTrack.query.get(team.id)
            assert tt.track == "blue-team"

    def test_remove_track(self, admin_app, admin_client, teams_model):
        with admin_app.app_context():
            team = teams_model(name="Remover")
            db.session.add(team)
            db.session.flush()
            db.session.add(TeamTrack(team_id=team.id, track="blue-team"))
            db.session.commit()

            admin_client.post(
                "/admin/track_filter/assign",
                data={"team_id": team.id, "track": ""},
                follow_redirects=False,
            )

            tt = TeamTrack.query.get(team.id)
            assert tt is None

    def test_invalid_track_rejected(self, admin_app, admin_client, teams_model):
        with admin_app.app_context():
            team = teams_model(name="Invalid")
            db.session.add(team)
            db.session.flush()
            db.session.commit()

            resp = admin_client.post(
                "/admin/track_filter/assign",
                data={"team_id": team.id, "track": "purple-team"},
                follow_redirects=False,
            )
            # Should redirect back with error — no TeamTrack created
            assert resp.status_code in (301, 302, 303)
            assert TeamTrack.query.get(team.id) is None
