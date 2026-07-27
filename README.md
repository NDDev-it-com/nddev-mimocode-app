# nddev-mimocode-app

NDDev setup-switching manager for current MiMo Code CLI.

This module manages MiMo Code in an explicit, isolated target directory. It
does not read or modify live MiMo Code authentication, cache, data, or state.

## Verified upstream surface

- Command: `mimo`
- Tested release: `v0.1.9`, published `2026-07-24T06:06:13Z`
- Official release source: <https://github.com/XiaomiMiMo/MiMo-Code/releases/tag/v0.1.9>
- Official installer: <https://mimo.xiaomi.com/install>
- Official config/permission surface:
  <https://mimo.xiaomi.com/mimocode/config-files>,
  <https://mimo.xiaomi.com/mimocode/config-overrides>, and
  <https://mimo.xiaomi.com/mimocode/permissions>

The manager uses the documented `MIMOCODE_HOME`, `MIMOCODE_CONFIG`, and XDG
environment variables for target isolation. The managed
configuration uses the current `permission` field; deprecated permission
aliases are not used.

## Setup variants

- `safe`: read/search plus planning, writes and shell denied.
- `balanced`: read/search and common git inspection allowed; edits and general
  shell approval-bound.
- `full-auto`: autonomous within the isolated target while destructive shell
  and publish patterns remain constrained.

All variants enable `nddev-builder` by default through MiMo Code native config,
skills, agents, workflows, and instruction files. Marketplace support is intentionally
`null` because no current official MiMo Code marketplace contract was verified.

## Usage

Use an absolute target path:

```bash
python3 cli-tools/nddev_mimocode.py list --json
python3 cli-tools/nddev_mimocode.py plan --setup balanced --target /absolute/target --json
python3 cli-tools/nddev_mimocode.py install --setup balanced --target /absolute/target --json
python3 cli-tools/nddev_mimocode.py switch --setup safe --target /absolute/target --json
python3 cli-tools/nddev_mimocode.py restore --backup 0 --target /absolute/target --json
python3 cli-tools/nddev_mimocode.py remove --target /absolute/target --json
```

Software management is target-owned and exact-version:

```bash
python3 cli-tools/nddev_mimocode.py software-status --target /absolute/target --json
python3 cli-tools/nddev_mimocode.py install-cli --target /absolute/target --json
python3 cli-tools/nddev_mimocode.py update-cli --target /absolute/target --json
python3 cli-tools/nddev_mimocode.py remove-cli --target /absolute/target --json
```

The staged executable remains size-bounded. Its verified upstream archive
identity and executable metadata are owned by `references/mimocode-baseline.json`;
the managed path, private mode, recorded digests, and protective bounds are
declared by `config/nddev-contract.json` and revalidated by software status.

Launch forwards stdio and the child exit code:

```bash
python3 cli-tools/nddev_mimocode.py launch --target /absolute/target -- --version
```

Launch refuses documented permission-bypass and updater escape arguments
(`--dangerously-skip-permissions`, `--never-ask`, `--trust`, and `upgrade`);
permission policy and software updates stay bound to the managed target.

The launched child receives isolated `HOME`, `USERPROFILE`, `MIMOCODE_HOME`,
`MIMOCODE_CONFIG`, XDG directories, and temporary directory values under the
target. Provider tokens and MiMo Code credential environment variables are
stripped.

## Public validation

```bash
python3 cli-tools/validate_public_contracts.py
```

This validator is dependency-free and side-effect-free. It checks the public
version/build manifest/contract, exact tested upstream release, official
installer SHA-256, asset SHA-256 baseline agreement, setup permission shape,
builder native projection, current identity, and shared CI caller pins.
