<div align="center">

# 🔋 EcoFlow BLE

**Unofficial Bluetooth LE Integration for Home Assistant**

[![HACS](https://img.shields.io/badge/HACS-Default-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)
[![hassfest](https://img.shields.io/github/actions/workflow/status/rabits/ha-ef-ble/validate-hassfest.yaml?style=for-the-badge&label=hassfest)](https://github.com/rabits/ha-ef-ble/actions/workflows/validate-hassfest.yaml)
[![HACS Validation](https://img.shields.io/github/actions/workflow/status/rabits/ha-ef-ble/validate-hacs.yaml?style=for-the-badge&label=HACS)](https://github.com/rabits/ha-ef-ble/actions/workflows/validate-hacs.yaml)

---

**Monitor and control your EcoFlow devices locally via Bluetooth**

No internet connection required • Real-time status updates • Full local control

[Supported Devices](#supported-devices) • [Installation](#installation) •
[Development](#development)

</div>

---

## Overview

This integration enables local communication with EcoFlow power stations and accessories
through **Bluetooth LE**, allowing you to:

- **Monitor** battery levels, power flow, and device status
- **Control** outputs, charging parameters, and device settings
- **Integrate** seamlessly with Home Assistant automations
- **Operate** independently without cloud connectivity

---

## Supported Devices

Click on any device below to see available sensors, switches, and controls:

<br>
<details>
<summary><b>Smart Home Panel 2</b></summary>

<br>

| *Sensors*                                  |
|--------------------------------------------|
| Battery Level                              |
| Input Power                                |
| Output Power                               |
| Grid Power                                 |
| Power In Use                               |
| Circuit Power (Each Circuit)               |
| Circuit Current (Each Circuit)             |
| Channel Power (Each Channel)               |
| Channel Battery Level (Each Channel)       |
| Channel Battery Temperature (Each Channel) |
| Channel Connected (Each Channel)           |
| Channel Control Status (Each Channel)      |
| Channel Enabled (Each Channel)             |
| Channel Output Power (Each Channel)        |
| Channel PV HV Input Power (Each Channel)   |
| Channel PV LV Input Power (Each Channel)   |

</details>
<details>
<summary><b>Delta Pro Ultra</b></summary>

<br>

| *Sensors*                            |
|--------------------------------------|
| Battery Level                        |
| Individual Battery Levels (disabled) |
| Input Power                          |
| Output Power                         |
| Low Voltage Solar Power              |
| High Voltage Solar Power             |
| AC L1 (1) Output Power               |
| AC L1 (2) Output Power               |
| AC L2 (1) Output Power               |
| AC L2 (2) Output Power               |
| AC TT-30R Output Power               |
| AC L14-30P Output Power              |
| AC I/O Output Power                  |
</details>
<details>
<summary><b>River 3</b> <i>(Plus, UPS, Plus Wireless)</i></summary>

<br>

| *Sensors*                           | *Switches*     | *Sliders*            | *Selects*        |
|-------------------------------------|----------------|----------------------|------------------|
| AC Input Energy                     | AC Port        | Backup Reserve Level | Led Mode⁺        |
| AC Input Power                      | DC Port        | Max Charge Limit     | DC Charging Type |
| AC Output Energy                    | Backup Reserve | Min Discharge Limit  |                  |
| AC Output Power                     |                | AC Charging Speed    |                  |
| Main Battery Level ⁺                |                | DC Charging Max Amps |                  |
| Battery Level                       |                |                      |                  |
| DC 12V Port Output Energy           |                |                      |                  |
| DC 12V Port Output Power            |                |                      |                  |
| DC Input Energy                     |                |                      |                  |
| DC Input Power                      |                |                      |                  |
| Input Energy Total                  |                |                      |                  |
| Input Power Total                   |                |                      |                  |
| Output Energy Total                 |                |                      |                  |
| Output Power Total                  |                |                      |                  |
| USB A Output Energy                 |                |                      |                  |
| USB A Output Power                  |                |                      |                  |
| USB C Output Energy                 |                |                      |                  |
| USB C Output Power                  |                |                      |                  |
| Battery Input Power (disabled)      |                |                      |                  |
| Battery Output Power (disabled)     |                |                      |                  |
| Cell Temperature (disabled)         |                |                      |                  |
| Charge Time Remaining (disabled)    |                |                      |                  |
| Discharge Time Remaining (disabled) |                |                      |                  |

<sup>⁺ Only available on Plus variant</sup>

> **📝 Note:** **AC Input Energy sensor** is not working as intended - this is a firmware
> bug. If you need this sensor, create an integral helper from AC Input Power instead. See
> [issue #73](https://github.com/rabits/ha-ef-ble/issues/73) for details.

> **⚠️ Warning:** This integration allows setting Backup Reserve Limit to Min Discharge
> Limit, which may cause AC ports to turn off when hitting this limit. The official
> application allows the same behavior, but this is most likely a bug. See
> [issue #78](https://github.com/rabits/ha-ef-ble/issues/78) for more info.

</details>

<details>
<summary><b>Delta 3</b> <i>(Classic, Plus, Max, Max Plus, Ultra, Air)</i></summary>

<br>

| *Sensors*                           | *Switches*                      | *Sliders*                  |
|-------------------------------------|---------------------------------|----------------------------|
| Main Battery Level                  | AC Ports                        | Backup Reserve Level ²     |
| Battery Level                       | AC Ports (2) ³                  | Max Charge Limit           |
| AC Input Power                      | DC Ports ²                      | Min Discharge Limit        |
| AC Output Power                     | Backup Reserve ²                | AC Charging Speed          |
| AC (1) Power ³                      | USB Ports ¹²                    | DC Charging Max Amps       |
| AC (2) Power ³                      | Disable Grid Bypass ²(disabled) | DC (2) Charging Max Amps ⁺ |
| DC 12V Port Output Power ²          |                                 |                            |
| DC Port Input Power                 |                                 |                            |
| DC Port Input State                 |                                 |                            |
| DC Port (2) Input Power ⁺           |                                 |                            |
| DC Port (2) Input State ⁺           |                                 |                            |
| Solar Power                         |                                 |                            |
| Solar Power (2) ⁺                   |                                 |                            |
| Input Power Total                   |                                 |                            |
| Output Power Total                  |                                 |                            |
| USB A Output Power                  |                                 |                            |
| USB A (2) Output Power              |                                 |                            |
| USB C Output Power                  |                                 |                            |
| USB C (2) Output Power              |                                 |                            |
| USB C (3) Output Power ³            |                                 |                            |
| AC Plugged In                       |                                 |                            |
| Battery Input Power (disabled)      |                                 |                            |
| Battery Output Power (disabled)     |                                 |                            |
| Cell Temperature (disabled)         |                                 |                            |
| Charge Time Remaining (disabled)    |                                 |                            |
| Discharge Time Remaining (disabled) |                                 |                            |

<sup>⁺ Only available on Plus variant</sup><br>
<sup>¹ Not available on Classic</sup><br>
<sup>² Not available on Air</sup><br>
<sup>³ Only available on Max Plus</sup>

> **📝 Note:** Delta 3 models do not expose energy sensors. To use with the Energy
> dashboard, you must create them yourself. See the
> [Home Assistant FAQ](https://www.home-assistant.io/docs/energy/faq/#creating-an-energy-sensor-out-of-a-power-sensor)
> for instructions.

</details>

<details>
<summary><b>Delta Pro 3</b></summary>

<br>

| *Sensors*                           | *Switches*     | *Sliders*            |
|-------------------------------------|----------------|----------------------|
| Main Battery Level                  | AC Ports       | Backup Reserve Level |
| Battery Level                       | DC Ports       | Max Charge Limit     |
| AC Input Power                      | Backup Reserve | Min Discharge Limit  |
| AC LV Output Power                  |                | AC Charging Speed    |
| AC HV Output Power                  |                |                      |
| DC 12V Output Power                 |                |                      |
| DC LV Input Power                   |                |                      |
| DC LV Input State                   |                |                      |
| DC HV Input Power                   |                |                      |
| DC HV Input State                   |                |                      |
| Solar LV Power                      |                |                      |
| Solar HV Power                      |                |                      |
| Input Power Total                   |                |                      |
| Output Power Total                  |                |                      |
| USB A Output Power                  |                |                      |
| USB A (2) Output Power              |                |                      |
| USB C Output Power                  |                |                      |
| USB C (2) Output Power              |                |                      |
| AC Plugged In                       |                |                      |
| Cell Temperature (disabled)         |                |                      |
| Charge Time Remaining (disabled)    |                |                      |
| Discharge Time Remaining (disabled) |                |                      |

> **📝 Note:** Delta Pro 3 does not expose energy sensors. To use with the Energy
> dashboard, you must create them yourself. See the
> [Home Assistant FAQ](https://www.home-assistant.io/docs/energy/faq/#creating-an-energy-sensor-out-of-a-power-sensor)
> for instructions.

</details>

<details>
<summary><b>Smart Generator</b> <i>(3000, 4000)</i></summary>

<br>

| *Sensors*              | *Switches*           | *Sliders*        | *Selects*        |
|------------------------|----------------------|------------------|------------------|
| Output Power           | Engine               | Gas Weight       | Performance Mode |
| AC Output Power        | Self Start           | DC Output Power⁴ | Gas Unit         |
| Engine State           | LPG Level Monitoring |                  |                  |
| Fuel Type              | AC Ports             |                  |                  |
| Gas Consumption        |                      |                  |                  |
| Abnormal State         |                      |                  |                  |
| Internal Battery Power |                      |                  |                  |
| Internal Battery State |                      |                  |                  |
| XT150 Battery Level ⁴  |                      |                  |                  |
| XT150 Charge Type ⁴    |                      |                  |                  |

<sup>⁴ Only available on 4000 variant</sup>

</details>

<details>
<summary><b>Alternator Charger</b></summary>

<br>

| *Sensors*           | *Switches*                 | *Sliders*                | *Selects*    |
|---------------------|----------------------------|--------------------------|--------------|
| Battery Level       | Charger                    | Start Voltage            | Charger Mode |
| Battery Temperature | Emergency Reverse Charging | Reverse Charging Current |              |
| DC Power            |                            | Charging Current         |              |
| Battery Voltage     |                            | Power Limit              |              |

</details>

<details>
<summary><b>STREAM</b> <i>(AC, AC Pro, Max, Pro, Ultra, Ultra X)</i></summary>

<br>

| *Sensors*                           | *Switches*  | *Sliders*               | *Selects*       |
|-------------------------------------|-------------|-------------------------|-----------------|
| Battery Level                       | Feed Grid   | Feed Grid Power Limit   | Energy Strategy |
| Main Battery Level                  | AC (1) ᴬᴹᴾᵁ | Backup Reserve Level    |                 |
| Grid Power                          | AC (2) ᴬᴾᵁ  | Charge Limit            |                 |
| Grid Voltage                        |             | Discharge Limit         |                 |
| Grid Frequency                      |             | Base Load Power ¹       |                 |
| Load from Battery                   |             | Grid Input Power Limit  |                 |
| Load from Grid                      |             | Charging Power Limit ²ꜝ |                 |
| Load from PV ᴹᴾᵁ                    |             | Charging Target SOC ²ꜝ  |                 |
| AC (1) Power ᴬᴹᴾᵁ                   |             |                         |                 |
| AC (2) Power ᴬᴾᵁ                    |             |                         |                 |
| PV (1) Poweri ᴹᴾᵁ                   |             |                         |                 |
| PV (2) Power ᴹᴾᵁ                    |             |                         |                 |
| PV (3) Power ᴾᵁ                     |             |                         |                 |
| PV (4) Power ᵁ                      |             |                         |                 |
| PV Power Total ᴹᴾᵁ                  |             |                         |                 |
| Cell Temperature (disabled)         |             |                         |                 |
| Charge Time Remaining (disabled)    |             |                         |                 |
| Discharge Time Remaining (disabled) |             |                         |                 |

<sup>ᴬ Only available on AC Pro variant</sup><br>
<sup>ᴹ Only available on Max variant</sup><br>
<sup>ᴾ Only available on Pro variant</sup><br>
<sup>ᵁ Only available on Ultra and Ultra X variants</sup><br>
<sup>¹ Not available when there's no base load timeframe or more than 1 timeframe configured</sup><br>
<sup>² Only works if timer task with charging power limit is configured and only works for the
first charging task</sup>

> **❗ Important:** When changing limits or target SOC using automations, wait at least 1
> second between each set, otherwise the last one will override all previous ones. This is
> a current limitation that will be addressed in a future update.

</details>

<details>
<summary><b>STREAM Microinverter</b></summary>

<br>

| *Sensors*      | *Sliders*            |
|----------------|----------------------|
| Grid Power     | Maximum Output Power |
| Grid Voltage   |                      |
| Grid Current   |                      |
| Grid Frequency |                      |
| PV (1) Power   |                      |
| PV (1) Current |                      |
| PV (1) Voltage |                      |
| PV (2) Power   |                      |
| PV (2) Current |                      |
| PV (2) Voltage |                      |

</details>

<details>
<summary><b>Wave 3</b></summary>

<br>

| *Sensors*                        | *Sliders*       | *Switches* |
|----------------------------------|-----------------|------------|
| Battery Level                    | Charge Limit    | Power      |
| Ambient Temperature              | Discharge Limit |            |
| Ambient Humidity                 |                 |            |
| Operating Mode                   |                 |            |
| Condensate Water Level           |                 |            |
| Cell Temperature (disabled)      |                 |            |
| Fan Level                        |                 |            |
| Drainage Mode                    |                 |            |
| Input Power                      |                 |            |
| Output Power                     |                 |            |
| Indoor Supply Air Temperature    |                 |            |
| Indoor Return Air Temperature    |                 |            |
| Outdoor Ambient Temperature      |                 |            |
| Condenser Temperature            |                 |            |
| Evaporator Temperature           |                 |            |
| Compressor Discharge Temperature |                 |            |
| Sleep State                      |                 |            |

</details>

<details>
<summary><b>Smart Meter</b></summary>

<br>

| *Sensors*             |
|-----------------------|
| Grid Power            |
| Grid Energy           |
| L1 Power (disabled)   |
| L1 Current (disabled) |
| L1 Voltage (disabled) |
| L1 Energy (disabled)  |
| L2 Power (disabled)   |
| L2 Current (disabled) |
| L2 Voltage (disabled) |
| L2 Energy (disabled)  |
| L3 Power (disabled)   |
| L3 Current (disabled) |
| L3 Voltage (disabled) |
| L3 Energy (disabled)  |

</details>

<details>
<summary><b>Delta 2</b> <i>(Max, Delta 3 1500)</i></summary>

<br>

| *Sensors*                                 | *Switches*  | *Sliders*           |
|-------------------------------------------|-------------|---------------------|
| Battery Level                             | AC Ports    | Max Charge Limit    |
| Main Battery Level                        | DC 12V Port | Min Discharge Limit |
| Addon Battery Level (disabled)            | USB Ports   | Energy Backup       |
| Input Power                               |             | AC Charging Speed   |
| Output Power                              |             |                     |
| AC Input Power                            |             |                     |
| AC Input Voltage (disabled)               |             |                     |
| AC Input Current (disabled)               |             |                     |
| AC Output Power                           |             |                     |
| DC Output Power                           |             |                     |
| DC 12V Output Voltage (disabled)          |             |                     |
| DC 12V Output Current (disabled)          |             |                     |
| USB A (1) Output Power                    |             |                     |
| USB A (2) Output Power                    |             |                     |
| USB A QC (1) Output Power                 |             |                     |
| USB A QC (2) Output Power                 |             |                     |
| USB C (1) Output Power                    |             |                     |
| USB C (2) Output Power                    |             |                     |
| Cell Temperature (disabled)               |             |                     |
| Addon Battery Cell Temperature (disabled) |             |                     |
| Charge Time Remaining (disabled)          |             |                     |
| Discharge Time Remaining (disabled)       |             |                     |

</details>

<details>
<summary><b>River 2</b> <i>(Pro, Max)</i></summary>

<br>

| *Sensors*                           | *Switches*     | *Sliders*            | *Selects* |
|-------------------------------------|----------------|----------------------|-----------|
| Battery Level                       | AC Ports       | Max Charge Limit     | DC Mode   |
| Input Power                         | DC 12V Port    | Min Discharge Limit  |           |
| Output Power                        | USB Ports      | AC Charging Speed    |           |
| AC Input Power                      | Backup Reserve | DC Charging Max Amps |           |
| AC Output Power                     |                | Backup Reserve Level |           |
| DC 12V Output Power                 |                |                      |           |
| DC Output Power                     |                |                      |           |
| USB A Output Power                  |                |                      |           |
| USB C Output Power                  |                |                      |           |
| Solar Input Power                   |                |                      |           |
| Cell Temperature (disabled)         |                |                      |           |
| Charge Time Remaining (disabled)    |                |                      |           |
| Discharge Time Remaining (disabled) |                |                      |           |

</details>

<details>
<summary><b>Wave 2</b></summary>

<br>

| *Sensors*          | *Switches*      | *Sliders*   | *Selects*  |
|--------------------|-----------------|-------------|------------|
| Battery Level      | Automatic Drain | Temperature | Power Mode |
| Battery Power      | Ambient Light   |             | Main Mode  |
| MPPT Power         |                 |             | Sub Mode   |
| PSDR Power         |                 |             | Fan Speed  |
| Outlet Temperature |                 |             | Drain Mode |
| Water Level        |                 |             |            |

</details>

<br>

> [!NOTE]
> This integration focuses on implementing the **most useful sensors and controls** rather than
> achieving 100% completeness. While all sensors and controls available in the EcoFlow app can
> technically be implemented, we prioritize commonly used features. If you're missing a sensor
> or control that's important for your use case, please
> [create an issue](https://github.com/rabits/ha-ef-ble/issues/new) to request it.

> [!IMPORTANT]
> **Bluetooth LE Limitation**: EcoFlow devices support only **one BLE connection at a
> time**. If you want to manage your device via the EcoFlow mobile app, you must
> temporarily disable this integration in Home Assistant, then re-enable it afterward to
> resume data collection. This is an EcoFlow device limitation.

---

## Support & Warranty

> [!CAUTION]
> **Limited Support • No Warranty • Use at Your Own Risk**
>
> - This is an **unofficial integration** with no warranty of any kind
> - The author takes **no responsibility** for your actions or device behavior
> - EcoFlow products involve **dangerous voltages** and energy storage that can cause
>   **injury or death**
> - **EcoFlow support may not help** if you experience issues after using this integration
> - The author is **not affiliated with EcoFlow** in any way
>
> **Proceed only if you fully understand the risks and know what you are doing.**

> [!WARNING]
> **Firmware Updates May Break This Integration**
>
> This integration relies on reverse-engineered Bluetooth protocols. **Future EcoFlow firmware
> updates may change these protocols and break compatibility.** If everything is working
> correctly, do not update your device firmware unless you're willing to wait for this
> integration to be updated to support the new firmware version.

---

## Installation

### Prerequisites

- Home Assistant with Bluetooth support
- Your **User ID** from the EcoFlow app (can be retrieved via the config flow login form
  during setup)
- [HACS](https://hacs.xyz/) installed (recommended method)

### Method 1: HACS Installation (Recommended)

This integration is available in the default HACS repository.

**Quick Install:** Click the badge below to open this repository directly in HACS:

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=rabits&repository=ha-ef-ble&category=integration)

**Manual steps:**

1. Open **HACS** in your Home Assistant instance
2. Go to **Integrations**
3. Click the **⋮** menu (three dots) in the top right
4. Select **Custom repositories**
5. Add this repository URL: `https://github.com/rabits/ha-ef-ble`
6. Select category: **Integration**
7. Click **Add**
8. Search for **"EcoFlow BLE"** in HACS
9. Click **Download**
10. Restart Home Assistant

### Method 2: Manual Installation

1. Download the latest release from
   [GitHub Releases](https://github.com/rabits/ha-ef-ble/releases)
2. Extract the `custom_components/ef_ble` folder
3. Copy it to your Home Assistant `config/custom_components/` directory
4. Restart Home Assistant

### Configuration

After installation, the integration will automatically discover supported EcoFlow devices
via Bluetooth LE.

> [!TIP]
> For detailed configuration help, FAQ, and troubleshooting common issues (like BLE
> disconnections), see the [**Wiki**](https://github.com/rabits/ha-ef-ble/wiki)

---

## Development

### Reverse Engineering

Curious about how this integration was created? Check out the reverse engineering process:
**[ef-ble-reverse](https://github.com/rabits/ef-ble-reverse)**

### Contributing

Contributions are welcome! If you'd like to help improve this integration:

1. **Open an issue first** to discuss your proposed changes
2. Make sure your changes align with the integration's purpose
3. Submit a pull request with clear descriptions

This helps ensure your contributions can be successfully integrated.

### Requesting Support for New Devices

Have an EcoFlow device that isn't listed in [Supported Devices](#supported-devices)?

**You can help add support!** Starting from version
[v0.6.0](https://github.com/rabits/ha-ef-ble/releases/tag/v0.6.0), this integration can
connect to unsupported devices to collect diagnostic data.

**👉 See the
[Requesting Support for New Devices](https://github.com/rabits/ha-ef-ble/wiki/Requesting-Support-for-New-Devices)
wiki page** for step-by-step instructions.

The process is straightforward:

1. Add your unsupported device through this integration
2. Let it collect diagnostic data while using different ports/features
3. Download and share the diagnostics file (note: may contain personal info - see wiki
   for privacy options)

> [!IMPORTANT]
> **Some devices may not be able to provide diagnostics**. This integration works with
> **most 3rd generation and some 2nd generation devices**. If your device cannot connect
> for diagnostics collection, please open an issue with your device model and firmware
> version - adding support is possible but may require additional reverse engineering work.

---

## Legal

> **This repository is not for sale.**

### Purpose & Motivation

This integration was created to enable **local device control** in disaster scenarios:

- **Internet outages** or **EcoFlow server unavailability**
- The official EcoFlow app requires server login, even for Bluetooth connections
- **No server access = no control**, which is unacceptable for critical power equipment

### Background

- Support requests to EcoFlow are typically ignored or handled inadequately
- This motivated independent development using reverse engineering
- **Intent:** Enable safe, reliable local control in emergencies - not to cause harm

### Declaration

This work is provided for **safety and resilience** in critical situations. There is
**no intention to harm** any individual or entity.

---

<div align="center">

**Stay charged. Stay connected. Stay in control.**

*Because when the cloud goes down, your smart home shouldn't follow.*

<br>

<sub>Built by the community, for the community</sub>

</div>
