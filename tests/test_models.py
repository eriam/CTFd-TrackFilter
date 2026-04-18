"""Tests for the TeamTrack model."""

import pytest

from CTFd.models import db

from track_filter.models import TeamTrack


class TestTeamTrack:
    def test_create_and_read(self, app, teams_model):
        with app.app_context():
            team = teams_model(name="Alpha")
            db.session.add(team)
            db.session.flush()

            tt = TeamTrack(team_id=team.id, track="red-team")
            db.session.add(tt)
            db.session.commit()

            result = TeamTrack.query.get(team.id)
            assert result is not None
            assert result.track == "red-team"
            assert result.team_id == team.id

    def test_repr(self, app, teams_model):
        with app.app_context():
            team = teams_model(name="Bravo")
            db.session.add(team)
            db.session.flush()

            tt = TeamTrack(team_id=team.id, track="blue-team")
            db.session.add(tt)
            db.session.commit()

            assert "blue-team" in repr(tt)

    def test_track_not_nullable(self, app, teams_model):
        with app.app_context():
            team = teams_model(name="Charlie")
            db.session.add(team)
            db.session.flush()

            tt = TeamTrack(team_id=team.id, track=None)
            db.session.add(tt)
            with pytest.raises(Exception):
                db.session.commit()

    def test_cascade_delete(self, app, teams_model):
        """Deleting a team should cascade-delete its TeamTrack."""
        with app.app_context():
            team = teams_model(name="Delta")
            db.session.add(team)
            db.session.flush()

            tt = TeamTrack(team_id=team.id, track="red-team")
            db.session.add(tt)
            db.session.commit()

            # Delete the team
            db.session.delete(team)
            db.session.commit()

            assert TeamTrack.query.get(team.id) is None

    def test_unique_team_id(self, app, teams_model):
        """team_id is the primary key — duplicates should fail."""
        with app.app_context():
            team = teams_model(name="Echo")
            db.session.add(team)
            db.session.flush()

            db.session.add(TeamTrack(team_id=team.id, track="red-team"))
            db.session.commit()

            db.session.add(TeamTrack(team_id=team.id, track="blue-team"))
            with pytest.raises(Exception):
                db.session.commit()
