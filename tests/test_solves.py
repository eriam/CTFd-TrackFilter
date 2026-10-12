"""Tests for hide_foreign_solves (team solves API and team pages)."""

import pytest
from flask import jsonify

from CTFd.models import db

from track_filter.solves import HIDDEN_NAME, register_solve_masking

from .helpers import logged_in, make_challenge, make_team, make_user, use_config


@pytest.fixture()
def team_solves(app, models):
    register_solve_masking(app)

    def solves_json(**_):
        team = models.Teams.query.first()
        return jsonify(
            {
                "success": True,
                "data": [
                    {
                        "challenge_id": s.challenge.id,
                        "challenge": {
                            "id": s.challenge.id,
                            "name": s.challenge.name,
                            "category": s.challenge.category,
                            "value": s.challenge.value,
                        },
                    }
                    for s in team.get_solves(admin=True)
                ],
            }
        )

    app.add_url_rule("/api/v1/teams/me/solves", "team_me_solves", solves_json)
    app.add_url_rule("/api/v1/teams/<int:team_id>/solves", "team_solves", solves_json)
    app.add_url_rule("/team", "teams.private", lambda: "")
    app.add_url_rule("/teams/<int:team_id>", "teams.public", lambda team_id: "")

    team = make_team(models, "Equipe mixte")
    defender = make_user(models, "Defender", team, track="blue-team")
    agent = make_user(models, "Agent", team, track="support")
    blue = make_challenge(models, "Open ports", "Blue Team · 01 — Recon", 100)
    cs = make_challenge(models, "Badge", "Support — Helpdesk", 50)
    db.session.add_all(
        [
            models.Solves(challenge_id=blue.id, user_id=defender.id, team_id=team.id),
            models.Solves(challenge_id=cs.id, user_id=agent.id, team_id=team.id),
        ]
    )
    db.session.commit()
    return team, defender, agent


def _api_names(app, url, user, team, admin=False):
    with logged_in(user, team, admin):
        data = app.test_client().get(url).get_json()["data"]
    return sorted((d["challenge"]["name"], d["challenge"]["category"]) for d in data)


def _page_names(app, url, user, team, admin=False):
    with app.test_request_context(url), logged_in(user, team, admin):
        return sorted(
            (s.challenge.name, s.challenge.category, s.challenge.value)
            for s in team.get_solves()
        )


class TestTeamSolvesApi:
    def test_disabled_by_default(self, app, team_solves):
        use_config()
        team, defender, _ = team_solves
        names = _api_names(app, "/api/v1/teams/me/solves", defender, team)
        assert ("Badge", "Support — Helpdesk") in names

    @pytest.mark.parametrize("url", ["/api/v1/teams/me/solves", "/api/v1/teams/{id}/solves"])
    def test_foreign_titles_masked(self, app, team_solves, url):
        use_config(hide_foreign_solves=True)
        team, defender, agent = team_solves
        url = url.format(id=team.id)
        assert _api_names(app, url, defender, team) == [
            (HIDDEN_NAME, "Support"),
            ("Open ports", "Blue Team · 01 — Recon"),
        ]
        assert _api_names(app, url, agent, team) == [
            ("Badge", "Support — Helpdesk"),
            (HIDDEN_NAME, "Blue Team"),
        ]

    def test_admin_sees_all_titles(self, app, team_solves):
        use_config(hide_foreign_solves=True)
        team, defender, _ = team_solves
        names = _api_names(app, "/api/v1/teams/me/solves", defender, team, admin=True)
        assert HIDDEN_NAME not in [n for n, _ in names]


class TestTeamPages:
    @pytest.mark.parametrize("url", ["/team", "/teams/{id}"])
    def test_foreign_titles_masked_on_team_pages(self, app, team_solves, url):
        use_config(hide_foreign_solves=True)
        team, defender, _ = team_solves
        assert _page_names(app, url.format(id=team.id), defender, team) == [
            (HIDDEN_NAME, "Support", 50),
            ("Open ports", "Blue Team · 01 — Recon", 100),
        ]

    def test_other_endpoints_get_real_objects(self, app, team_solves):
        use_config(hide_foreign_solves=True)
        team, defender, _ = team_solves
        names = _page_names(app, "/api/v1/teams/me/solves", defender, team)
        assert HIDDEN_NAME not in [n for n, _, _ in names]

    def test_masked_solve_is_read_only(self, app, team_solves):
        use_config(hide_foreign_solves=True)
        team, defender, _ = team_solves
        with app.test_request_context("/team"), logged_in(defender, team):
            masked = [s for s in team.get_solves() if s.challenge.name == HIDDEN_NAME]
            with pytest.raises(AttributeError):
                masked[0].challenge.name = "x"
        # The real challenge row is untouched
        from CTFd.models import Challenges

        assert Challenges.query.filter_by(name="Badge").count() == 1

    def test_disabled_option_leaves_pages_alone(self, app, team_solves):
        use_config()
        team, defender, _ = team_solves
        names = _page_names(app, "/team", defender, team)
        assert ("Badge", "Support — Helpdesk", 50) in names
