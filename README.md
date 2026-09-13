# Viessmann Climate Devices

[![HACS](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

Viessmann Climate Devices connects Home Assistant to compatible Viessmann
heating systems through the official Viessmann IoT API. It uses OAuth 2.0 with
PKCE and the Home Assistant Application Credentials framework; no Viessmann
password is stored by the integration.

This is a custom integration distributed through HACS. It is not affiliated
with, maintained by, or supported by Viessmann or Home Assistant.

## Use cases

- See heating-system and hot-water status alongside the rest of the home.
- Control supported heating circuits, hot-water target temperature, operation
  modes, heating curves, and selected device settings from Home Assistant.
- Create automations from normal Home Assistant entity states, such as reducing
  a heating-circuit target when nobody is home or starting a one-time domestic
  hot-water charge before guests arrive.
- Track API-provided temperatures, pressures, energy values, SCOP values, and
  compressor statistics in dashboards.

## Supported devices

The integration supports devices and features exposed to the signed-in account
by the official Viessmann IoT API. Actual entities depend on the device model,
installed components, API subscription, and permissions granted to the OAuth
application.

The integration has been tested against a Viessmann Vitocal 250-A. Other
Viessmann heat pumps and boilers may work when the API exposes compatible
features, but are not yet individually verified.

The following are not represented as Home Assistant devices:

- Equipment that is not visible in the Viessmann account or whose API package
  does not grant access to its features.
- API gateway entries and `RoomControl-1`, which are intentionally ignored by
  the integration.

## Prerequisites

Before configuring the integration, you need:

1. A Viessmann account with the heating system linked to it.
2. A [Viessmann Developer Portal account](https://developer.viessmann-climatesolutions.com/start.html).
3. An OAuth application in the Developer Portal:
   - Create an application under **My Apps**.
   - Use a descriptive name such as `Home Assistant`.
   - Set the redirect URI to `https://my.home-assistant.io/redirect/oauth`.
   - Copy the generated **Client ID**.

The OAuth flow uses PKCE. Home Assistant requires the Client Secret field to
be non-empty, but the integration does not send it to Viessmann. Enter a
placeholder such as `123` when Home Assistant asks for it.

## Installation

### HACS installation

1. In Home Assistant, open HACS.
2. Select the three-dot menu, then **Custom repositories**.
3. Add `https://github.com/ignazhabibi/vi_climate_devices` with category
   **Integration**.
4. Search for **Viessmann Climate Devices** and install it.
5. Restart Home Assistant.

### Manual installation

1. Download the desired release from the
   [project releases](https://github.com/ignazhabibi/vi_climate_devices/releases).
2. Copy `custom_components/vi_climate_devices` into your Home Assistant
   configuration directory under `custom_components/`.
3. Restart Home Assistant.

### Pre-releases

If a pre-release is available, enable beta versions for this repository in
HACS before installing it. Pre-releases are intended for testing before a
stable release.

## Configuration

1. In Home Assistant, go to **Settings** > **Devices & services**.
2. Select **Add integration** and choose **Viessmann Climate Devices**.
3. When prompted, create or select an Application Credential using the Client
   ID from the Viessmann Developer Portal and a non-empty placeholder Client
   Secret.
4. Complete the Viessmann OAuth login and grant the requested access.

The integration discovers the installations and compatible devices available to
the authorized account during setup. It supports multiple devices in one
installation.

### Reauthentication

If the Viessmann refresh token is rejected, Home Assistant starts a
reauthentication flow. Complete the prompt for the existing integration; do
not remove and re-add it. Reauthentication keeps existing entities and their
history.

## Supported functionality

Only features reported by a device are added. A missing entity normally means
that the corresponding capability is not available for that device or API
account, not that setup failed.

| Platform | Functionality |
| --- | --- |
| `binary_sensor` | Operating states such as compressor, pump, defrosting, and frost-protection status |
| `climate` | Heating and cooling circuit target temperature, HVAC mode, and supported presets |
| `number` | Heating-curve values, temperature limits, hot-water target temperature, and selected configuration values |
| `select` | Hot-water and heating-circuit operation modes where exposed by the API |
| `sensor` | Temperatures, pressure, humidity, flow, energy, power, SCOP, and diagnostic statistics |
| `switch` | One-time domestic hot-water charge, hygiene function, and supported boolean controls |
| `water_heater` | Domestic hot-water target temperature and operation mode |

Entities use appropriate device classes and are grouped under their Viessmann
device. Less commonly useful auto-discovered features may be disabled by
default on tested device models; they can be enabled from the entity settings.

### Actions, triggers, and conditions

The integration does not register custom `vi_climate_devices.*` actions,
triggers, or conditions. Its controls use the standard actions provided by
their entity platforms:

- `climate.set_temperature`, `climate.set_hvac_mode`, and
  `climate.set_preset_mode`
- `water_heater.set_temperature` and `water_heater.set_operation_mode`
- `number.set_value`, `select.select_option`, `switch.turn_on`, and
  `switch.turn_off`

Use standard state and numeric-state triggers and conditions with the entities
provided by this integration. This keeps automations portable and avoids a
second, integration-specific interface for the same controls.

## Automation examples

Replace the example entity IDs with the IDs created in your Home Assistant
instance.

### Reduce a heating circuit when everybody leaves

```yaml
alias: Reduce heating when nobody is home
triggers:
  - trigger: state
    entity_id: zone.home
    to: "0"
conditions: []
actions:
  - action: climate.set_temperature
    target:
      entity_id: climate.your_heating_circuit
    data:
      temperature: 18
mode: single
```

### Start a one-time domestic hot-water charge before guests arrive

```yaml
alias: Prepare hot water before guests arrive
triggers:
  - trigger: calendar
    entity_id: calendar.guests
    event: start
    offset: "-01:00:00"
conditions: []
actions:
  - action: switch.turn_on
    target:
      entity_id: switch.your_one_time_dhw_charge
mode: single
```

### Notify when a monitored temperature falls below a threshold

```yaml
alias: Notify about low buffer temperature
triggers:
  - trigger: numeric_state
    entity_id: sensor.your_buffer_temperature
    below: 35
conditions: []
actions:
  - action: notify.notify
    data:
      message: Buffer temperature is below 35 °C.
mode: single
```

## Data updates

This is a cloud-polling integration. After the initial account discovery, it
refreshes known devices every **90 seconds** through the Viessmann API.

Writes and refreshes are serialized to prevent concurrent API requests. A
successful supported control action immediately updates the relevant entity
state from the API response; it does not reset or replace the scheduled poll.
If a refresh for a device fails, entities for that device become unavailable.
They recover after the next successful refresh.

## Known limitations

- The integration requires Internet access and availability of both the
  Viessmann API and the configured Viessmann gateway.
- Available entities vary by device model, installed components, Viessmann API
  product/package, and OAuth permissions.
- The integration polls; it does not receive real-time push updates. State
  changes may take up to the next successful 90-second refresh to appear if
  they were not initiated through Home Assistant.
- Devices added to or removed from the Viessmann account after setup currently
  require reloading the integration to be reflected in Home Assistant.
- The integration does not provide local-network discovery, firmware updates,
  schedules, or a local fallback when the Viessmann cloud is unavailable.
- The polling interval does not by itself guarantee API rate-limit compliance:
  total API use also depends on device count and command frequency.

## Troubleshooting

### Reauthentication or token refresh fails

If Home Assistant asks for reauthentication, complete the prompt for the
existing integration. Viessmann refresh tokens can expire or be revoked. Do
not reuse an old OAuth callback URL: authorization codes are short-lived and
can be used only once.

### The OAuth flow reports an invalid redirect URI

Confirm that the application in the Viessmann Developer Portal uses exactly:

```
https://my.home-assistant.io/redirect/oauth
```

Also ensure that your Home Assistant URL is configured in My Home Assistant.

### No entities, or expected entities are missing

Check that the device is visible and online in the Viessmann account. Entity
availability depends on the model and the API features granted to the account.
Some auto-discovered entities may be disabled by default; inspect the device's
entity list and enable the needed entity there.

### Entities are unavailable or do not update

Check Internet connectivity, the gateway's online state, and the Viessmann
service status. A transient failure leaves the affected device unavailable
until a subsequent successful refresh. Wait at least one polling interval
(90 seconds) before concluding that recovery failed.

### Enable debug logging

Add the following to `configuration.yaml`, then restart Home Assistant:

```yaml
logger:
  default: warning
  logs:
    custom_components.vi_climate_devices: debug
    vi_api_client: debug
```

Remove debug logging after collecting the relevant information. Logs can
contain operational details about your installation.

When reporting an issue, include the Home Assistant version, integration
version, device model, affected entity or feature, and relevant redacted logs.
Never include OAuth tokens, client credentials, or personal account data.

## Removing the integration

To remove an integration entry:

1. Go to **Settings** > **Devices & services**.
2. Select **Viessmann Climate Devices**.
3. Select the three-dot menu on the integration entry, then **Delete**.
4. Confirm the deletion.

This removes the integration entry and its entities from Home Assistant. To
revoke access completely, also remove the OAuth application from the Viessmann
Developer Portal. To uninstall the custom integration, remove it in HACS (or
delete `custom_components/vi_climate_devices` after removing all entries) and
restart Home Assistant.

## Development

### Development setup

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install '.[dev]'
pre-commit install --install-hooks
```

### Quality checks

```bash
python scripts/quality_check.py

# Run the same gate manually through pre-commit.
pre-commit run --all-files
```

For Python and test standards, read [CONTRIBUTING.md](CONTRIBUTING.md).
Automated coding agents must also follow [AGENTS.md](AGENTS.md).

## License

MIT License — see [LICENSE](LICENSE).

## Acknowledgments

- Built on [vi_api_client](https://github.com/ignazhabibi/vi_api_client)
