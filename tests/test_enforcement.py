"""Server-side refusal of actions on challenges outside the user's track."""

import pytest
from flask import jsonify

from CTFd.models import db

from track_filter.filter import FORBIDDEN_MESSAGE, register_filter

from .helpers import logged_in, make_challenge, make_team, make_user, use_config

SUBRESOURCES = ["solves", "files", "hints", "tags", "requirements", "solution"]


@pytest.fixture()
def guarded(app, models):
    """App with the track hooks and stand-ins for the CTFd API routes."""
    register_filter(app)

    def reached(**_):
        return jsonify({"success": True, "data": "reached"})

    def challenge_detail(challenge_id):
        chal = models.Challenges.query.get(challenge_id)
        return jsonify({"success": True, "data": {"id": chal.id, "category": chal.category}})

    app.add_url_rule("/api/v1/challenges/attempt", "attempt", reached, methods=["POST"])
    app.add_url_rule("/api/v1/unlocks", "unlocks", reached, methods=["POST"])
    app.add_url_rule("/api/v1/challenges/<int:challenge_id>", "detail", challenge_detail)
    app.add_url_rule(
        "/api/v1/challenges/<int:challenge_id>/<sub>",
        "sub",
        reached,
        methods=["GET", "PUT"],
    )
    app.add_url_rule("/api/v1/hints/<int:hint_id>", "hint", reached)
    app.add_url_rule("/api/v1/solutions/<int:solution_id>", "solution", reached)

    use_config(untracked="none")
    team = make_team(models, "Equipe mixte")
    ns = type("Guarded", (), {})()
    ns.client = app.test_client()
    ns.team = team
    ns.defender = make_user(models, "Defender", team, track="blue-team")
    ns.agent = make_user(models, "Agent", team, track="support")
    ns.untracked = make_user(models, "Nobody", team)
    ns.blue = make_challenge(models, "Ports", "Blue Team · 01 — Recon")
    ns.cs = make_challenge(models, "Badge", "Support — Helpdesk")
    ns.cs_optional = make_challenge(models, "Bonus", "[Optional] Support — Helpdesk")
    ns.blue_hint = models.Hints(challenge_id=ns.blue.id)
    ns.cs_hint = models.Hints(challenge_id=ns.cs.id)
    ns.blue_solution = models.Solutions(challenge_id=ns.blue.id)
    db.session.add_all([ns.blue_hint, ns.cs_hint, ns.blue_solution])
    db.session.commit()
    return ns


def _as(g, user, admin=False):
    return logged_in(user, g.team, admin)


class TestAttempt:
    def test_foreign_attempt_json_is_403(self, guarded):
        g = guarded
        with _as(g, g.agent):
            resp = g.client.post(
                "/api/v1/challenges/attempt",
                json={"challenge_id": g.blue.id, "submission": "flag{x}"},
            )
        assert resp.status_code == 403
        assert resp.get_json()["data"]["message"] == FORBIDDEN_MESSAGE

    def test_foreign_attempt_form_is_403(self, guarded):
        g = guarded
        with _as(g, g.defender):
            resp = g.client.post(
                "/api/v1/challenges/attempt",
                data={"challenge_id": str(g.cs.id), "submission": "flag{x}"},
            )
        assert resp.status_code == 403

    def test_own_attempt_passes(self, guarded):
        g = guarded
        with _as(g, g.agent):
            resp = g.client.post(
                "/api/v1/challenges/attempt",
                json={"challenge_id": g.cs_optional.id, "submission": "flag{x}"},
            )
        assert resp.status_code == 200
        assert resp.get_json()["data"] == "reached"

    def test_unknown_challenge_left_to_ctfd(self, guarded):
        g = guarded
        with _as(g, g.agent):
            resp = g.client.post(
                "/api/v1/challenges/attempt", json={"challenge_id": 9999}
            )
        assert resp.status_code == 200

    def test_untracked_none_attempt_refused(self, guarded):
        g = guarded
        with _as(g, g.untracked):
            resp = g.client.post(
                "/api/v1/challenges/attempt", json={"challenge_id": g.blue.id}
            )
        assert resp.status_code == 403


