# STREAM BLE: Reverse-Engineering-Notizen

## Zweck

Diese Notiz hält die für den MrChurch-Fork relevanten Ergebnisse aus der EcoFlow-App-Analyse und den Home-Assistant-Logs fest. Der Fokus liegt ausschließlich auf STREAM AC und STREAM AC Pro sowie auf stabilen BLE-Verbindungen mit mehreren Geräten.

## Lokale Beweisdateien

Die APKs und Rohlogs bleiben wegen Größe, proprietärer Inhalte und möglicher Zugangsdaten lokal und werden nicht in dieses öffentliche Repository kopiert.

| Datei | SHA-256 | Verwendung |
|---|---|---|
| `ecoflow.apk` | `188BBDB899BE2DA401AC0471BA4D10693612FA1067F2EA0987CC6E1AFCFD4374` | Erste EcoFlow-App-Analyse |
| `app-release.apk` | `78BB0886770453A309C4246BB703BEC33BA456D5A26DFC8254AD52CFFE53EBD2` | Direkt aus der EcoFlow-Quelle bereitgestellte App |
| `latest (15).txt` | lokal vorhanden | Vorheriger HA-/BLE-Testlauf |
| `latest (16).txt` | lokal vorhanden | Drei-Geräte-Testlauf und Reconnect-Diagnose |

Die Hashes erlauben eine spätere erneute Analyse ohne die Binärdateien im Git-Verlauf abzulegen. Bei einer Weitergabe der APKs müssen die Nutzungs- und Urheberrechtsbedingungen von EcoFlow beachtet werden.

## Ergebnis der App-Analyse

In der dekompilierten EcoFlow-App wurde in `ai/b.smali`, Methode `l()`, der relevante Konfigurationsschreibvorgang gefunden:

1. Die App baut `BkSeries.ConfigWrite` auf.
2. Sie setzt `active_display_property_full_upload=true`.
3. Sie sendet die Nachricht über den STREAM-Konfigurationskanal mit Command Set `0xFE` und Command ID `0x11`.

Das erklärt den Zustand „BLE authentifiziert, aber keine aktuellen Werte“. Die Integration übernimmt diesen Vorgang in `stream_ac.py` über die vorhandenen Protobuf- und Packet-Helfer und wiederholt ihn nach Reconnect.

## Im Fork umgesetzte Änderungen

- STREAM-Telemetrie wird nach der Authentifizierung explizit aktiviert.
- Die Aktivierung wird regelmäßig aufgefrischt und nach einer neuen Verbindung erneut gesendet.
- Der Reconnect wird pro Gerät verzögert und mit Jitter verteilt, damit mehrere STREAM-Geräte nicht gleichzeitig den Bluetooth-Adapter belasten.
- Der Zustand `RECONNECTING` blockiert keinen neuen BLE-Verbindungsversuch mehr.
- Die Änderungen sind in diesem PR enthalten.

Relevante Implementierung:

- `custom_components/ef_ble/eflib/devices/stream_ac.py`
- `custom_components/ef_ble/eflib/connection.py`
- `custom_components/ef_ble/manifest.json`

Relevante Tests:

- `tests/eflib/test_stream_ac.py`
- `tests/eflib/test_stream_reconnect.py`

## Beobachtung aus dem Drei-Geräte-Test

Der Loglauf `latest (16).txt` zeigte zunächst: Geräte authentifizieren sich, verlieren später die Verbindung und protokollieren zwar „Reconnecting“, starten aber keinen neuen „Connecting“-Versuch. Ursache war die Reconnect-Zustandsprüfung: `RECONNECTING` wurde als bereits laufender Verbindungsaufbau behandelt. Dieser Fehler ist in `connection.py` behoben.

Nach dem Telemetrie-Fix liefern die STREAM-Geräte wieder Werte; der Premium-Aufbau läuft im aktuellen Test stabil. Drei Geräte sind damit praktisch validiert. Die Implementierung ist für bis zu fünf STREAM-Geräte ausgelegt, wobei die tatsächlich erreichbare Zahl weiterhin von Bluetooth-Adapter, Host und Funkumgebung abhängt.

## Grenzen und nächste Beweisschritte

- Die proprietäre Verschlüsselung und Authentifizierung werden nicht verändert.
- Die App-Analyse ist eine technische Referenz für das beobachtete Protokoll, keine vollständige Dokumentation des EcoFlow-Protokolls.
- Vor einer Aussage über fünf Geräte sollten ein längerer Testlauf, Adapter-Statistiken und die Reconnect-Zeiten aller Geräte dokumentiert werden.
- Rohlogs mit Geräteadressen, Tokens oder verschlüsselten Nutzdaten gehören nicht in das öffentliche Repository.
