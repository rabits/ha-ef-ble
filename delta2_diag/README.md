# delta2_diag: DELTA 2 service data over Bluetooth

A console app that connects to an EcoFlow DELTA 2 over Bluetooth (BLE), authenticates
and then only listens. The only packets it sends the station are the login packets, and
after login it writes nothing. At the end of every run it shows how many packets went
out before login and how many after it. The count after login should be `0`.

It shows the BMS heartbeat (data from the battery management system):

- design, full (actual) and remaining capacity;
- the voltage of each of the 16 cells and the spread between them;
- cycle count, SOH, temperatures, error codes and the other service fields;
- every field with its bytes, plus a hex dump of the whole packet. Bytes the decoder
  did not recognize are highlighted in yellow.

Every received packet is written to `captures/<date>-dump.jsonl`, so it can be decoded
again later.

## Setup (Windows)

1. Install [uv](https://docs.astral.sh/uv/). It downloads the required Python (3.13 or
   newer) and libraries by itself. In PowerShell:

   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

2. Get the fork's code and change into its directory:

   ```powershell
   git clone https://github.com/FreeFox/ha-ef-ble.git
   cd ha-ef-ble
   ```

3. Get your User ID. The station only accepts a client that knows the User ID of the
   account it is bound to. The command asks for your EcoFlow email and password and
   saves only the User ID, to `%APPDATA%\delta2-diag\user_id`. The password is not
   stored anywhere.

   ```powershell
   uv run --group diag python -m delta2_diag login
   ```

   Instead of the file, you can set the `EF_USER_ID` environment variable.

## Running

Before connecting, turn off Bluetooth on your phone or close the EcoFlow app. The
station holds only one Bluetooth connection.

```powershell
# list EcoFlow devices nearby
uv run --group diag python -m delta2_diag scan

# connect, listen for 15 seconds, show the BMS heartbeat
uv run --group diag python -m delta2_diag dump

# decode a saved file again, without the station
uv run --group diag python -m delta2_diag decode captures\20261102-213000-dump.jsonl
```

Useful `dump` options:

- `--listen 60`: listen longer;
- `--sn-suffix 1234`: pick the station by the last characters of its serial number,
  if there are several nearby;
- `-v` or `-vv` before the command name (`python -m delta2_diag -vv dump`): a detailed
  log, if something does not connect.

## What the markers mean

- `?` in the field table: the field sits at a plausible position, but its width or
  meaning is not confirmed yet. A field without `?` has been checked against real
  packets. For example, the highest and lowest cell voltages in the header match the
  cell array.
- `(no data)`: all bits are set (`0xffff…`). This is how the BMS marks an unfilled field.
- `(implausible)`: the value cannot be a percentage. Your model most likely does not
  fill this field.

## Sharing the output or a capture file

Packets can contain battery serial numbers (`bms_sn`, `pack_sn`, the serial numbers of
extra batteries). The station's serial number and Bluetooth address are masked in the
output, and the User ID and password never appear in the output or in capture files.
