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
    "E3_Vitocal_17",
]

# Successors Viessmann announces for deprecated features that back defined
# entities. The entity keeps the deprecated feature name in its unique ID, so
# its entity ID, history, and customizations survive. It reads the successor
# whenever the device reports it and falls back to the deprecated feature on
# devices that do not report the successor yet.
# Sort the keys alphabetically.
FEATURE_SUCCESSORS = {
    "heating.configuration.dhw.temperature.minimumComfort": (
        "heating.dhw.configuration.temperature.minimumComfort"
    ),
    "heating.configuration.temperature.outside.DampingFactor": (
        "heating.configuration.temperature.outside.dampingFactor"
    ),
    "heating.dhw.sensors.temperature.hotWaterStorage": (
        "heating.dhw.sensors.temperature.dhwCylinder"
    ),
    "heating.dhw.sensors.temperature.hotWaterStorage.bottom": (
        "heating.dhw.sensors.temperature.dhwCylinder.bottom"
    ),
    "heating.dhw.sensors.temperature.hotWaterStorage.middle": (
        "heating.dhw.sensors.temperature.dhwCylinder.middle"
    ),
    "heating.dhw.sensors.temperature.hotWaterStorage.top": (
        "heating.dhw.sensors.temperature.dhwCylinder.top"
    ),
    "heating.scop.dhw": "heating.spf.dhw",
    "heating.scop.heating": "heating.spf.heating",
    "heating.scop.total": "heating.spf.total",
}

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
    # Set through the water heater entity only.
    "heating.dhw.operating.modes.active",
    "heating.dhw.operating.modes.efficient.active",
    "heating.dhw.operating.modes.efficientWithMinComfort.active",
    "heating.dhw.operating.modes.off.active",
    "heating.external.lock.active",
    "heating.gas.consumption.dhw",
    "heating.gas.consumption.heating",
    "heating.gas.consumption.summary.dhw.currentMonth",
    "heating.gas.consumption.summary.dhw.lastMonth",
    "heating.gas.consumption.summary.dhw.lastSevenDays",
    "heating.gas.consumption.summary.dhw.lastYear",
    "heating.gas.consumption.summary.heating.currentMonth",
    "heating.gas.consumption.summary.heating.lastMonth",
    "heating.gas.consumption.summary.heating.lastSevenDays",
    "heating.gas.consumption.summary.heating.lastYear",
    "heating.gas.consumption.total",
    "heating.heat.production.current.status",
    "heating.heat.production.summary.cooling.currentMonth",
    "heating.heat.production.summary.cooling.lastMonth",
    "heating.heat.production.summary.cooling.lastSevenDays",
    "heating.heat.production.summary.cooling.lastYear",
    "heating.heat.production.summary.dhw.currentMonth",
    "heating.heat.production.summary.dhw.lastMonth",
    "heating.heat.production.summary.dhw.lastSevenDays",
    "heating.heat.production.summary.dhw.lastYear",
    "heating.heat.production.summary.heating.currentMonth",
    "heating.heat.production.summary.heating.lastMonth",
    "heating.heat.production.summary.heating.lastSevenDays",
    "heating.heat.production.summary.heating.lastYear",
    "heating.heatingRod.power.consumption.summary.dhw.currentDay",
    "heating.heatingRod.power.consumption.summary.dhw.currentMonth",
    "heating.heatingRod.power.consumption.summary.dhw.lastMonth",
    "heating.heatingRod.power.consumption.summary.dhw.lastSevenDays",
    "heating.heatingRod.power.consumption.summary.dhw.lastYear",
    "heating.heatingRod.power.consumption.summary.heating.currentDay",
    "heating.heatingRod.power.consumption.summary.heating.currentMonth",
    "heating.heatingRod.power.consumption.summary.heating.lastMonth",
    "heating.heatingRod.power.consumption.summary.heating.lastSevenDays",
    "heating.heatingRod.power.consumption.summary.heating.lastYear",
    "heating.power.consumption.current.status",
    "heating.power.consumption.dhw",
    "heating.power.consumption.heating",
    "heating.power.consumption.summary.cooling.currentDay",
    "heating.power.consumption.summary.cooling.currentMonth",
    "heating.power.consumption.summary.cooling.currentYear",
    "heating.power.consumption.summary.cooling.lastMonth",
    "heating.power.consumption.summary.cooling.lastSevenDays",
    "heating.power.consumption.summary.cooling.lastYear",
    "heating.power.consumption.summary.dhw.currentDay",
    "heating.power.consumption.summary.dhw.currentMonth",
    "heating.power.consumption.summary.dhw.currentYear",
    "heating.power.consumption.summary.dhw.lastMonth",
    "heating.power.consumption.summary.dhw.lastSevenDays",
    "heating.power.consumption.summary.dhw.lastYear",
    "heating.power.consumption.summary.heating.currentDay",
    "heating.power.consumption.summary.heating.currentMonth",
    "heating.power.consumption.summary.heating.currentYear",
    "heating.power.consumption.summary.heating.lastMonth",
    "heating.power.consumption.summary.heating.lastSevenDays",
    "heating.power.consumption.summary.heating.lastYear",
    "heating.power.consumption.total",
    "heating.power.consumption.total.currentDay",
    "heating.primaryCircuit.fans.0.current.status",
    "heating.primaryCircuit.fans.1.current.status",
    "heating.primaryCircuit.valves.fourThreeWay.active",
    "heating.secondaryCircuit.sensors.temperature.supply.status",
    # Legacy heat pumps such as the CU401B report these refrigerant values a
    # second time next to the defined compressor and evaporator sensors.
    "heating.sensors.pressure.suctionGas",
    "heating.sensors.temperature.hotGas",
    "heating.sensors.temperature.liquidGas",
    "heating.sensors.temperature.suctionGas",
    "heating.secondaryHeatGenerator.connectionType",
    re.compile(r"^.*\.schedule\.active$"),
    re.compile(r"^device\.zigbee\.status\.status$"),
    re.compile(r"^heating\..*\.schedule$"),
    re.compile(r"^heating\.boiler\.sensors\.temperature\..*\.status$"),
    re.compile(r"^heating\.buffer\..*\.status$"),
    re.compile(r"^heating\.bufferCylinder\..*\.status$"),
    re.compile(r"^heating\.circuits\.\d+\.active$"),
    re.compile(r"^heating\.circuits\.\d+\.name$"),
    # Set through the climate entity only.
    re.compile(r"^heating\.circuits\.\d+\.operating\.modes\.active$"),
    re.compile(r"^heating\.circuits\.\d+\.operating\.modes\..*\.active$"),
    re.compile(r"^heating\.circuits\.\d+\.sensors\.temperature\..*\.status$"),
    re.compile(r"^heating\.compressors\.\d+\.sensors\.pressure\..*\.status$"),
    re.compile(r"^heating\.compressors\.\d+\.sensors\.temperature\..*\.status$"),
    re.compile(r"^heating\.condensors\.\d+\.sensors\.temperature\..*\.status$"),
    re.compile(r"^heating\.dhw\.sensors\.temperature\..*\.status$"),
    re.compile(r"^heating\.economizers\.\d+\.sensors\.temperature\..*\.status$"),
    re.compile(r"^heating\.evaporators\.\d+\.sensors\.temperature\..*\.status$"),
    re.compile(r"^heating\.inverters\.\d+\.sensors\..*\.status$"),
    # Holiday dates are read-only and report placeholders such as "" or
    # 2000-01-01 when no holiday is planned; the active state is a binary sensor.
    re.compile(r"^heating\.operating\.programs\.holiday(AtHome)?\.(start|end)$"),
    re.compile(r"^heating\.primaryCircuit\.sensors\.temperature\..*\.status$"),
    re.compile(r"^heating\.sensors\..*\.status$"),
    re.compile(r"^ventilation\.quickmodes\.holiday\.(start|end)$"),
    # Set through the fan entity only.
    "ventilation.operating.modes.active",
]
