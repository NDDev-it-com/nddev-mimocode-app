# Changelog

## 0.2.0

- Replace setup variants with the `nddev-builder` content setup and
  orthogonal `full-auto` and `safe` profiles.
- Add target-internal and external lifecycle locking for setup, software, and
  launch operations.
- Add explicit setup `update` lifecycle distinct from target-owned software
  `update-cli`.
- Bind software installation to verified official MiMo Code release assets and
  the verified official installer in local-binary mode.
- Add canonical `AGENTS.md` plus the Claude instruction bridge.
- Harden public contract validation for archive execution.

## 0.1.0

- Add explicit-target MiMo Code setup manager.
- Add safe, balanced, and full-auto setup variants.
- Add target-bound backup, restore, remove, rollback, drift, and safety checks.
- Add exact MiMo Code `v0.1.9` software install/update support.
- Add native nddev-builder skill/agent/instruction projection.
- Add dependency-free public contract validator and shared CI callers.
