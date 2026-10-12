"""Tests for per-user track resolution and the untracked policy."""

import pytest

from track_filter.filter import (
    TRACK_CATEGORY_PREFIX,
    filter_challenges_by_track,
    get_current_track,
)
from track_filter.tracks import resolve_track_id

from .helpers import (
    MIXED_CHALLENGES,
    json_response,
    logged_in,
    make_team,
    make_user,
    use_config,
)


def _visible_ids(app, user=None, team=None, admin=False):
    with app.test_request_context("/api/v1/challenges", method="GET"):
        with logged_in(user, team, admin):
            resp = json_response(app, {"success": True, "data": MIXED_CHALLENGES})
            return [c["id"] for c in filter_challenges_by_track(resp).get_json()["data"]]


def _detail_status(app, challenge, user=None, team=None, admin=False):
    with app.test_request_context(f"/api/v1/challenges/{challenge['id']}"):
        with logged_in(user, team, admin):
            resp = json_response(app, {"success": True, "data": challenge})
            return filter_challenges_by_track(resp).status_code


class TestResolution:
    def test_user_track_without_team(self, app, models):
        use_config()
        user = make_user(models, "Solo", track="support")
        with app.test_request_context(), logged_in(user):
            assert get_current_track().id == "support"

    def test_user_track_overrides_team_track(self, app, models):
        use_config()
        team = make_team(models, "Mixed", track="blue-team")
        user = make_user(models, "Alice", team, track="support")
        assert resolve_track_id(user.id, team.id) == "support"

    def test_fallback_to_team(self, app, models):
        use_config()
        team = make_team(models, "Alpha", track="blue-team")
        user = make_user(models, "Bob", team)
        with app.test_request_context(), logged_in(user, team):
            assert get_current_track().id == "blue-team"

    def test_fallback_disabled(self, app, models):
        use_config(fallback_to_team=False)
        team = make_team(models, "Alpha", track="blue-team")
        user = make_user(models, "Bob", team)
        with app.test_request_context(), logged_in(user, team):
            assert get_current_track() is None

    def test_no_track_anywhere(self, app, models):
        use_config()
        team = make_team(models, "Libre")
        user = make_user(models, "Carol", team)
        assert resolve_track_id(user.id, team.id) is None

    def test_unconfigured_stored_track_is_ignored(self, app, models):
        """A track removed from the config falls through to the next rule."""
        use_config()
        team = make_team(models, "Legacy", track="blue-team")
        user = make_user(models, "Dave", team, track="red-team")
        assert resolve_track_id(user.id, team.id) == "blue-team"

    def test_prefix_view_follows_config(self, app):
        use_config()
        assert dict(TRACK_CATEGORY_PREFIX) == {
            "blue-team": "Blue Team",
            "support": "Support",
        }


class TestMixedTeam:
    """One team, one blue-team member and one support member."""

    @pytest.fixture()
    def mixed(self, app, models):
        use_config(untracked="none", fallback_to_team=False)
        team = make_team(models, "Equipe 7")
        defender = make_user(models, "Defender", team, track="blue-team")
        agent = make_user(models, "Agent", team, track="support")
        return team, defender, agent

    def test_blue_member_sees_only_blue_challenges(self, app, mixed):
        team, defender, _ = mixed
        assert _visible_ids(app, defender, team) == [1, 2]

    def test_support_member_sees_only_support_challenges(self, app, mixed):
        team, _, agent = mixed
        assert _visible_ids(app, agent, team) == [3, 4]

    def test_detail_of_other_track_is_404(self, app, mixed):
        team, defender, agent = mixed
        assert _detail_status(app, MIXED_CHALLENGES[2], defender, team) == 404
        assert _detail_status(app, MIXED_CHALLENGES[0], agent, team) == 404
        assert _detail_status(app, MIXED_CHALLENGES[0], defender, team) == 200
        assert _detail_status(app, MIXED_CHALLENGES[3], agent, team) == 200


class TestUntrackedPolicy:
    def test_untracked_all_sees_everything(self, app, models):
        use_config(untracked="all")
        user = make_user(models, "Eve")
        assert _visible_ids(app, user) == [1, 2, 3, 4]
        assert _detail_status(app, MIXED_CHALLENGES[2], user) == 200

    def test_untracked_none_sees_nothing(self, app, models):
        use_config(untracked="none")
        user = make_user(models, "Eve")
        assert _visible_ids(app, user) == []
        assert _detail_status(app, MIXED_CHALLENGES[2], user) == 404

    def test_untracked_none_applies_to_anonymous_visitors(self, app):
        use_config(untracked="none")
        assert _visible_ids(app) == []

    def test_admin_sees_everything_even_untracked_none(self, app, models):
        use_config(untracked="none")
        admin = make_user(models, "Root")
        assert _visible_ids(app, admin, admin=True) == [1, 2, 3, 4]

    def test_admin_with_a_track_is_not_filtered(self, app, models):
        use_config()
        admin = make_user(models, "Root", track="support")
        assert _visible_ids(app, admin, admin=True) == [1, 2, 3, 4]
        assert _detail_status(app, MIXED_CHALLENGES[0], admin, admin=True) == 200