class TestUnlocks:
    def test_foreign_hint_unlock_is_403(self, guarded):
        g = guarded
        with _as(g, g.agent):
            resp = g.client.post(
                "/api/v1/unlocks", json={"type": "hints", "target": g.blue_hint.id}
            )
        assert resp.status_code == 403
        assert resp.get_json()["errors"]["target"] == [FORBIDDEN_MESSAGE]

    def test_foreign_solution_unlock_is_403(self, guarded):
        g = guarded
        with _as(g, g.agent):
            resp = g.client.post(
                "/api/v1/unlocks",
                json={"type": "solutions", "target": g.blue_solution.id},
            )
        assert resp.status_code == 403

    def test_own_hint_unlock_passes(self, guarded):
        g = guarded
        with _as(g, g.agent):
            resp = g.client.post(
                "/api/v1/unlocks", json={"type": "hints", "target": g.cs_hint.id}
            )
        assert resp.status_code == 200

    def test_unknown_type_left_to_ctfd(self, guarded):
        g = guarded
        with _as(g, g.agent):
            resp = g.client.post("/api/v1/unlocks", json={"type": "users", "target": 1})
        assert resp.status_code == 200


class TestReadRoutes:
    @pytest.mark.parametrize("sub", SUBRESOURCES)
    def test_foreign_subresource_is_404(self, guarded, sub):
        g = guarded
        with _as(g, g.defender):
            resp = g.client.get(f"/api/v1/challenges/{g.cs.id}/{sub}")
        assert resp.status_code == 404

    @pytest.mark.parametrize("sub", SUBRESOURCES)
    def test_own_subresource_passes(self, guarded, sub):
        g = guarded
        with _as(g, g.defender):
            resp = g.client.get(f"/api/v1/challenges/{g.blue.id}/{sub}")
        assert resp.status_code == 200

    def test_foreign_detail_is_404(self, guarded):
        g = guarded
        with _as(g, g.defender):
            assert g.client.get(f"/api/v1/challenges/{g.cs.id}").status_code == 404
            assert g.client.get(f"/api/v1/challenges/{g.blue.id}").status_code == 200

    def test_404_body_matches_unknown_challenge(self, guarded):
        g = guarded
        with _as(g, g.defender):
            body = g.client.get(f"/api/v1/challenges/{g.cs.id}/solves").get_json()
        assert set(body) == {"message"}

    def test_foreign_rating_is_403(self, guarded):
        g = guarded
        with _as(g, g.defender):
            resp = g.client.put(f"/api/v1/challenges/{g.cs.id}/ratings", json={"value": 1})
        assert resp.status_code == 403

    def test_foreign_hint_detail_is_404(self, guarded):
        g = guarded
        with _as(g, g.agent):
            assert g.client.get(f"/api/v1/hints/{g.blue_hint.id}").status_code == 404
            assert g.client.get(f"/api/v1/hints/{g.cs_hint.id}").status_code == 200

    def test_foreign_solution_detail_is_404(self, guarded):
        g = guarded
        with _as(g, g.agent):
            resp = g.client.get(f"/api/v1/solutions/{g.blue_solution.id}")
        assert resp.status_code == 404


class TestAdminNeverFiltered:
    def test_admin_passes_everywhere(self, guarded):
        g = guarded
        admin = g.agent  # an admin who also has a track
        with _as(g, admin, admin=True):
            c = g.client
            assert c.post(
                "/api/v1/challenges/attempt", json={"challenge_id": g.blue.id}
            ).status_code == 200
            assert c.post(
                "/api/v1/unlocks", json={"type": "hints", "target": g.blue_hint.id}
            ).status_code == 200
            for sub in SUBRESOURCES:
                assert c.get(f"/api/v1/challenges/{g.blue.id}/{sub}").status_code == 200
            assert c.get(f"/api/v1/hints/{g.blue_hint.id}").status_code == 200
            assert c.get(f"/api/v1/challenges/{g.blue.id}").status_code == 200


class TestUntrackedAll:
    def test_untracked_all_is_never_refused(self, guarded):
        g = guarded
        use_config(untracked="all")
        with _as(g, g.untracked):
            assert g.client.post(
                "/api/v1/challenges/attempt", json={"challenge_id": g.cs.id}
            ).status_code == 200
            assert g.client.get(f"/api/v1/hints/{g.blue_hint.id}").status_code == 200
