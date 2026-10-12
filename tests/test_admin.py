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


# --- Per-user administration -------------------------------------------------

from track_filter.models import UserTrack  # noqa: E402

from .helpers import make_team, make_user, use_config  # noqa: E402


class TestUserListing:
    @pytest.fixture()
    def mixed(self, admin_app, models):
        use_config()
        team = make_team(models, "Equipe 7", track="blue-team")
        other = make_team(models, "Equipe 8")
        defender = make_user(models, "Alice", team)
        agent = make_user(models, "Charlie", team, track="support")
        lone = make_user(models, "Zoe", other)
        return team, other, defender, agent, lone

    def test_lists_users_with_own_and_effective_track(self, admin_client, mixed):
        html = admin_client.get("/admin/track_filter").data.decode()
        assert "Alice" in html and "Charlie" in html and "Zoe" in html
        assert "Support" in html
        assert "(team)" in html  # Alice inherits blue-team from her team

    def test_filter_by_team(self, admin_client, mixed):
        team, other, *_ = mixed
        html = admin_client.get(
            f"/admin/track_filter?filter_team_id={other.id}"
        ).data.decode()
        assert "Zoe" in html
        assert "Alice" not in html

    def test_filter_by_effective_track(self, admin_client, mixed):
        html = admin_client.get("/admin/track_filter?filter_track=blue-team").data.decode()
        assert "Alice" in html
        assert "Charlie" not in html
        html = admin_client.get("/admin/track_filter?filter_track=none").data.decode()
        assert "Zoe" in html
        assert "Alice" not in html

    def test_assign_user_track(self, admin_client, mixed):
        _, _, defender, _, _ = mixed
        resp = admin_client.post(
            "/admin/track_filter/assign_user",
            data={"user_id": defender.id, "track": "support", "filter_track": "none"},
        )
        assert resp.status_code in (301, 302, 303)
        assert "filter_track=none" in resp.headers["Location"]
        assert UserTrack.query.get(defender.id).track == "support"

    def test_remove_user_track(self, admin_client, mixed):
        _, _, _, agent, _ = mixed
        admin_client.post(
            "/admin/track_filter/assign_user", data={"user_id": agent.id, "track": ""}
        )
        assert UserTrack.query.get(agent.id) is None

    def test_invalid_user_track_rejected(self, admin_client, mixed):
        _, _, defender, _, _ = mixed
        admin_client.post(
            "/admin/track_filter/assign_user", data={"user_id": defender.id, "track": "red-team"}
        )
        assert UserTrack.query.get(defender.id) is None

    def test_team_assignment_validated_against_config(self, admin_client, mixed):
        _, other, *_ = mixed
        admin_client.post(
            "/admin/track_filter/assign", data={"team_id": other.id, "track": "support"}
        )
        assert TeamTrack.query.get(other.id).track == "support"
        admin_client.post(
            "/admin/track_filter/assign", data={"team_id": other.id, "track": "red-team"}
        )
        assert TeamTrack.query.get(other.id).track == "support"
