# Security

Report security issues privately to the repository owner.

This module manages only explicit target directories. It must not read live
MiMo Code authentication, provider credentials, runtime caches, or state
outside the target supplied with `--target`.

The manager validates target ownership, preserves unmanaged target files,
rolls back failed mutations, and holds lifecycle locks through launched child
completion. The exact lock and software handoff contract is owned by
`config/nddev-contract.json` and enforced by `cli-tools/nddev_mimocode.py`.
Manager-owned launch and staged-probe environment values disable upstream
analysis telemetry, autoupdate, project config discovery, external compatibility
loaders, and external skill/plugin discovery; caller overrides are rejected.
Launch also rejects unknown files under the managed `MIMOCODE_CONFIG_DIR`
projection instead of executing or deleting them.
Target-owned software install, update, and launch reject non-canonical product
hosts before network, staging, or runtime: only macOS arm64/x64 and Ubuntu glibc
arm64/x64 are in scope, with no official Ubuntu version floor claimed.

The full-auto profile is a no-sandbox runtime posture. Deliberate same-UID
tampering outside that no-sandbox boundary is not claimed to be prevented.
