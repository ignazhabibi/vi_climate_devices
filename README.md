# Viessmann Climate Devices


[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

> [!WARNING]
> This project is in an early stage of development. It is currently under active development, and changes (including breaking changes) are possible at any time.

A modern Home Assistant integration for Viessmann heating systems using the official Viessmann IoT API.
It is built upon the **[vi_api_client](https://github.com/ignazhabibi/vi_api_client)** library, which was written from scratch specifically for this integration to ensure maximum performance and modern architecture.

**Key Highlights:**
- **Secure Authentication**: Uses the native Home Assistant **Application Credentials** platform for secure OAuth2/PKCE token management.
- **Asynchronous & Fast**: The underlying API client is fully async (`aiohttp`/`asyncio`) for non-blocking I/O.
- **Full Auto-Discovery**: Automatically finds all installations, gateways, and devices linked to your account.


## Features

- **Automatic Device Discovery**: Detects connected Viessmann devices (heat pumps, gas boilers...)
- **Sensors**: Temperature, pressure, energy consumption, SCOP, and diagnostic data
- **Controls**: Target temperatures, operation modes, heating curves
- **Switches**: One-time DHW charge, hygiene function
- **Water Heater**: Full hot water control with temperature and mode settings
- **Multi-Device Support**: Works with multiple Viessmann devices in one installation

## Supported Devices

Tested with:
- Vitocal 250A (real installation) und mock data of other devices

## Installation

### Prerequisites

1. **Viessmann Developer Account**: Register at [developer.viessmann-climatesolutions.com](https://developer.viessmann-climatesolutions.com/start.html)
2. **Create an API Client**:
   - Go to "My Apps" → "Create New App"
   - Name: `Home Assistant` (or any name)
   - Redirect URI: `https://my.home-assistant.io/redirect/oauth`
   - Copy the **Client ID** (you'll need it later)

### HACS Installation (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots menu (⋮) → **Custom repositories**
3. Add repository:
   - **URL**: `https://github.com/ignazhabibi/vi_climate_devices`
   - **Category**: Integration
4. Click **Add**
5. Search for "Viessmann Climate Devices" in HACS and install it
6. **Restart Home Assistant**

### Manual Installation

1. Download the latest release from GitHub
2. Copy the `custom_components/vi_climate_devices` folder to your HA `config/custom_components/` directory
3. Restart Home Assistant

---

### Configuration

1. Go to **Settings** → **Devices & Services**
2. Click **Add Integration**
3. Search for "Viessmann Climate Devices"
4. Follow the setup wizard:
   - You will be asked to enter your **Client ID** (from Viessmann Developer Portal)
   - **Client Secret**: Enter any dummy value (e.g., `123`) since we use PKCE, but the field cannot be empty.
   - Perform the OAuth login to authorize with your Viessmann account

---

## Entities Overview

| Platform | Examples |
|----------|----------|
| `sensor` | Outside temperature, return temperature, SCOP, compressor statistics |
| `binary_sensor` | Compressor active, pumps running, frost protection |
| `number` | Target temperatures, heating curves, hysteresis settings |
| `switch` | One-time DHW charge, hygiene function |
| `select` | DHW operation mode |
| `water_heater` | Hot water temperature and mode control |

All entities are grouped under their respective device and support German and English translations.

---

## Troubleshooting

### Common Issues

**"Invalid Grant" or "Bad Request" during Login**
This is often a timing issue with the OAuth code. 
- **Solution:** Simply try the login process again. It usually works on the second attempt.
- Ensure your browser clock is synchronized.

**"Invalid redirect URI"**
- Ensure `https://my.home-assistant.io/redirect/oauth` is added in Viessmann Developer Portal

**Entities not updating**
- Check if your Viessmann gateway is online
- API rate limit is respected (default: 60s polling interval)

**Missing entities**
- Not all features are available on all device models
- Check HA logs for feature discovery details

### Debug Logging

Add to `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.vi_climate_devices: debug
    vi_api_client: debug
```

---

## Development

### Running Tests

```bash
pip install -r requirements_test.txt
pytest tests/
```

### Code Quality

```bash
ruff check custom_components/vi_climate_devices
```

---

## License

MIT License – see [LICENSE](LICENSE) for details.

## Acknowledgments

- Built on [vi_api_client](https://github.com/ignazhabibi/vi_api_client) library

