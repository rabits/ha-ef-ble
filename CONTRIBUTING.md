# Contributing to ha-ef-ble

Thanks for considering a contribution! This integration is maintained by volunteers, and
improvements of any size - bug reports, documentation fixes, new device support, new
features - are very welcome.

This document explains how to get set up, how to propose changes, and what to expect
from the review process. If anything is unclear, open a
[Discussion](https://github.com/rabits/ha-ef-ble/discussions) or draft issue and we'll
help out.

## Table of contents

- [Code of conduct](#code-of-conduct)
- [Ways to contribute](#ways-to-contribute)
  - [Reporting bugs](#reporting-bugs)
  - [Reporting a missing or incorrect sensor](#reporting-a-missing-or-incorrect-sensor)
  - [Requesting support for a new device](#requesting-support-for-a-new-device)
  - [Suggesting enhancements](#suggesting-enhancements)
  - [Asking questions](#asking-questions)
- [Your first code contribution](#your-first-code-contribution)
- [Development setup](#development-setup)
  - [Prerequisites](#prerequisites)
  - [Clone and install](#clone-and-install)
  - [Running tests](#running-tests)
  - [Code style and linting](#code-style-and-linting)
  - [Running the integration in Home Assistant](#running-the-integration-in-home-assistant)
- [Making a pull request](#making-a-pull-request)
  - [Branching and commits](#branching-and-commits)
  - [AI-assisted contributions](#ai-assisted-contributions)
- [Style guide](#style-guide)
- [Project layout](#project-layout)

## Code of conduct

Be kind, patient, and constructive. Assume good intent, give concrete feedback, and
remember that most contributors are hobbyists working in their spare time. Harassment,
personal attacks, or hostility toward other contributors are not tolerated.

## Ways to contribute

All three of the flows below open through dedicated issue forms in
[`.github/ISSUE_TEMPLATE/`](.github/ISSUE_TEMPLATE/) - blank issues are disabled, so
pick the template that matches what you're reporting.

### Reporting bugs

For crashes, disconnects, errors in the log, or anything broken that isn't specifically
a sensor value problem, use the
[Bug report](https://github.com/rabits/ha-ef-ble/issues/new?template=bug_report.yaml)
template. Before opening it:

1. make sure you're on the latest release and that the bug still reproduces
2. search existing [issues](https://github.com/rabits/ha-ef-ble/issues) to avoid
   duplicates - add a 👍 to an existing report rather than opening a new one
3. fill in every field the template asks for - integration and Home Assistant versions,
   device model, Bluetooth connection type, any changed settings, and relevant log
   output. Bug reports without this information are much harder to act on
4. if the bug is sensor-value-shaped rather than crash-shaped, use the sensor template
   below instead

### Reporting a missing or incorrect sensor

If a sensor is missing, shows the wrong value, or a value the device exposes isn't
surfaced in Home Assistant, use the
[New / missing / incorrect sensor](https://github.com/rabits/ha-ef-ble/issues/new?template=sensor_request.yaml)
template. Almost all sensor reports need a diagnostics dump to identify the right
protobuf field - see
[Providing Diagnostics Data](https://github.com/rabits/ha-ef-ble/wiki/Providing-Diagnostics-Data-for-Debugging-or-Implementing-New-Sensors)
for how to capture one. Diagnostics are safe to share publicly - all potentially
sensitive data is AES encrypted. Capture the dump while the value you care about is
**non-zero** (sun on the panels, load on the output, charger plugged in) so the
relevant field is actually populated.

### Requesting support for a new device

If you own an EcoFlow device that isn't listed in the README's
[Supported Devices](README.md#supported-devices) section, use the
[New device support](https://github.com/rabits/ha-ef-ble/issues/new?template=device_request.yaml)
template. It mirrors the flow described on the
[Requesting Support for New Devices](https://github.com/rabits/ha-ef-ble/wiki/Requesting-Support-for-New-Devices)
wiki page:

1. add the unsupported device through the integration; it will run in a diagnostic
   collection mode
2. exercise different ports / features so the captured traffic covers the functionality
   you care about
3. attach the diagnostics file to the issue along with the device model, firmware, and
   SN prefix the template asks for

Some devices can't provide useful diagnostics over BLE. If your device won't connect for
collection, open the issue anyway with the model and firmware version so we know
there's demand.

### Suggesting enhancements

Before opening a pull request for a non-trivial change, please **open an issue first**
describing the motivation and proposed approach. This avoids wasted effort on changes
that don't fit the integration's scope or conflict with other ongoing work.

Small, focused suggestions (wording fixes, obvious bug fixes, sensor defaults) don't
need a pre-discussion issue - just send the PR.

### Asking questions

For usage questions, setup troubleshooting, or general discussion, use
[GitHub Discussions](https://github.com/rabits/ha-ef-ble/discussions). The issue
templates link to Discussions directly, and blank issues are disabled on the tracker -
it's only for actionable bug reports and feature requests.

## Your first code contribution

Good starting points:

- issues labelled
  [`good first issue`](https://github.com/rabits/ha-ef-ble/labels/good%20first%20issue)
  or [`help wanted`](https://github.com/rabits/ha-ef-ble/labels/help%20wanted)
- documentation and translation fixes - typos, clarifications, missing sensor entries in
  the README device tables
- adding tests for existing device modules under `tests/eflib/`

## Development setup

### Prerequisites

- **Python 3.13 or newer.** The project also runs on 3.14.
- **[`uv`](https://github.com/astral-sh/uv)** for dependency management and tooling.
  Install via the [official instructions](https://docs.astral.sh/uv/getting-started/installation/),
  e.g. `curl -LsSf https://astral.sh/uv/install.sh | sh` on Linux/macOS.
- **git**, and ideally a running Home Assistant instance to test the integration
  end-to-end.

### Clone and install

```bash
git clone https://github.com/rabits/ha-ef-ble.git
cd ha-ef-ble
uv sync --all-groups
```

This creates a `.venv/` with the runtime dependencies plus the `dev`, `test`, and `lint`
groups - everything needed for the device-library tests and the code-style hooks.

### Running tests

```bash
uv run pytest tests/eflib
```

Use `uv run pytest -k <name>` to run a single test and
`uv run pytest --cov=custom_components.ef_ble` if you want coverage locally. Add tests
for new device modules - `tests/eflib/test_powerstream.py` and
`tests/eflib/test_river3.py` are reasonable templates.

### Code style and linting

Style and lint rules are enforced with [`prek`](https://github.com/j178/prek) (a fast
Rust reimplementation of pre-commit) running the hooks defined in
[`.pre-commit-config.yaml`](.pre-commit-config.yaml). The same hooks run in CI, so if
`prek` is happy locally, CI will be too.

The simplest way to run `prek` is through `uvx`, which fetches and runs it in an
ephemeral environment - no separate install step needed:

```bash
uvx prek install              # enable the pre-commit git hook (one-time)
uvx prek run                  # check files staged for the next commit
uvx prek run --all-files      # check the whole repo (matches CI)
```

If you run these often and want to skip the per-invocation resolve, install `prek` as a
persistent tool once with `uv tool install prek` and drop the `uvx` prefix.

The hooks include [`ruff`](https://docs.astral.sh/ruff/) for linting and formatting
(configured under `[tool.ruff]` in `pyproject.toml`),
[`rumdl`](https://github.com/rvben/rumdl) for Markdown, and a handful of generic hygiene
checks (trailing whitespace, line endings, YAML/TOML parsing, accidentally-committed
private keys).

### Running the integration in Home Assistant

The simplest loop for manual testing is to symlink the component into a local Home
Assistant config directory:

```bash
ln -s "$(pwd)/custom_components/ef_ble" /path/to/ha-config/custom_components/ef_ble
```

Restart Home Assistant after changes to Python code; translation and manifest changes
may also require a restart rather than a hot-reload.

## Making a pull request

### Branching and commits

- Fork the repo and create a feature branch off `main`:
  `git checkout -b fix-device-sensor`.
- Keep each PR focused on a single concern. If your branch fixes a bug *and* refactors
  something nearby, prefer two PRs (or two commits that can be reviewed independently).
- Write commit messages in the imperative mood ("Fix PV2 mapping on STREAM Ultra")

### AI-assisted contributions

Using LLMs / AI coding assistants is fine - most of us do nowadays. What matters is that
**you own the code you submit**: you've read every line, understand why it's there,
tested that it works, and can respond to review feedback without going back to the model
for every answer.

**Adding support for a new device is the one place where fully vibe-coded PRs are
actively welcome.** It's genuinely easier to start from a rough LLM draft plus a
diagnostics dump than from a blank module - even an imperfect draft gives us a concrete
starting point, your field mappings, and proof that the device is reachable. Open the
PR, link the diagnostics file, describe what you tested on the hardware, and be honest
about which parts you didn't verify.

That said: **we will not merge a vibe-coded new-device PR as-is.** Expect us to use it
as a reference and rewrite the parts that need to match project patterns - renaming
fields to line up with existing device modules, consolidating duplicated logic into
shared transforms, dropping invented APIs, adjusting controls to the conventions in
`eflib/entity/`, adding tests, and so on. The final commit that lands usually won't
look much like your original branch. If that's not how you want your contribution
handled, open an issue with the diagnostics dump instead and we'll pick it up from
there.

For everything else (bug fixes, refactors, changes to existing devices, protocol /
packet handling), the bar is higher: unread LLM output, code the author can't explain,
or changes that ignore existing patterns won't be reviewed in place. Re-read your diff
top-to-bottom before opening the PR.

## Style guide

Most style is enforced by `ruff`, so the full rule set lives in `pyproject.toml`. A few
non-obvious conventions:

- **Python≥3.13** features are fair game: pattern matching, PEP 695 generics, `type`
  statements, f-strings, the walrus operator, dataclasses.
- **Type hints everywhere.** Public functions, class attributes, and fields declared via
  `pb_field` / `raw_field` should have meaningful types. The shared transforms in
  `custom_components/ef_ble/eflib/props/transforms.py` preserve `None` intentionally -
  prefer them over inline `lambda` helpers.
- **American English** for identifiers, comments, and user-facing strings.
- **Logging:** use lazy `%s` formatting (`_LOGGER.debug("got %s", value)`), no trailing
  periods, no sensitive data, and don't repeat the integration name - it's added
  automatically.
- **Async-safe** everywhere: no blocking I/O on the event loop, no `time.sleep`, don't
  reuse `BleakClient` instances across connects. Use `asyncio.gather` instead of
  sequential `await`s where possible.
- **Exceptions:** raise the most specific type that fits (`ConfigEntryAuthFailed`,
  `ConfigEntryNotReady`, `HomeAssistantError`, `ServiceValidationError`,
  `UpdateFailed`).Keep `try` blocks minimal - only wrap the call that can raise, not the
  data processing that follows. Bare `except Exception:` is reserved for config flows
  and background tasks.
- **Docstrings:** [NumPy style](https://numpydoc.readthedocs.io/en/latest/format.html)
  without types in the docstring (`numpy-notypes` variant - argument and return types
  belong in the signature, not duplicated in the docstring). Use a one-line docstring
  for short descriptions; when a longer explanation is needed, start the summary on the
  second line (matches Ruff's `D213`) and use `Parameters` / `Returns` sections for
  non-obvious arguments and return values. **The summary line does not end with a
  period.** Document *why*, not what - skip docstrings that only restate the function
  name.

  ```python
  class Device(DeviceBase, ProtobufProps):
      """STREAM AC"""

  def pb_field(
      attr: Any,
      transform: Callable[[Any], Any] | None = None,
  ) -> "ProtobufField[Any]":
      """
      Create field that allows value assignment from protocol buffer messages

      Parameters
      ----------
      attr
          Protobuf field attribute of instance returned from `proto_attr_mapper`
      transform, optional
          Function that is applied to raw protobuf value
      """
  ```

## Project layout

```text
custom_components/ef_ble/
├── __init__.py            # HA integration entry point
├── config_flow.py         # Config flow for pairing
├── sensor.py / switch.py  # Entity platforms
├── translations/          # User-facing strings
└── eflib/                 # Home Assistant-independent device library
    ├── devices/           # One module per EcoFlow device family
    ├── pb/                # Generated protobuf bindings (do not edit)
    ├── props/             # Field descriptors, transforms, prop mixins
    ├── entity/            # Control / dynamic entity helpers
    └── ...
tests/
├── eflib/                 # Library-level tests (no Home Assistant)
└── ha/                    # Integration tests using Home Assistant
```

New device support typically means:

1. a new module in `custom_components/ef_ble/eflib/devices/` with a `Device` class and a
   `SN_PREFIX` tuple.
2. field definitions using `pb_field` / `raw_field` and shared transforms from
   `eflib/props/transforms.py`
3. controls defined with the `controls.*` decorators where applicable.
4. tests under `tests/eflib/test_<device>.py`
5. a new `<details>` block in the README listing the exposed sensors and controls

---

Thanks again for contributing. When in doubt, open an issue or draft PR early - it's
much easier to course-correct at the design stage than at review time.
