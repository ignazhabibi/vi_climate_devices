"""Constants for Viessmann Climate Devices."""

DOMAIN = "vi_climate_devices"

# Devices to ignore during discovery to prevent API calls
IGNORED_DEVICES = ["gateway", "RoomControl-1"]

# Features to ignore during auto-discovery
# List feature names (dot-notation) to exclude them from entity creation
IGNORED_FEATURES = [
    "device.actorSensorTest.active",
    "device.actorSensorTest.status",
    "device.brand",
    "device.configuration.houseLocation.altitude",
    "device.lock.external.active",
    "device.lock.malfunction.active",
    "device.messages.info.raw",
    "device.messages.service.raw",
    "device.messages.status.raw",
    "device.parameterIdentification.version",
    "device.power.consumption.limitation",
    "device.power.statusReport.consumption.limit",
    "device.power.statusReport.consumption.status",
    "device.power.statusReport.production.limit",
    "device.power.statusReport.production.status",
    "device.productIdentification.product",
    "device.productMatrix.product",
    "device.serial",
    "device.time.daylightSaving.active",
    "device.time.daylightSaving.begin",
    "device.time.daylightSaving.end",
    "device.type",
    "device.variant",
    "device.zigbee.active.active",
    "device.zigbee.status.status",
]
