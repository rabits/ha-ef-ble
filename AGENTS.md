# Instructions for AI coding agents

This file is for AI assistants writing code for this repository. Humans should read
[CONTRIBUTING.md](CONTRIBUTING.md), which covers setup, the PR workflow, the AI-assisted
contribution policy and the style guide. Everything there applies here too; this file
adds the rules that agent-written PRs most often break.

## Before you start

- Read the README notice on supported devices. Do not open a PR adding a new device or
  serial prefix unless a maintainer has asked for it in an issue.
- Keep a PR to one concern. Do not touch files the change does not need: no README
  rewrites, no edits to `.github/workflows/`, no drive-by reformatting, no version
  bumps.
- Find the closest existing device or helper and follow it. Reuse the transforms in
  `eflib/props/transforms.py` and the `@controls` decorators in `eflib/entity/`
  instead of writing local variants.

## Feature design

- **Every mapping needs evidence.** A field offset, scale, unit, sign or command must
  come from a real capture or from what the EcoFlow app does. Never guess one from a
  name or from a sibling device, and say in the PR where each one came from.
- **Declare state, don't parse it by hand.** Map device values with `pb_field` /
  `raw_field` and a shared transform, and let the field machinery do the extraction.
  Hand-written parsing in `data_parse` is for what the field system can't express.
- **Group repeated fields.** For numbered sensors (circuits, ports, PV inputs, cells),
  declare one `pb_field_group` or `field_group` instead of a field per index;
  `shp3.py` shows both.
- **Model a variant as its own device.** When a model differs from a sibling, add a
  subclass with its own `SN_PREFIX` and override the fields that differ, instead of
  branching on the serial number inside the shared class.
- **Commands go through `@controls`.** Platforms discover them automatically, so a new
  control needs only the decorated method, an icon in `icons.json` and a name in
  `translations/en.json`.
- **Controls are a deliberate choice.** Expose only settings the EcoFlow app itself
  offers, keep the app's limits (going past them is an opt-in option, and a maintainer's
  call), and explain the use case in the PR. Something the
  device accepts is not a reason to expose it.
- **Protobuf messages come from a `.proto`.** Never build protobuf bytes by hand; add
  the message to `proto/`, regenerate, and use the generated class.
- **Keep entity identities stable.** Unique IDs are `ef_{serial}_{key}`, so renaming a
  field key orphans the entity and its history. Rename only with a migration.
- **Keep `eflib/` free of Home Assistant.** It is the device library; anything that
  needs Home Assistant belongs in the platform files.
- **Don't assume periodic updates.** Devices report many values only when they change,
  so code must not treat a quiet value as stale or missing.
- **A command must not fail silently.** If a setter can't send (missing state, an
  unknown option), raise or log a warning instead of returning quietly; otherwise the
  entity looks fine and does nothing.
- **Don't invent values.** An unknown value is `None`, so Home Assistant shows it as
  unknown. Map a missing field to `0` only when the device omits it to mean zero, and
  show the evidence in the PR.
- **Follow the conventions of sibling devices.** Consumption is positive, output power
  goes through `out_power`, and a sensor's device class and state class match its unit.
- **Keep logs quiet.** Nothing per packet above `debug`, and `warning` only for
  something the user can act on: every connected device writes to the same log.
- **No new runtime dependencies** in `manifest.json` without a maintainer's agreement.

## High-risk code

`eflib/connection.py`, the auth handshake, `config_flow.py` and anything that writes the
device or entity registry affect every user and every device. In these files:

- Make the smallest change that fixes the problem, and explain in the PR which
  connection states and transitions it changes.
- Do not read or write private attributes of other libraries (`bleak`,
  `bleak_retry_connector`, `habluetooth`, Home Assistant). Home Assistant picks their
  versions, not us, so a private field can vanish in any release and take every
  connection down with it. If the bug is in the dependency, report it there; a local
  workaround needs a maintainer's agreement, a version check and a guard that degrades
  to a no-op.
- Code in a `finally` block or a cleanup path must not be able to raise.
- Keep a reference to every task you create, and make sure its exceptions are retrieved.

## Tests

Tests exist to catch regressions, not to restate the implementation. Smaller and fewer
is better when it covers the same behavior.

