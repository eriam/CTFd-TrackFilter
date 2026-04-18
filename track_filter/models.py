from CTFd.models import db


class TeamTrack(db.Model):
    __tablename__ = "team_tracks"

    team_id = db.Column(
        db.Integer,
        db.ForeignKey("teams.id", ondelete="CASCADE"),
        primary_key=True,
    )
    track = db.Column(db.String(16), nullable=False)  # "red-team" | "blue-team"

    def __repr__(self):
        return f"<TeamTrack team_id={self.team_id} track={self.track}>"
