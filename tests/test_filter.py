"""Tests for challenge filtering logic."""

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from CTFd.models import db

from track_filter.filter import (
    TRACK_CATEGORY_PREFIX,
    _strip_optional,
    filter_challenges_by_track,
)
from track_filter.models import TeamTrack


# --- Helpers ------------------------------------------------------------------

SAMPLE_CHALLENGES = [
    {"id": 1, "name": "Recon Web", "category": "Red Team \u2014 reconnaissance"},
    {"id": 2, "name": "Phish Craft", "category": "Red Team \u2014 social-engineering"},
    {"id": 3, "name": "Asset Inventory", "category": "Blue Team \u2014 preparation"},
    {"id": 4, "name": "PCAP Analysis", "category": "Blue Team \u2014 forensics"},
    {"id": 5, "name": "Bonus Recon", "category": "[Optional] Red Team \u2014 bonus"},
    {"id": 6, "name": "Bonus DFIR", "category": "[Optional] Blue Team \u2014 bonus"},
]


def _make_json_response(app, data, status=200):
    """Build a Flask response that mimics CTFd's JSON API."""
    with app.test_request_context():
        from flask import jsonify

        resp = jsonify(data)
        resp.status_code = status
        return resp


# --- Unit tests for helpers ---------------------------------------------------


class TestStripOptional:
    def test_no_prefix(self):
        assert _strip_optional("Red Team \u2014 recon") == "Red Team \u2014 recon"

    def test_with_prefix(self):
        assert _strip_optional("[Optional] Red Team \u2014 bonus") == "Red Team \u2014 bonus"

    def test_no_match(self):
        assert _strip_optional("Something else") == "Something else"


class TestTrackCategoryPrefix:
    def test_red_team_prefix(self):
        assert TRACK_CATEGORY_PREFIX["red-team"] == "Red Team"

    def test_blue_team_prefix(self):
        assert TRACK_CATEGORY_PREFIX["blue-team"] == "Blue Team"


# --- Integration tests for filter_challenges_by_track -------------------------


class TestFilterChallengeList:
    """Test filtering on GET /api/v1/challenges."""

    def test_red_team_sees_only_red_challenges(self, app, teams_model):
        with app.app_context():
            team = teams_model(name="Attackers")
            db.session.add(team)
            db.session.flush()
            db.session.add(TeamTrack(team_id=team.id, track="red-team"))
            db.session.commit()

            with app.test_request_context(
                "/api/v1/challenges", method="GET"
            ):
                with patch(
                    "track_filter.filter.get_current_team",
                    return_value=team,
                ):
                    resp = _make_json_response(
                        app, {"success": True, "data": SAMPLE_CHALLENGES}
                    )
                    result = filter_challenges_by_track(resp)
                    data = result.get_json()

                    ids = [c["id"] for c in data["data"]]
                    assert ids == [1, 2, 5]

    def test_blue_team_sees_only_blue_challenges(self, app, teams_model):
        with app.app_context():
            team = teams_model(name="Defenders")
            db.session.add(team)
            db.session.flush()
            db.session.add(TeamTrack(team_id=team.id, track="blue-team"))
            db.session.commit()

            with app.test_request_context(
                "/api/v1/challenges", method="GET"
            ):
                with patch(
                    "track_filter.filter.get_current_team",
                    return_value=team,
                ):
                    resp = _make_json_response(
                        app, {"success": True, "data": SAMPLE_CHALLENGES}
                    )
                    result = filter_challenges_by_track(resp)
                    data = result.get_json()

                    ids = [c["id"] for c in data["data"]]
                    assert ids == [3, 4, 6]

    def test_optional_prefix_included(self, app, teams_model):
        """[Optional] challenges should match if the track prefix follows."""
        with app.app_context():
            team = teams_model(name="RT")
            db.session.add(team)
            db.session.flush()
            db.session.add(TeamTrack(team_id=team.id, track="red-team"))
            db.session.commit()

            with app.test_request_context(
                "/api/v1/challenges", method="GET"
            ):
                with patch(
                    "track_filter.filter.get_current_team",
                    return_value=team,
                ):
                    resp = _make_json_response(
                        app,
                        {
                            "success": True,
                            "data": [
                                {
                                    "id": 99,
                                    "category": "[Optional] Red Team \u2014 bonus",
                                }
                            ],
                        },
                    )
                    result = filter_challenges_by_track(resp)
                    data = result.get_json()
                    assert len(data["data"]) == 1

    def test_no_team_shows_all(self, app):
        """User without a team sees all challenges (e.g. admin)."""
        with app.test_request_context("/api/v1/challenges", method="GET"):
            with patch(
                "track_filter.filter.get_current_team", return_value=None
            ):
                resp = _make_json_response(
                    app, {"success": True, "data": SAMPLE_CHALLENGES}
                )
                result = filter_challenges_by_track(resp)
                data = result.get_json()
                assert len(data["data"]) == 6

    def test_team_without_track_shows_all(self, app, teams_model):
        """Team with no TeamTrack record sees everything."""
        with app.app_context():
            team = teams_model(name="Observers")
            db.session.add(team)
            db.session.flush()
            db.session.commit()

            with app.test_request_context(
                "/api/v1/challenges", method="GET"
            ):
                with patch(
                    "track_filter.filter.get_current_team",
                    return_value=team,
                ):
                    resp = _make_json_response(
                        app, {"success": True, "data": SAMPLE_CHALLENGES}
                    )
                    result = filter_challenges_by_track(resp)
                    data = result.get_json()
                    assert len(data["data"]) == 6

    def test_non_get_request_passthrough(self, app, teams_model):
        """POST requests are not filtered."""
        with app.app_context():
            team = teams_model(name="PostTeam")
            db.session.add(team)
            db.session.flush()
            db.session.add(TeamTrack(team_id=team.id, track="red-team"))
            db.session.commit()

            with app.test_request_context(
                "/api/v1/challenges", method="POST"
            ):
                with patch(
                    "track_filter.filter.get_current_team",
                    return_value=team,
                ):
                    resp = _make_json_response(
                        app, {"success": True, "data": SAMPLE_CHALLENGES}
                    )
                    result = filter_challenges_by_track(resp)
                    data = result.get_json()
                    assert len(data["data"]) == 6

    def test_unrelated_path_passthrough(self, app, teams_model):
        """Requests to other endpoints are untouched."""
        with app.app_context():
            team = teams_model(name="OtherTeam")
            db.session.add(team)
            db.session.flush()
            db.session.add(TeamTrack(team_id=team.id, track="red-team"))
            db.session.commit()

            with app.test_request_context(
                "/api/v1/scoreboard", method="GET"
            ):
                with patch(
                    "track_filter.filter.get_current_team",
                    return_value=team,
                ):
                    resp = _make_json_response(
                        app, {"success": True, "data": [{"id": 1}]}
                    )
                    result = filter_challenges_by_track(resp)
                    data = result.get_json()
                    assert len(data["data"]) == 1


