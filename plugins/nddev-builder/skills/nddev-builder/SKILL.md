---
name: nddev-builder
description: Review and maintain native MiMo Code setup artifacts managed by nddev-mimocode-app.
---

# nddev-builder for MiMo Code

Use this skill when editing or reviewing NDDev MiMo Code setup artifacts.

Rules:

- Keep repository artifacts in English and owner-facing summaries in the
  caller's language.
- Preserve the explicit-target boundary. Do not read or write MiMo Code auth,
  cache, data, or state outside `MIMOCODE_HOME`.
- Use only current MiMo Code native surfaces: `mimocode.json`, `AGENTS.md`,
  skills under `skills/`, and agents under `agents/`.
- Do not add marketplace assumptions unless an official MiMo Code marketplace
  contract exists.
- Keep the `permission` config authoritative. Do not reintroduce deprecated
  `tools` permission config.
