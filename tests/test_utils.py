"""Tests for Viessmann Climate Devices utilities."""

from custom_components.vi_climate_devices.utils import (
    beautify_name,
    get_feature_bool_value,
    get_suggested_precision,
    is_feature_boolean_like,
)


def test_beautify_name():
    """Test name beautification."""

    # Act & Assert: Verify standard dot-separated conversion.
    assert beautify_name("heating.outside.temperature") == "Outside Temperature"

    # Act & Assert: Verify edge cases (None, Empty string).
    assert beautify_name(None) is None
    assert beautify_name("") == ""

    # Act & Assert: Verify single word input.
    assert beautify_name("simple") == "Simple"

    # Act & Assert: Verify extended cleaning logic (heating.heat, summary, Power).
    assert (
        beautify_name("heating.heat.production.summary.dhw.currentDay")
        == "Production Dhw Current Day"
    )
    assert (
        beautify_name("device.power.consumption.limitation") == "Consumption Limitation"
    )
    assert (
        beautify_name("heating.boiler.sensors.temperature.commonSupply")
        == "Boiler Sensors Temperature Common Supply"
    )
    assert (
        beautify_name("heating.bufferCylinder.sensors.temperature.main")
        == "Buffer Cylinder Sensors Temperature Main"
    )
    assert (
        beautify_name("heating.solar.power.production.day")
        == "Solar Power Production Day"
    )


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
    assert is_feature_boolean_like("inactive") is True
    assert is_feature_boolean_like("1") is True
    assert is_feature_boolean_like("0") is True
    assert is_feature_boolean_like("enabled") is True
    assert is_feature_boolean_like("disabled") is True

    # Act & Assert: Verify Non-Boolean values.
    # These should NOT identify as boolean-like.
    assert is_feature_boolean_like("standby") is False
    assert is_feature_boolean_like("error") is False
    assert is_feature_boolean_like("some_random_string") is False
    assert is_feature_boolean_like(123) is False
    assert is_feature_boolean_like(0) is False
    assert is_feature_boolean_like(1.5) is False
    assert is_feature_boolean_like(None) is False


def test_get_feature_bool_value():
    """Test boolean interpretation logic."""

    # Act & Assert: Verification of various truthy values.
    assert get_feature_bool_value(True) is True
    assert get_feature_bool_value("on") is True
    assert get_feature_bool_value("active") is True
    assert get_feature_bool_value("1") is True
    assert get_feature_bool_value("enabled") is True
    assert get_feature_bool_value(1) is True
    assert get_feature_bool_value(1.0) is True

    # Act & Assert: Verification of various falsy values.
    assert get_feature_bool_value(False) is False
    assert get_feature_bool_value("off") is False
    assert get_feature_bool_value("inactive") is False
    assert get_feature_bool_value("0") is False
    assert get_feature_bool_value("disabled") is False
    assert get_feature_bool_value(0) is False
    assert get_feature_bool_value(0.0) is False

    # Act & Assert: Edge cases.
    assert get_feature_bool_value(None) is None
    assert get_feature_bool_value("standby") is None
    assert get_feature_bool_value("some_random_string") is None


def test_get_suggested_precision():
    """Test precision detection logic based on step."""

    # Act & Assert: Verify Whole Numbers.
    assert get_suggested_precision(1.0) == 0
    assert get_suggested_precision(1) == 0
    assert get_suggested_precision(2.0) == 0
    assert get_suggested_precision(5.0) == 0

    # Act & Assert: Verify Decimals.
    assert get_suggested_precision(0.5) == 1
    assert get_suggested_precision(0.1) == 1
    assert get_suggested_precision(0.01) == 2
    assert get_suggested_precision(0.25) == 2

    # Act & Assert: Verify Scientific/Edge cases.
    assert get_suggested_precision(0.0001) == 4
    assert get_suggested_precision(1e-06) == 6

    # Act & Assert: Edge cases.
    assert get_suggested_precision(None) is None
    assert get_suggested_precision(0.0) == 0
