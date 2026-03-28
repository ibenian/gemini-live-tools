"""Tests for get_static_content."""

import pytest
from gemini_live_tools import get_static_content


def test_loads_existing_js_file():
    content = get_static_content("tts-audio-player.js")
    assert len(content) > 0
    assert "TTSAudioPlayer" in content


def test_loads_another_js_file():
    content = get_static_content("voice-character-selector.js")
    assert len(content) > 0


def test_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        get_static_content("nonexistent.js")


def test_path_traversal_blocked():
    with pytest.raises(ValueError, match="must resolve inside js/"):
        get_static_content("../pyproject.toml")


def test_path_traversal_absolute_blocked():
    with pytest.raises(ValueError, match="must resolve inside js/"):
        get_static_content("/etc/passwd")


def test_path_traversal_double_dot_blocked():
    with pytest.raises(ValueError, match="must resolve inside js/"):
        get_static_content("../../README.md")
