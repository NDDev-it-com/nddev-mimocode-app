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
version floor is published or claimed. The baseline preserves all 12 official
v0.1.9 uploaded runtime archive names and digests, plus the two generated
source downloads reported by the GitHub release page, as vendor observation
separate from the supported subset.
For every target-bound command the supported-host preflight runs before target
filesystem inspection; only lexical absolute-target validation precedes
external lifecycle coordination, except for the documented cold read-only
case where no product anchor exists yet. Mutating commands publish a complete
`global.lock` product anchor and canonical-target external marker with
atomic no-replace binding. Their final-path publication is the rollback
commit point, so published anchors are monotonic rendezvous files; a later
mutating opener recovers only a bounded same-inode publication alias after
locking the final anchor. Read-only commands fail closed if they observe an
incomplete hard-link publication state and leave the namespace unchanged.
Read-only `status`, `plan`, and `software-status` do not create anchors: a
cold read uses a no-create path and retries if a concurrent mutation publishes
`global.lock`, while a seeded read opens existing anchors no-follow/no-create.
Read-only commands create neither target-specific external markers nor
target-internal lock state.

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
python3 cli-tools/nddev_mimocode.py update --target /absolute/target --json
python3 cli-tools/nddev_mimocode.py switch --profile safe --target /absolute/target --json
python3 cli-tools/nddev_mimocode.py migrate --target /absolute/target --json
python3 cli-tools/nddev_mimocode.py restore --backup 0 --target /absolute/target --json
python3 cli-tools/nddev_mimocode.py remove --target /absolute/target --json
```

`update` is the setup-content update command. It reconciles an existing
managed target to the current module build for the target's recorded setup and
profile, creates a backup only when managed files change, verifies exact
postconditions, and is a true no-op only when the target is already current
and no post-commit cleanup is pending.
Target-owned MiMo Code software updates use `update-cli` instead.

When `--json` is present, invalid commands, missing required arguments, and
argument type errors return exit code 2 with a JSON error on stdout and an
empty stderr stream.

If a lifecycle command reaches the desired active state but cannot finish
irreversible cleanup, it leaves an immutable manager-owned cleanup journal under
`.nddev-mimocode-cleanup` and returns `cleanup_pending: true`. Read-only
`status`, `plan`, and `software-status` only validate and report that bounded
state; they never repair or drain it. The next mutating target-bound command
drains a valid journal before active changes, and malformed cleanup state fails
closed with exit code 2.

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
