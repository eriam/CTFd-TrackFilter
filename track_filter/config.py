"""Plugin configuration: track definitions and behaviour options.

The defaults live in ``config.json`` next to this file (the same file CTFd
reads for the admin menu entry).  A deployment can override any key with a
JSON file whose path is given in the ``TRACK_FILTER_CONFIG`` environment
variable; keys present in that file replace the defaults (``tracks`` is
replaced as a whole, not merged).
"""

import json
import os
import re
from collections import OrderedDict

CONFIG_ENV_VAR = "TRACK_FILTER_CONFIG"
DEFAULT_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.realpath(__file__)), "config.json"
)

# Must fit in the String(16) columns of TeamTrack / UserTrack.
TRACK_ID_MAX_LENGTH = 16
_TRACK_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_CSS_CLASS_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")
_HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

UNTRACKED_POLICIES = ("all", "none")
# Used as "no track" in admin filters and in the per-track scoreboard.
RESERVED_TRACK_IDS = ("none",)

# CSS custom properties generated from a track's theme colours.
_THEME_COLOR_VARS = OrderedDict(
    [
        ("accent", "--track-accent"),
        ("accent_light", "--track-accent-light"),
        ("accent_dark", "--track-accent-dark"),
        ("bg", "--track-bg"),
        ("bg_subtle", "--track-bg-subtle"),
    ]
)


class ConfigError(ValueError):
    """Raised when the plugin configuration is invalid."""


def validate_track_id(track_id):
    """Raise ConfigError unless ``track_id`` is a well-formed identifier."""
    if not isinstance(track_id, str) or not track_id:
        raise ConfigError("track id must be a non-empty string")
    if len(track_id) > TRACK_ID_MAX_LENGTH:
        raise ConfigError(
            f"track id {track_id!r} is longer than {TRACK_ID_MAX_LENGTH} characters"
        )
    if not _TRACK_ID_RE.match(track_id):
        raise ConfigError(
            f"track id {track_id!r} must use lowercase letters, digits, '-' or '_'"
        )
    if track_id in RESERVED_TRACK_IDS:
        raise ConfigError(f"track id {track_id!r} is reserved")


def _hex_to_rgb(color):
    color = color.lstrip("#")
    if len(color) == 3:
        color = "".join(c * 2 for c in color)
    return tuple(int(color[i : i + 2], 16) for i in (0, 2, 4))


def _css_string(text):
    """Quote ``text`` as a CSS string literal that cannot break out of <style>."""
    escaped = []
    for ch in text:
        if ch.isalnum() or ch in " -_.,:;!?()'&+/":
            escaped.append(ch)
        else:
            escaped.append("\\%x " % ord(ch))
    return '"' + "".join(escaped) + '"'


class Track:
    def __init__(self, id, label, category_prefix, description="", theme=None):
        self.id = id
        self.label = label
        self.category_prefix = category_prefix
        self.description = description
        theme = theme or {}
        self.css_class = theme.get("class") or f"track-{id}"
        self.colors = {k: theme[k] for k in _THEME_COLOR_VARS if theme.get(k)}
        self.banner = theme.get("banner", "")

    @property
    def accent(self):
        return self.colors.get("accent", "")

    def matches(self, category):
        """True if ``category`` (already stripped of '[Optional] ') is ours."""
        return category.startswith(self.category_prefix)

    def theme_css(self):
        """CSS variable block for ``body.<css_class>``, or '' if no colours."""
        if not self.colors and not self.banner:
            return ""
        lines = []
        for key, var in _THEME_COLOR_VARS.items():
            if key in self.colors:
                lines.append(f"    {var}: {self.colors[key]};")
        if "accent" in self.colors:
            r, g, b = _hex_to_rgb(self.colors["accent"])
            lines.append(f"    --track-accent-rgb: {r}, {g}, {b};")
            lines.append(f"    --track-surface: rgba({r}, {g}, {b}, 0.06);")
            lines.append(f"    --track-border: rgba({r}, {g}, {b}, 0.25);")
            lines.append(f"    --track-glow: rgba({r}, {g}, {b}, 0.4);")
        if self.banner:
            lines.append(f"    --track-label: {_css_string(self.banner)};")
        return "body.%s {\n%s\n}" % (self.css_class, "\n".join(lines))

    def to_dict(self):
        return {
            "id": self.id,
            "label": self.label,
            "category_prefix": self.category_prefix,
            "description": self.description,
            "css_class": self.css_class,
            "accent": self.accent,
        }

    def __repr__(self):
        return f"<Track {self.id} prefix={self.category_prefix!r}>"


