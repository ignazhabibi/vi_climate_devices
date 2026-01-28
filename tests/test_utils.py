"""Tests for Viessmann Climate Devices utilities."""

from custom_components.vi_climate_devices.utils import (
    beautify_name,
    is_feature_boolean_like,
)


def test_beautify_name():
    """Test name beautification."""

    # Act & Assert: Verify standard dot-separated conversion.
    assert beautify_name("heating.outside.temperature") == "Heating Outside Temperature"

    # Act & Assert: Verify edge cases (None, Empty string).
    assert beautify_name(None) is None
    assert beautify_name("") == ""

    # Act & Assert: Verify single word input.
    assert beautify_name("simple") == "Simple"


def test_is_feature_boolean_like():
    """Test boolean detection logic."""

    # Act & Assert: Verify Python Booleans.
    assert is_feature_boolean_like(True) is True
    assert is_feature_boolean_like(False) is True

    # Act & Assert: Verify String representations (Case Insensitive).
    # These should all identify as boolean-like.
    assert is_feature_boolean_like("on") is True
    assert is_feature_boolean_like("On") is True
    assert is_feature_boolean_like("ON") is True
    assert is_feature_boolean_like("off") is True
    assert is_feature_boolean_like("OFF") is True
    assert is_feature_boolean_like("true") is True
    assert is_feature_boolean_like("false") is True
    assert is_feature_boolean_like("active") is True

    # Act & Assert: Verify Non-Boolean values.
    # These should NOT identify as boolean-like.
    assert is_feature_boolean_like("standby") is False
    assert is_feature_boolean_like("error") is False
    assert is_feature_boolean_like("some_random_string") is False
    assert is_feature_boolean_like(123) is False
    assert is_feature_boolean_like(0) is False
    assert is_feature_boolean_like(1.5) is False
    assert is_feature_boolean_like(None) is False
