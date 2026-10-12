"""Track resolution: which track applies to a given user."""

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
