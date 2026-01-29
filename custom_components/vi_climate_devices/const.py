"""Constants for Viessmann Climate Devices."""

DOMAIN = "vi_climate_devices"

# Devices to ignore during discovery to prevent API calls
IGNORED_DEVICES = ["gateway", "RoomControl-1"]

# Features to ignore during auto-discovery
# List feature names (dot-notation) to exclude them from entity creation
IGNORED_FEATURES = [
    # Example: "heating.circuits.0.sensors.temperature.outside",
]
