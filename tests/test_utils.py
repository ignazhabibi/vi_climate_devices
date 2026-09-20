"""Tests for Viessmann Climate Devices utilities."""

from custom_components.vi_climate_devices.utils import (
    beautify_name,
    get_feature_bool_value,
    get_feature_number_value,
    get_feature_string_options,
    get_feature_string_value,
    get_suggested_precision,
    is_feature_boolean_like,
    normalize_sensor_value,
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
    assert (
        beautify_name("heating.heatingRod.power.consumption.summary.dhw.currentDay")
        == "Heating Rod Consumption Dhw Current Day"
    )
    assert (
        beautify_name("heating.power.consumption.summary.cooling.currentDay")
        == "Consumption Cooling Current Day"
    )
    assert (
        beautify_name("heating.configuration.pressure.total.maximumPressure")
        == "Total Maximum Pressure"
    )
    assert (
        beautify_name("heating.circuits.0.configuration.summerEco.absolute.threshold")
        == "Circuits 0 Summer Eco Absolute Threshold"
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


def test_get_feature_number_value_rejects_boolean_and_non_numeric_values():
    """Test numeric feature values preserve numbers without accepting booleans."""
    # Act and Assert: Real JSON numbers remain available to numeric entities.
    assert get_feature_number_value(12) == 12
    assert get_feature_number_value(12.5) == 12.5

    # Act and Assert: Booleans and non-numeric JSON values are not numbers.
    assert get_feature_number_value(True) is None
    assert get_feature_number_value(False) is None
    assert get_feature_number_value("12") is None
    assert get_feature_number_value([12]) is None
    assert get_feature_number_value({"value": 12}) is None


def test_get_feature_string_value_returns_only_plain_strings():
    """Test string feature values without stringifying arbitrary JSON shapes."""
    # Act and Assert: Plain strings pass through unchanged.
    assert get_feature_string_value("heating") == "heating"
    assert get_feature_string_value("") == ""

    # Act and Assert: Non-string shapes never become mode or program names.
    assert get_feature_string_value(None) is None
    assert get_feature_string_value(5) is None
    assert get_feature_string_value(True) is None
    assert get_feature_string_value(["heating"]) is None
    assert get_feature_string_value({"mode": "heating"}) is None


def test_get_feature_string_options_keeps_only_string_entries():
    """Test control options are built from strings without string conversion."""
    # Act and Assert: Missing options yield an empty list.
    assert get_feature_string_options(None) == []

    # Act and Assert: Only plain strings become options, in their original order.
    assert get_feature_string_options((5, "off", True, ["eco"], {"value": "eco"})) == [
        "off"
    ]
    assert get_feature_string_options(("off", "eco")) == ["off", "eco"]


def test_normalize_sensor_value_preserves_scalars_and_rejects_structured_values():
    """Test generic sensor values become valid states with inspectable raw data."""
    # Act and Assert: Scalar API values remain truthful Home Assistant states.
    assert normalize_sensor_value("heating") == "heating"
    assert normalize_sensor_value(12) == 12
    assert normalize_sensor_value(12.5) == 12.5
    assert normalize_sensor_value(None) is None

    # Act and Assert: Boolean and disconnected values are unavailable sensor states.
    assert normalize_sensor_value(True) is None
    assert normalize_sensor_value("Not Connected") is None

    # Act and Assert: Structured API values cannot become fabricated states.
    assert normalize_sensor_value(["a", "b"]) is None
    assert normalize_sensor_value({"state": "heating"}) is None


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
    assert get_suggested_precision(float("nan")) == 0
