"""Constants for Viessmann Climate Devices."""

import re

DOMAIN = "vi_climate_devices"

# Devices to ignore during discovery to prevent API calls
IGNORED_DEVICES = ["gateway", "RoomControl-1"]

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
    "heating.circuits.0.heating.schedule",
    "heating.circuits.1.heating.schedule",
    "heating.circuits.2.heating.schedule",
    "heating.circuits.3.heating.schedule",
    "heating.dhw.pumps.circulation.schedule",
    "heating.dhw.schedule",
    re.compile(r"^heating\.boiler\.sensors\.temperature\..*\.status$"),
    re.compile(r"^heating\.buffer\..*\.status$"),
    re.compile(r"^heating\.bufferCylinder\..*\.status$"),
    re.compile(r"^heating\.circuits\.\d+\.sensors\.temperature\..*\.status$"),
    re.compile(r"^heating\.compressors\.\d+\.sensors\.pressure\..*\.status$"),
    re.compile(r"^heating\.compressors\.\d+\.sensors\.temperature\..*\.status$"),
    re.compile(r"^heating\.condensors\.\d+\.sensors\.temperature\..*\.status$"),
    re.compile(r"^heating\.dhw\.sensors\.temperature\..*\.status$"),
    re.compile(r"^heating\.economizers\.\d+\.sensors\.temperature\..*\.status$"),
    re.compile(r"^heating\.evaporators\.\d+\.sensors\.temperature\..*\.status$"),
    re.compile(r"^heating\.inverters\.\d+\.sensors\..*\.status$"),
    re.compile(r"^heating\.primaryCircuit\.sensors\.temperature\..*\.status$"),
    re.compile(r"^heating\.sensors\..*\.status$"),
    re.compile(r"^device\.zigbee\.status\.status$"),
    re.compile(r"^heating\.circuits\.\d+\.active$"),
    re.compile(r"^heating\.circuits\.\d+\.name$"),
    re.compile(r"^heating\.circuits\.\d+\.operating\.modes\..*\.active$"),
    re.compile(r"^heating\.circuits\.\d+\.operating\.programs\..*$"),
]
