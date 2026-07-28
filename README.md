# nddev-mimocode-app

Public NDDev setup manager for MiMo Code.

The manager works only on an explicit absolute target directory. It installs
and launches target-owned MiMo Code software, projects the `nddev-builder`
content setup, and switches between the default full-auto profile and the safe
profile without reading live user configuration or credentials.

Production software install, update, and launch support the canonical NDDev
product hosts `macos-arm64`, `macos-x64`, `ubuntu-glibc-arm64`, and
`ubuntu-glibc-x64`. Linux hosts must report structured `/etc/os-release`
`ID=ubuntu` and glibc; non-Ubuntu Linux, musl Linux, Windows, and unsupported
architectures fail before network, staging, or runtime. No official Ubuntu
version floor is published or claimed. The baseline preserves
all official v0.1.9 upstream artifact names and digests, including musl and
Windows artifacts, as vendor observation separate from the supported subset.

Managed launch and staged probes set manager-owned MiMo Code flags that disable
project config discovery, Claude compatibility loaders, external skill scans,
external plugin origins, autoupdate, model/LSP fetches, provider-env
autodiscovery, and upstream analysis telemetry. Callers and profiles cannot
override those values. Known unmanaged project extension paths such as
`.mimocode/tui`, `.claude`, `.agents/skills`, `.codex/skills`, and
`.opencode/skills` are rejected before launch so only the managed
`nddev-builder` content under `MIMOCODE_CONFIG_DIR` participates. Unknown files
inside that managed config directory are also rejected before launch.

## Usage

```bash
python3 cli-tools/nddev_mimocode.py list --json
python3 cli-tools/nddev_mimocode.py plan --target /absolute/target --json
python3 cli-tools/nddev_mimocode.py install --target /absolute/target --json
python3 cli-tools/nddev_mimocode.py switch --profile safe --target /absolute/target --json
python3 cli-tools/nddev_mimocode.py migrate --target /absolute/target --json
python3 cli-tools/nddev_mimocode.py restore --backup 0 --target /absolute/target --json
python3 cli-tools/nddev_mimocode.py remove --target /absolute/target --json
```

Target-owned software lifecycle:

```bash
python3 cli-tools/nddev_mimocode.py software-status --target /absolute/target --json
python3 cli-tools/nddev_mimocode.py install-cli --target /absolute/target --json
python3 cli-tools/nddev_mimocode.py update-cli --target /absolute/target --json
python3 cli-tools/nddev_mimocode.py remove-cli --target /absolute/target --json
```

Launch forwards stdio and the child exit code:

```bash
python3 cli-tools/nddev_mimocode.py launch --target /absolute/target -- [args...]
```

Use `config/nddev-contract.json`, `build/version.json`, and
`references/mimocode-baseline.json` for exact runtime, release, platform,
permission, and installer facts. Use `cli-tools/nddev_mimocode.py` for the
enforced lifecycle behavior.

## Validation

```bash
python3 cli-tools/validate_public_contracts.py
```

The public validator is dependency-free, archive-safe, and does not install,
launch, authenticate, or contact live MiMo Code services. It disables bytecode
writes before importing local code, so the documented command leaves no
`__pycache__` residue in a clean checkout.
