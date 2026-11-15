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
    "E3_Vitocal_262_02",
    "E3_Vitodens_300_0419",
    "E3_VitoPure",
    "CU401B_G",
    "E3_VitoCharge_Evolution_08",
    "E3_ViAir_300F_13",
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

# Features that create no entity on any platform. A string matches one feature
# name; a compiled pattern matches a family, such as numbered components. An
# ignored feature also hides a defined entity, so keep patterns narrow.
# Sensor connection statuses such as `connected` need no entry; the discovery
# skips them next to their reading. Sort the entries of each group.
IGNORED_FEATURES = [
    # Identifiers and serial numbers.
    "device.brand",
    "device.etn",
    "device.parameterIdentification.version",
    "device.productIdentification.product",
    "device.productMatrix.product",
    "device.serial",
    "device.serial.internalComponents.vinList",
    "device.type",
    "device.variant",
    "heating.boiler.serial",
    "heating.controller.serial",
    "heating.device.variant",
    re.compile(r"^ess\.version\.hardware\.[^.]+$"),
    re.compile(r"^ventilation\.filter\.information\.[^.]+$"),
    # Static installation details and capability flags.
    "device.configuration.houseLocation.altitude",
    "ess.configuration.systemType",
    "ess.power.nominal.inverter",
    "heating.burners.enabled",
    "heating.circuits.enabled",
    "heating.circuits.internal",
    "heating.compressors.enabled",
    "heating.configuration.buffer.temperature.max",
    "heating.configuration.bufferCylinderSize",
    "heating.configuration.centralHeatingCylinderSize",
    "heating.configuration.dhwCylinderSize",
    "heating.configuration.dhwHeater.useApproved",
    "heating.configuration.gasType",
    "heating.configuration.heatingRod.dhw.useApproved",
    "heating.configuration.heatingRod.heating.useApproved",
    "heating.configuration.houseHeatingLoad",
    "heating.configuration.houseLocation.latitude",
    "heating.configuration.houseLocation.longitude",
    "heating.configuration.houseOrientation.horizontal",
    "heating.configuration.houseOrientation.vertical",
    "heating.secondaryHeatGenerator.connectionType",
    "pcc.state.gridCode",
    "photovoltaic.installedPeakPower",
    "photovoltaic.string.enabled",
    # Successors that no device reports yet: the inverter country code
    # replaces pcc.state.gridCode, the gas type heating.configuration.gasType.
    "ess.inverter.configuration.countryCode",
    "heating.gas.configuration.type",
    # A capability flag: True on ventilation devices, whose fan entity shows
    # whether they ventilate, and False on devices without ventilation.
    "ventilation.active",
    # The rated power of the compressor.
    re.compile(r"^heating\.compressors\.\d+\.power$"),
    re.compile(r"^heating\.coolingCircuits\.\d+\.type$"),
    re.compile(
        r"^heating\.circuits\.\d+\.operating\.programs\.screedDrying\."
        r"heatpump\.useApproved$"
    ),
    # Installation details of ventilation units: commissioning, capability
    # flags, air balance, configured level volume flows and bypass thresholds,
    # the fan assignment, and the actuator self-test.
    "ventilation.fan.assignmentSwitch.active",
    re.compile(r"^device\.commissioning\.information\.[^.]+$"),
    re.compile(r"^ventilation\.air\.balance\.offset\.[^.]+$"),
    re.compile(r"^ventilation\.bypass\.configuration\.temperature\..+$"),
    re.compile(r"^ventilation\.features\.[^.]+\.active$"),
    re.compile(r"^ventilation\.levels\.[^.]+\.volumeFlow$"),
    re.compile(r"^ventilation\.sensors\.actuator\.selftest\.[^.]+$"),
    # Feature flags and network settings of energy storage systems.
    re.compile(r"^ess\.features\.[^.]+\.active$"),
    re.compile(r"^tcu\.ethernet\.\d+\.config\.mode$"),
    # Device internals: service tests, clock settings, radio status, locks,
    # power limits, and raw message logs.
    "device.actorSensorTest.active",
    "device.actorSensorTest.status",
    "device.lock.external.active",
    "device.lock.malfunction.active",
    "device.messages.info.raw",
    "device.messages.logbook",
    "device.messages.service.raw",
    "device.power.consumption.limitation",
    "device.power.statusReport.consumption.limit",
    "device.power.statusReport.consumption.status",
    "device.power.statusReport.production.limit",
    "device.power.statusReport.production.status",
    "device.time.daylightSaving.active",
    "device.time.daylightSaving.begin",
    "device.time.daylightSaving.end",
    "device.zigbee.active.active",
    "device.zigbee.status.status",
    "heating.external.lock.active",
    "heating.primaryCircuit.valves.fourThreeWay.active",
    "ventilation.external.lock.active",
    re.compile(r"^ventilation\.lockExternal\.[^.]+$"),
    # Raw history arrays and summary periods of the energy and gas counters.
    # The defined sensors report the day, the year, and the lifetime totals.
    "heating.gas.consumption.dhw",
    "heating.gas.consumption.heating",
    "heating.gas.consumption.total",
    "heating.power.consumption.dhw",
    "heating.power.consumption.heating",
    "heating.power.consumption.total",
    "heating.power.consumption.total.currentDay",
    re.compile(
        r"^heating\.(gas\.consumption|heat\.production)\.summary\.[^.]+\."
        r"(currentMonth|lastMonth|lastSevenDays|lastYear)$"
    ),
    re.compile(
        r"^heating\.heatingRod\.power\.consumption\.summary\.[^.]+\."
        r"(currentDay|currentMonth|lastMonth|lastSevenDays|lastYear)$"
    ),
    re.compile(r"^heating\.power\.consumption\.summary\.[^.]+\.[^.]+$"),
    re.compile(r"^ess\.transfer\.(charge|discharge)\.cumulated\.current(Week|Month)$"),
    re.compile(r"^photovoltaic\.production\.cumulated\.current(Week|Month)$"),
    # Values that a defined entity already reports.
    # Absent battery modules report 0; the usable system energy covers them.
    re.compile(r"^ess\.battery\.usedAverage\.usableEnergyModule[A-Za-z]+$"),
    # Deprecated copies of the defined heating.bufferCylinder sensors.
    re.compile(r"^heating\.buffer\.sensors\.temperature\.[^.]+$"),
    # Legacy heat pumps such as the CU401B report these refrigerant values a
    # second time next to the defined compressor and evaporator sensors.
    "heating.sensors.pressure.suctionGas",
    "heating.sensors.temperature.hotGas",
    "heating.sensors.temperature.liquidGas",
    "heating.sensors.temperature.suctionGas",
    # The string name labels the PV string readings.
    re.compile(r"^photovoltaic\.string\.\d+\.name$"),
    # The bypass mode sensor shows the active mode.
    "ventilation.bypass.operating.modes.active.level",
    "ventilation.bypass.operating.modes.active.state",
    re.compile(r"^ventilation\.bypass\.operating\.modes\.[^.]+\.active$"),
    # Command availability flags of the quick mode switches.
    re.compile(r"^ventilation\.quickmodes\.[^.]+\.isCommandExecutable$"),
    # Set or shown through the climate entity: the operating mode, the active
    # program as its preset, and the program demand as its current action.
    re.compile(r"^heating\.circuits\.\d+\.active$"),
    re.compile(r"^heating\.circuits\.\d+\.name$"),
    re.compile(r"^heating\.circuits\.\d+\.operating\.modes\.active$"),
    re.compile(r"^heating\.circuits\.\d+\.operating\.modes\..*\.active$"),
    re.compile(
        r"^heating\.circuits\.\d+\.operating\.programs\.(normal|reduced)\.active$"
    ),
    re.compile(
        r"^heating\.circuits\.\d+\.operating\.programs\."
        r"(comfort|normal|reduced)\.demand$"
    ),
    # Set through the water heater entity.
    "heating.dhw.operating.modes.active",
    "heating.dhw.operating.modes.balanced.active",
    "heating.dhw.operating.modes.efficient.active",
    "heating.dhw.operating.modes.efficientWithMinComfort.active",
    "heating.dhw.operating.modes.off.active",
    # Set or shown through the fan entity: the operating mode, standby, and
    # the active level as its speed. What the demand reports beyond
    # "ventilation" is not documented.
    "ventilation.operating.modes.active",
    "ventilation.operating.programs.active",
    "ventilation.operating.state.demand",
    "ventilation.quickmodes.standby.active",
    re.compile(r"^ventilation\.operating\.modes\.[^.]+\.active$"),
    # Schedules are structured data; the switches and the climate entity cover
    # their effect.
    re.compile(r"^.*\.schedule\.active$"),
    re.compile(r"^heating\..*\.schedule$"),
    # Holiday dates are read-only and report placeholders such as "" or
    # 2000-01-01 when no holiday is planned; the active state is a binary sensor.
    re.compile(r"^heating\.operating\.programs\.holiday(AtHome)?\.(start|end)$"),
    re.compile(r"^ventilation\.quickmodes\.holiday\.(start|end)$"),
]
