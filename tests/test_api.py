"""Tests for the admin JSON API (bulk assignment, export, scoreboard)."""

import pytest

from CTFd.models import db

from track_filter.api import track_api
from track_filter.models import UserTrack

from .helpers import logged_in, make_challenge, make_team, make_user, use_config

URL = "/api/v1/track_filter/users"


@pytest.fixture()
def api(app, models):
    app.register_blueprint(track_api)
    use_config()
    team = make_team(models, "Equipe 7")
    ns = type("Api", (), {})()
    ns.client = app.test_client()
    ns.team = team
    ns.alice = make_user(models, "Alice", team, email="Alice@Valmont.example")
    ns.bob = make_user(models, "Bob", team)
    ns.carol = make_user(models, "Carol", team, track="cs-tip")
    return ns


def _post(api, body, admin=True):
    with logged_in(admin=admin, module="track_filter.api"):
        return api.client.post(URL, json=body)


def _get(api, url=URL, admin=True):
    with logged_in(admin=admin, module="track_filter.api"):
        return api.client.get(url)


class TestBulkAssign:
    def test_by_user_id(self, api):
        resp = _post(api, [{"user_id": api.alice.id, "track": "cs-tip"}])
        assert resp.status_code == 200
        row = resp.get_json()["data"][0]
        assert row["status"] == "applied"
        assert row["user_id"] == api.alice.id
        assert row["previous"] is None
        assert UserTrack.query.get(api.alice.id).track == "cs-tip"

    def test_by_email_case_insensitive(self, api):
        resp = _post(api, [{"email": "alice@valmont.example", "track": "blue-team"}])
        assert resp.get_json()["data"][0]["status"] == "applied"
        assert UserTrack.query.get(api.alice.id).track == "blue-team"

    def test_by_name(self, api):
        resp = _post(api, [{"name": "Bob", "track": "cs-tip"}])
        assert resp.get_json()["data"][0]["status"] == "applied"
        assert UserTrack.query.get(api.bob.id).track == "cs-tip"

    def test_change_reports_previous_track(self, api):
        row = _post(api, [{"name": "Carol", "track": "blue-team"}]).get_json()["data"][0]
        assert row["previous"] == "cs-tip"
        assert UserTrack.query.get(api.carol.id).track == "blue-team"

    def test_empty_track_removes(self, api):
        row = _post(api, [{"user_id": api.carol.id, "track": ""}]).get_json()["data"][0]
        assert row["status"] == "applied"
        assert row["track"] is None
        assert UserTrack.query.get(api.carol.id) is None

    def test_invalid_track_rejected(self, api):
        body = _post(api, [{"user_id": api.alice.id, "track": "red-team"}]).get_json()
        assert body["success"] is False
        assert body["data"][0]["status"] == "error"
        assert "invalid track" in body["data"][0]["error"]
        assert UserTrack.query.get(api.alice.id) is None

    def test_mixed_rows_reported_line_by_line(self, api):
        body = _post(
            api,
            [
                {"user_id": api.alice.id, "track": "blue-team"},
                {"email": "nobody@example.org", "track": "cs-tip"},
                {"name": "Bob"},
                {"track": "cs-tip"},
                "not an object",
                {"user_id": "abc", "track": "cs-tip"},
                {"name": "Bob", "track": "cs-tip"},
            ],
        ).get_json()
        statuses = [(r["index"], r["status"], r.get("error")) for r in body["data"]]
        assert statuses == [
            (0, "applied", None),
            (1, "error", "user not found"),
            (2, "error", statuses[2][2]),
            (3, "error", "missing user_id, email or name"),
            (4, "error", "row must be an object"),
            (5, "error", "invalid user_id"),
            (6, "applied", None),
        ]
        assert "invalid track" in statuses[2][2]
        assert body["meta"] == {"applied": 2, "errors": 5}
        assert UserTrack.query.get(api.alice.id).track == "blue-team"
        assert UserTrack.query.get(api.bob.id).track == "cs-tip"

    def test_body_must_be_a_list(self, api):
        assert _post(api, {"user_id": 1, "track": "cs-tip"}).status_code == 400

    def test_non_admin_refused(self, api):
        resp = _post(api, [{"user_id": api.alice.id, "track": "cs-tip"}], admin=False)
        assert resp.status_code == 403
        assert UserTrack.query.get(api.alice.id) is None


class TestExport:
    def test_export_assignments(self, api):
        body = _get(api).get_json()
        rows = {r["name"]: r for r in body["data"]}
        assert body["meta"]["count"] == 3
        assert rows["Carol"]["track"] == "cs-tip"
        assert rows["Carol"]["effective_track"] == "cs-tip"
        assert rows["Carol"]["team"] == "Equipe 7"
        assert rows["Alice"]["effective_track"] is None

    def test_export_filters(self, api):
        names = [r["name"] for r in _get(api, URL + "?track=cs-tip").get_json()["data"]]
        assert names == ["Carol"]
        names = [r["name"] for r in _get(api, URL + "?track=none").get_json()["data"]]
        assert names == ["Alice", "Bob"]

    def test_export_non_admin_refused(self, api):
        assert _get(api, admin=False).status_code == 403


class TestScoreboard:
    def test_points_split_by_member_track(self, api, models):
        blue = make_challenge(models, "Ports", "Blue Team · 01 — Exposition", 100)
        cs = make_challenge(models, "Badge", "CS-TIP — Site annexe", 50)
        db.session.add(UserTrack(user_id=api.alice.id, track="blue-team"))
        db.session.add_all(
            [
                models.Solves(challenge_id=blue.id, user_id=api.alice.id, team_id=api.team.id),
                models.Solves(challenge_id=cs.id, user_id=api.carol.id, team_id=api.team.id),
                models.Solves(challenge_id=blue.id, user_id=api.bob.id, team_id=api.team.id),
                models.Awards(user_id=api.carol.id, team_id=api.team.id, value=-10),
            ]
        )
        db.session.commit()

        body = _get(api, "/api/v1/track_filter/scoreboard").get_json()
        entry = body["data"][0]
        assert entry["name"] == "Equipe 7"
        assert entry["total"] == 240
        assert entry["by_track"] == {"blue-team": 100, "cs-tip": 40, "none": 100}

    def test_scoreboard_non_admin_refused(self, api):
        resp = _get(api, "/api/v1/track_filter/scoreboard", admin=False)
        assert resp.status_code == 403
