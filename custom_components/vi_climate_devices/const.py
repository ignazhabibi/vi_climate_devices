"""Constants for Viessmann Climate Devices."""

import re

DOMAIN = "vi_climate_devices"

# Devices to ignore during discovery to prevent API calls
IGNORED_DEVICES = ["gateway", "RoomControl-1"]

# List of thoroughly tested device model_id values.
# Only these devices will have auto-discovered entities disabled by default,
# because there are well-defined entities available that provide a better UX.
# For untested devices, all entities are enabled by default so users can decide.
TESTED_DEVICES = [
    "E3_Vitocal_16",
]

# Features to ignore during auto-discovery
# List feature names (dot-notation) or regex patterns (compiled) to exclude them
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
    "heating.boiler.serial",
    "heating.circuits.enabled",
    "heating.circuits.internal",
    "heating.compressors.enabled",
    "heating.configuration.bufferCylinderSize",
    "heating.configuration.centralHeatingCylinderSize",
    "heating.configuration.dhwCylinderSize",
    "heating.configuration.heatingRod.dhw.useApproved",
    "heating.configuration.heatingRod.heating.useApproved",
    "heating.configuration.houseHeatingLoad",
    "heating.configuration.houseLocation.latitude",
    "heating.configuration.houseLocation.longitude",
    "heating.configuration.houseOrientation.horizontal",
    "heating.configuration.houseOrientation.vertical",
    "heating.device.variant",
    "heating.dhw.operating.modes.efficient.active",
    "heating.dhw.operating.modes.efficientWithMinComfort.active",
    "heating.dhw.operating.modes.off.active",
    "heating.external.lock.active",
    "heating.power.consumption.dhw",
    "heating.power.consumption.heating",
    "heating.power.consumption.total",
    "heating.primaryCircuit.fans.0.current.status",
    "heating.primaryCircuit.fans.1.current.status",
    "heating.primaryCircuit.valves.fourThreeWay.active",
    "heating.secondaryCircuit.sensors.temperature.supply.status",
    "heating.secondaryHeatGenerator.connectionType",
    re.compile(r"^device\.zigbee\.status\.status$"),
    re.compile(r"^heating\..*\.schedule$"),
    re.compile(r"^heating\.boiler\.sensors\.temperature\..*\.status$"),
    re.compile(r"^heating\.buffer\..*\.status$"),
    re.compile(r"^heating\.bufferCylinder\..*\.status$"),
    re.compile(r"^heating\.circuits\.\d+\\.active$"),
    re.compile(r"^heating\.circuits\.\d+\\.name$"),
    re.compile(r"^heating\.circuits\.\d+\\.operating\\.modes\\..*\\.active$"),
    re.compile(r"^heating\.circuits\.\d+\\.sensors\\.temperature\\..*\\.status$"),
    re.compile(r"^heating\.compressors\.\d+\.sensors\.pressure\..*\.status$"),
    re.compile(r"^heating\.compressors\.\d+\.sensors\.temperature\..*\.status$"),
    re.compile(r"^heating\.condensors\.\d+\.sensors\.temperature\..*\.status$"),
    re.compile(r"^heating\.dhw\.sensors\.temperature\..*\.status$"),
    re.compile(r"^heating\.economizers\.\d+\.sensors\.temperature\..*\.status$"),
    re.compile(r"^heating\.evaporators\.\d+\.sensors\.temperature\..*\.status$"),
    re.compile(r"^heating\.inverters\.\d+\.sensors\..*\.status$"),
    re.compile(r"^heating\.primaryCircuit\.sensors\.temperature\..*\.status$"),
    re.compile(r"^heating\.sensors\..*\.status$"),
]
