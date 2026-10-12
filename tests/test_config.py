"""Tests for the plugin configuration (track definitions and options)."""

import json

import pytest

from track_filter.config import (
    ConfigError,
    DEFAULT_CONFIG_PATH,
    load_config,
    parse_config,
)

VALMONT_PATH = DEFAULT_CONFIG_PATH.replace("config.json", "examples/valmont.json")


def _track(track_id="cs-tip", prefix="CS-TIP", **extra):
    return dict({"id": track_id, "category_prefix": prefix}, **extra)


class TestDefaultConfig:
    """The shipped config.json must reproduce the historical behaviour."""

    def test_default_tracks_are_red_and_blue(self):
        cfg = load_config(override_path="")
        assert cfg.track_ids() == ["red-team", "blue-team"]
        assert cfg.get("red-team").category_prefix == "Red Team"
        assert cfg.get("blue-team").category_prefix == "Blue Team"

    def test_default_body_classes_unchanged(self):
        cfg = load_config(override_path="")
        assert cfg.get("red-team").css_class == "track-red"
        assert cfg.get("blue-team").css_class == "track-blue"

    def test_default_options_are_backward_compatible(self):
        cfg = load_config(override_path="")
        assert cfg.fallback_to_team is True
        assert cfg.self_select is True
        assert cfg.untracked == "all"
        assert cfg.hide_foreign_solves is False

    def test_default_theme_matches_legacy_css(self):
        css = load_config(override_path="").theme_css()
        assert "body.track-red {" in css
        assert "--track-accent: #dc2626;" in css
        assert "--track-border: rgba(220, 38, 38, 0.25);" in css
        assert "--track-label: \"GRANITE STORM\";" in css
        assert "body.track-blue {" in css
        assert "--track-glow: rgba(37, 99, 235, 0.4);" in css


class TestCustomConfig:
    def test_valmont_example(self):
        cfg = load_config(override_path=VALMONT_PATH)
        assert cfg.track_ids() == ["blue-team", "cs-tip"]
        assert cfg.get("cs-tip").category_prefix == "CS-TIP"
        assert cfg.get("red-team") is None
        assert cfg.self_select is False
        assert cfg.untracked == "none"
        assert cfg.fallback_to_team is False

    def test_override_file_from_env(self, tmp_path, monkeypatch):
        override = tmp_path / "tracks.json"
        override.write_text(json.dumps({"tracks": [_track()], "untracked": "none"}))
        monkeypatch.setenv("TRACK_FILTER_CONFIG", str(override))
        cfg = load_config()
        assert cfg.track_ids() == ["cs-tip"]
        assert cfg.untracked == "none"
        # Keys absent from the override keep their default value
        assert cfg.self_select is True

    def test_label_defaults_to_prefix_and_class_to_id(self):
        cfg = parse_config({"tracks": [_track()]})
        track = cfg.get("cs-tip")
        assert track.label == "CS-TIP"
        assert track.css_class == "track-cs-tip"
        assert track.theme_css() == ""

    def test_theme_as_plain_class_name(self):
        cfg = parse_config({"tracks": [_track(theme="my-class")]})
        assert cfg.get("cs-tip").css_class == "my-class"

    def test_track_for_category_prefers_longest_prefix(self):
        cfg = parse_config(
            {"tracks": [_track("blue", "Blue"), _track("blue-team", "Blue Team")]}
        )
        assert cfg.track_for_category("Blue Team · 01 — Exposition").id == "blue-team"
        assert cfg.track_for_category("Blue other").id == "blue"
        assert cfg.track_for_category("CS-TIP — Site annexe") is None

    def test_banner_cannot_escape_css(self):
        cfg = parse_config(
            {"tracks": [_track(theme={"banner": 'x";}</style><script>'})]}
        )
        css = cfg.theme_css()
        assert "</style>" not in css
        assert 'x";' not in css
        assert "x\\22 " in css


class TestInvalidConfig:
    @pytest.mark.parametrize(
        "track_id",
        ["", "Red-Team", "red team", "-red", "x" * 17, None, 12, "rouge/bleu", "none"],
    )
    def test_invalid_track_id_rejected(self, track_id):
        with pytest.raises(ConfigError):
            parse_config({"tracks": [_track(track_id)]})

    def test_sixteen_char_id_accepted(self):
        cfg = parse_config({"tracks": [_track("x" * 16)]})
        assert cfg.is_valid("x" * 16)

    def test_duplicate_track_id_rejected(self):
        with pytest.raises(ConfigError):
            parse_config({"tracks": [_track(), _track()]})

    def test_missing_prefix_rejected(self):
        with pytest.raises(ConfigError):
            parse_config({"tracks": [{"id": "cs-tip"}]})

    def test_empty_tracks_rejected(self):
        with pytest.raises(ConfigError):
            parse_config({"tracks": []})

    def test_invalid_untracked_rejected(self):
        with pytest.raises(ConfigError):
            parse_config({"tracks": [_track()], "untracked": "some"})

    def test_non_boolean_option_rejected(self):
        with pytest.raises(ConfigError):
            parse_config({"tracks": [_track()], "self_select": "false"})

    def test_invalid_colour_rejected(self):
        with pytest.raises(ConfigError):
            parse_config({"tracks": [_track(theme={"accent": "red;}"})]})

    def test_invalid_css_class_rejected(self):
        with pytest.raises(ConfigError):
            parse_config({"tracks": [_track(theme={"class": "a b"})]})
