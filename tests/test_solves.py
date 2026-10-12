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
    ais = make_user(models, "AIS", team, track="blue-team")
    cstip = make_user(models, "CSTIP", team, track="cs-tip")
    blue = make_challenge(models, "Ports ouverts", "Blue Team · 01 — Exposition", 100)
    cs = make_challenge(models, "Badge", "CS-TIP — Site annexe", 50)
    db.session.add_all(
        [
            models.Solves(challenge_id=blue.id, user_id=ais.id, team_id=team.id),
            models.Solves(challenge_id=cs.id, user_id=cstip.id, team_id=team.id),
        ]
    )
    db.session.commit()
    return team, ais, cstip


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
        team, ais, _ = team_solves
        names = _api_names(app, "/api/v1/teams/me/solves", ais, team)
        assert ("Badge", "CS-TIP — Site annexe") in names

    @pytest.mark.parametrize("url", ["/api/v1/teams/me/solves", "/api/v1/teams/{id}/solves"])
    def test_foreign_titles_masked(self, app, team_solves, url):
        use_config(hide_foreign_solves=True)
        team, ais, cstip = team_solves
        url = url.format(id=team.id)
        assert _api_names(app, url, ais, team) == [
            (HIDDEN_NAME, "CS-TIP"),
            ("Ports ouverts", "Blue Team · 01 — Exposition"),
        ]
        assert _api_names(app, url, cstip, team) == [
            ("Badge", "CS-TIP — Site annexe"),
            (HIDDEN_NAME, "Blue Team"),
        ]

    def test_admin_sees_all_titles(self, app, team_solves):
        use_config(hide_foreign_solves=True)
        team, ais, _ = team_solves
        names = _api_names(app, "/api/v1/teams/me/solves", ais, team, admin=True)
        assert HIDDEN_NAME not in [n for n, _ in names]


class TestTeamPages:
    @pytest.mark.parametrize("url", ["/team", "/teams/{id}"])
    def test_foreign_titles_masked_on_team_pages(self, app, team_solves, url):
        use_config(hide_foreign_solves=True)
        team, ais, _ = team_solves
        assert _page_names(app, url.format(id=team.id), ais, team) == [
            (HIDDEN_NAME, "CS-TIP", 50),
            ("Ports ouverts", "Blue Team · 01 — Exposition", 100),
        ]

    def test_other_endpoints_get_real_objects(self, app, team_solves):
        use_config(hide_foreign_solves=True)
        team, ais, _ = team_solves
        names = _page_names(app, "/api/v1/teams/me/solves", ais, team)
        assert HIDDEN_NAME not in [n for n, _, _ in names]

    def test_masked_solve_is_read_only(self, app, team_solves):
        use_config(hide_foreign_solves=True)
        team, ais, _ = team_solves
        with app.test_request_context("/team"), logged_in(ais, team):
            masked = [s for s in team.get_solves() if s.challenge.name == HIDDEN_NAME]
            with pytest.raises(AttributeError):
                masked[0].challenge.name = "x"
        # The real challenge row is untouched
        from CTFd.models import Challenges

        assert Challenges.query.filter_by(name="Badge").count() == 1

    def test_disabled_option_leaves_pages_alone(self, app, team_solves):
        use_config()
        team, ais, _ = team_solves
        names = _page_names(app, "/team", ais, team)
        assert ("Badge", "CS-TIP — Site annexe", 50) in names
