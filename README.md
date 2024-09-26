# EcoFlow BLE

[![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](https://github.com/hacs/integration)
[![Validation hassfest](https://github.com/rabits/ha-ef-ble/actions/workflows/validation-hassfest.yml/badge.svg)](https://github.com/rabits/ha-ef-ble/actions/workflows/validation-hassfest.yml)
[![Validation HACS](https://github.com/rabits/ha-ef-ble/actions/workflows/validation-hacs.yml/badge.svg)](https://github.com/rabits/ha-ef-ble/actions/workflows/validation-hacs.yml)

Unofficial EcoFlow BLE devices Home Assistant integration will allow you to communicate with a
number of EcoFlow devices through bluetooth and monitor their status / control parameters.

Recognized devices:
* Smart Home Panel 2 (EF-HD3####, FW Version: 4.0.0.122, WiFi Version: 2.0.1.20)
* TODO: Delta Pro Ultra (EF-YJ####, FW Version: 5.0.0.25, WiFi Version: 2.0.2.4)

## WARNING: Support & Warranty

Sorry, limited support and no warranty - you on your own and I take no responsibility for any of
your actions. We all grown-ups here and know that we deal with quite dangerous voltages and storage
devices that could injure or cause death. So make sure you know what you doing for each and every
step - otherwise you can't use the provided information in this repository or integration.

In case you see some issues with your device after using this integration - ecoflow support could
be unable to help you. Author of the integration is not connected to EcoFlow anyhow and they can't
support anything you will find here.

## Usage

Install the integration as custom_component and it will automatically find the supported devices.
On configuration you will need to find your EcoFlow UserID and put it in the device configuration.

Two ways to find your UserID - it's sent to device when you bind it to your EcoFlow account and
becomes integral part of the authentication mechanism, but usually user don't see it. It's only
visible through:
* If you have root on your device with ef app: from `mmkv` db. Look at the file
  `/data/data/com.ecoflow/files/mmkv/mmkv.default` - binary, but you can find `user_id` field.
* By log in to ecoflow site: go to https://us.ecoflow.com/ , open dev console and switch to
  "Network" tab. Then login and find POST to https://api-a.ecoflow.com/auth/login - the response
  contains json, which have data.user.userId field string.

## Reverse

Information about how that was reversed you can find here: https://github.com/rabits/ef-ble-reverse

## Legal

This repository is not for sale.

The work was done in order to localize devices and make them available / controllable in disaster
situations (unavailability of internet or cut-off the ecoflow servers). The official application
allows to connect via bluetooth, but to do that you have to login to the server. No server is here
and you screwed.

The requests to ecoflow usually ends up in support department and generally ignored, so there is no
way to get support from them. That gave me right to take it in my own hands and use my knowledge &
time to make my own way. There is no intention to harm any people anyhow - just to make sure you
will be safe in emergency situation, which is critical for such a product.
