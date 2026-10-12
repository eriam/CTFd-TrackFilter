"""Track resolution: which track applies to a given user."""

from CTFd.models import db

from .config import get_config
from .models import TeamTrack, UserTrack


def load_assignments():
    """All stored assignments as ``({user_id: track}, {team_id: track})``."""
    user_tracks = {ut.user_id: ut.track for ut in UserTrack.query.all()}
    team_tracks = {tt.team_id: tt.track for tt in TeamTrack.query.all()}
    return user_tracks, team_tracks


def effective_track_id(user_id, team_id, user_tracks, team_tracks, config=None):
    """Resolve a track id from preloaded assignment dicts.

    1. the user's own track;
    2. otherwise, if ``fallback_to_team`` is on, the track of the user's team;
    3. otherwise None.

    Stored values that are not (or no longer) configured are ignored.
    """
    cfg = config or get_config()
    own = user_tracks.get(user_id) if user_id is not None else None
    if cfg.is_valid(own):
        return own
    if cfg.fallback_to_team and team_id is not None:
        inherited = team_tracks.get(team_id)
        if cfg.is_valid(inherited):
            return inherited
    return None


def resolve_track_id(user_id, team_id, config=None):
    """Same as effective_track_id() but reads only the two rows it needs."""
    user_tracks, team_tracks = {}, {}
    if user_id is not None:
        ut = UserTrack.query.get(user_id)
        if ut is not None:
            user_tracks[user_id] = ut.track
    if team_id is not None:
        tt = TeamTrack.query.get(team_id)
        if tt is not None:
            team_tracks[team_id] = tt.track
    return effective_track_id(user_id, team_id, user_tracks, team_tracks, config)


def _set_track(model, key, key_value, track):
    """Create, update or (track == "") delete one assignment row.

    Returns the previous track (or None).  Does not commit.
    """
    existing = model.query.get(key_value)
    previous = existing.track if existing else None
    if track == "":
        if existing:
            db.session.delete(existing)
    elif existing:
        existing.track = track
    else:
        db.session.add(model(**{key: key_value, "track": track}))
    return previous


def set_user_track(user_id, track):
    return _set_track(UserTrack, "user_id", user_id, track)


def set_team_track(team_id, track):
    return _set_track(TeamTrack, "team_id", team_id, track)


def user_rows(team_id=None, track=None, config=None):
    """Users with their team, own, team and effective tracks.

    ``track`` filters on the effective track; "none" keeps users without one.
    """
    from CTFd.models import Teams, Users

    cfg = config or get_config()
    user_tracks, team_tracks = load_assignments()
    team_names = {t.id: t.name for t in Teams.query.all()}

    query = Users.query.order_by(Users.id)
    if team_id is not None:
        query = query.filter(Users.team_id == team_id)

    rows = []
    for user in query.all():
        effective = effective_track_id(
            user.id, user.team_id, user_tracks, team_tracks, cfg
        )
        if track == "none" and effective is not None:
            continue
        if track not in (None, "", "none") and effective != track:
            continue
        rows.append(
            {
                "user_id": user.id,
                "name": user.name,
                "email": user.email,
                "team_id": user.team_id,
                "team": team_names.get(user.team_id),
                "track": user_tracks.get(user.id),
                "team_track": team_tracks.get(user.team_id),
                "effective_track": effective,
            }
        )
    return rows