class TrackConfig:
    def __init__(
        self,
        tracks,
        fallback_to_team=True,
        self_select=True,
        untracked="all",
        hide_foreign_solves=False,
    ):
        self.tracks = OrderedDict((t.id, t) for t in tracks)
        self.fallback_to_team = fallback_to_team
        self.self_select = self_select
        self.untracked = untracked
        self.hide_foreign_solves = hide_foreign_solves

    def get(self, track_id):
        """Return the Track for ``track_id``, or None if it is not configured."""
        if track_id is None:
            return None
        return self.tracks.get(track_id)

    def is_valid(self, track_id):
        return track_id in self.tracks

    def track_ids(self):
        return list(self.tracks)

    def track_for_category(self, category):
        """The track owning ``category`` (longest prefix wins), or None."""
        best = None
        for track in self.tracks.values():
            if track.matches(category) and (
                best is None or len(track.category_prefix) > len(best.category_prefix)
            ):
                best = track
        return best

    def theme_css(self):
        return "\n".join(filter(None, (t.theme_css() for t in self.tracks.values())))


def _parse_track(raw):
    if not isinstance(raw, dict):
        raise ConfigError("each entry of 'tracks' must be an object")
    track_id = raw.get("id")
    validate_track_id(track_id)

    prefix = raw.get("category_prefix")
    if not isinstance(prefix, str) or not prefix.strip():
        raise ConfigError(f"track {track_id!r}: 'category_prefix' is required")

    label = raw.get("label") or prefix
    description = raw.get("description", "")
    if not isinstance(label, str) or not isinstance(description, str):
        raise ConfigError(f"track {track_id!r}: 'label'/'description' must be strings")

    theme = raw.get("theme") or {}
    if isinstance(theme, str):
        theme = {"class": theme}
    if not isinstance(theme, dict):
        raise ConfigError(f"track {track_id!r}: 'theme' must be a string or an object")
    css_class = theme.get("class")
    if css_class is not None and not (
        isinstance(css_class, str) and _CSS_CLASS_RE.match(css_class)
    ):
        raise ConfigError(f"track {track_id!r}: invalid theme class {css_class!r}")
    for key in _THEME_COLOR_VARS:
        value = theme.get(key)
        if value is not None and not (
            isinstance(value, str) and _HEX_COLOR_RE.match(value)
        ):
            raise ConfigError(
                f"track {track_id!r}: theme '{key}' must be a #rgb or #rrggbb colour"
            )
    if not isinstance(theme.get("banner", ""), str):
        raise ConfigError(f"track {track_id!r}: theme 'banner' must be a string")

    return Track(track_id, label, prefix, description, theme)


def _parse_bool(data, key, default):
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise ConfigError(f"'{key}' must be true or false")
    return value


def parse_config(data):
    """Build a TrackConfig from a dict, raising ConfigError if it is invalid."""
    if not isinstance(data, dict):
        raise ConfigError("configuration must be a JSON object")

    raw_tracks = data.get("tracks")
    if not isinstance(raw_tracks, list) or not raw_tracks:
        raise ConfigError("'tracks' must be a non-empty list")
    tracks = [_parse_track(raw) for raw in raw_tracks]

    seen = set()
    for track in tracks:
        if track.id in seen:
            raise ConfigError(f"duplicate track id {track.id!r}")
        seen.add(track.id)

    untracked = data.get("untracked", "all")
    if untracked not in UNTRACKED_POLICIES:
        raise ConfigError(f"'untracked' must be one of {UNTRACKED_POLICIES}")

    return TrackConfig(
        tracks,
        fallback_to_team=_parse_bool(data, "fallback_to_team", True),
        self_select=_parse_bool(data, "self_select", True),
        untracked=untracked,
        hide_foreign_solves=_parse_bool(data, "hide_foreign_solves", False),
    )


def _read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        raise ConfigError(f"cannot read {path}: {e}")


def load_config(path=DEFAULT_CONFIG_PATH, override_path=None):
    """Load ``path`` and apply the override file (default: $TRACK_FILTER_CONFIG)."""
    data = _read_json(path)
    if override_path is None:
        override_path = os.environ.get(CONFIG_ENV_VAR) or None
    if override_path:
        override = _read_json(override_path)
        if not isinstance(override, dict):
            raise ConfigError(f"{override_path} must contain a JSON object")
        data = dict(data, **override)
    return parse_config(data)


_current = None


def get_config():
    """The active configuration, loaded on first use."""
    global _current
    if _current is None:
        _current = load_config()
    return _current


def set_config(config):
    """Replace the active configuration (used by load() and by tests)."""
    global _current
    _current = config
    return config


def reset_config():
    """Forget the active configuration so the next get_config() reloads it."""
    set_config(None)
