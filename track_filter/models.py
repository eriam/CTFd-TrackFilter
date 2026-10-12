from CTFd.models import db

from .config import TRACK_ID_MAX_LENGTH


class TeamTrack(db.Model):
    __tablename__ = "team_tracks"

    team_id = db.Column(
        db.Integer,
        db.ForeignKey("teams.id", ondelete="CASCADE"),
        primary_key=True,
    )
    track = db.Column(db.String(TRACK_ID_MAX_LENGTH), nullable=False)

    def __repr__(self):
        return f"<TeamTrack team_id={self.team_id} track={self.track}>"


class UserTrack(db.Model):
    __tablename__ = "user_tracks"

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    track = db.Column(db.String(TRACK_ID_MAX_LENGTH), nullable=False)

    def __repr__(self):
        return f"<UserTrack user_id={self.user_id} track={self.track}>"