class TestFilterChallengeDetail:
    """Test filtering on GET /api/v1/challenges/<id>."""

    def test_wrong_track_returns_404(self, app, teams_model):
        with app.app_context():
            team = teams_model(name="RedOnly")
            db.session.add(team)
            db.session.flush()
            db.session.add(TeamTrack(team_id=team.id, track="red-team"))
            db.session.commit()

            with app.test_request_context(
                "/api/v1/challenges/3", method="GET"
            ):
                with patch(
                    "track_filter.filter.get_current_team",
                    return_value=team,
                ):
                    resp = _make_json_response(
                        app,
                        {
                            "success": True,
                            "data": {
                                "id": 3,
                                "category": "Blue Team \u2014 forensics",
                            },
                        },
                    )
                    result = filter_challenges_by_track(resp)
                    assert result.status_code == 404

    def test_matching_track_passes_through(self, app, teams_model):
        with app.app_context():
            team = teams_model(name="RedOK")
            db.session.add(team)
            db.session.flush()
            db.session.add(TeamTrack(team_id=team.id, track="red-team"))
            db.session.commit()

            with app.test_request_context(
                "/api/v1/challenges/1", method="GET"
            ):
                with patch(
                    "track_filter.filter.get_current_team",
                    return_value=team,
                ):
                    resp = _make_json_response(
                        app,
                        {
                            "success": True,
                            "data": {
                                "id": 1,
                                "category": "Red Team \u2014 reconnaissance",
                            },
                        },
                    )
                    result = filter_challenges_by_track(resp)
                    assert result.status_code == 200
                    assert result.get_json()["data"]["id"] == 1

    def test_optional_wrong_track_returns_404(self, app, teams_model):
        with app.app_context():
            team = teams_model(name="BlueOnly")
            db.session.add(team)
            db.session.flush()
            db.session.add(TeamTrack(team_id=team.id, track="blue-team"))
            db.session.commit()

            with app.test_request_context(
                "/api/v1/challenges/5", method="GET"
            ):
                with patch(
                    "track_filter.filter.get_current_team",
                    return_value=team,
                ):
                    resp = _make_json_response(
                        app,
                        {
                            "success": True,
                            "data": {
                                "id": 5,
                                "category": "[Optional] Red Team \u2014 bonus",
                            },
                        },
                    )
                    result = filter_challenges_by_track(resp)
                    assert result.status_code == 404