- Test through the public surface: feed captured packets through `packet_parse` and
  `data_parse` and assert on the field values. `tests/eflib/test_river3.py` is the
  reference shape.
- Captured packets can carry personal data. Before adding one to a test, fixture or PR
  description, decode it and check for anything that identifies the owner or their
  device: serial numbers, user IDs, MAC addresses, device names, GPS coordinates,
  timezone and region settings, timestamps and keys. Replace any you find with
  placeholders (and fix the checksum), or use a different packet.
- Do not mock or patch the package's own classes or methods (`Connection`,
  `DeviceBase`, private helpers), and do not assert on private attributes. Mock only
  the outside world: the BLE client, the clock, Home Assistant.
- Do not pin details that are free to change: exact packet bytes of a command, `min` /
  `max` of a number entity, call order of internal helpers, log text.
- One behavior per test, named after it
  (`test_status_packet_before_auth_reply_does_not_confirm_auth`). Use
  `pytest.mark.parametrize` instead of copies of the same test, and fixtures instead of
  repeated setup.
- A bug fix gets one test that fails before the fix and passes after it. If the test is
  several times longer than the fix, cut it down to the part that reproduces the bug.
- No tests that depend on process-wide state or timing: file descriptor counts,
  `sleep`-based waits, real D-Bus or Bluetooth.
- CI runs only `tests/eflib`. Tests under `tests/ha/` are not run in CI, so they do not
  count as coverage for a change.

## Home Assistant integration

- Every new config flow step, menu option, error and abort reason needs its strings in
  `translations/en.json`. Renaming a step id means moving its strings in every file in
  `translations/`.
- New entities need a name in `translations/en.json` and an icon in `icons.json` under
  the same key.
- Read options from `entry.data | entry.options`, as setup does, never from
  `entry.data` alone.
- Stored config must keep working. A new key in entry data or options needs a default
  for existing entries; changing the shape means bumping the entry version and adding a
  step to `async_migrate_entry`.
- Use only Home Assistant APIs that exist in the minimum version `hacs.json` declares,
  or guard the newer call.

## Code

- Match the surrounding code: its naming, idioms and comment density.
- Keep functions small and single-purpose. Prefer early returns to nesting; more than
  two levels deep is a sign to extract a helper.
- Prefer a comprehension to an accumulating loop when it stays readable on a line or
  two.
- Use built-in generics and unions (`list[str]`, `int | None`), never `typing.List` or
  `Optional`. Use `Any` only at real dynamic boundaries.
- Make boolean parameters keyword-only, so call sites read `send(wait=True)`.
- Pass dataclasses, not dicts with magic keys, across function boundaries.
- Every `# noqa` carries a short reason on the same line.
- Wrap comments and docstrings close to the 88-column limit, and use single backticks
  for inline code in them.
- Fix the root cause, not the symptom. Don't add retries, sleeps or broad `except`
  blocks to make a race or a flaky test go away, and name the cause in the PR.
- Claim only what you verified. In comments and the PR, state a cause or behavior as
  fact only if you tested or reproduced it, and mark anything else as a guess.
- A comment says why, never what. Do not narrate the next line, do not leave notes for
  the reviewer, and do not put issue or PR numbers in code, comments or tests.
- Do not catch bare `Exception` to log and carry on; catch the specific errors the call
  can raise.
- Never edit the generated `eflib/pb/*_pb2.py` by hand. Change the `.proto` in `proto/`
  and regenerate.

## Before opening the PR

```bash
uv run pytest tests/eflib
uvx prek run --all-files
```

Both must pass. Re-read the whole diff and remove anything the change does not need.

## PR description

Write it for the reviewer, who reads it next to the diff:

- Say what the change does and why, in a short paragraph. For a fix, give the root
  cause.
- Say how it was tested: which tests, and which real hardware (model and firmware).
  Say plainly what you did not verify.
- Add only the details a reviewer needs and can't see in the diff: a decision and its
  alternative, a compatibility concern, a behavior that changes for existing users.
- Disclose AI use: say that the change was written with an AI agent, name the tool and
  model, and say what the human submitting it has reviewed or tested themselves.
- Do not walk through the diff file by file or list every field, function and test.
  Leave out anything that is evident from the code.
- Do not hard-wrap paragraphs or list items. GitHub renders each line break, so keep
  every paragraph and bullet on one line.
