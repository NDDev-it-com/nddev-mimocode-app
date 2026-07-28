---
name: nddev-builder
description: Build and review native MiMo Code setup artifacts managed by nddev-mimocode-app.
---

# nddev-builder for MiMo Code

Use this skill when creating, reviewing, or repairing MiMo Code artifacts that
belong to an NDDev-managed target.

Start with the source-owned facts:

- Run the public manager's `status` and `software-status` commands for target
  state and installed software readiness.
- Read the module contract for lifecycle and threat-boundary rules.
- Read the module baseline ledger for current upstream release and native
  capability facts.

Then open only the focused reference needed for the artifact family:

- `references/native-config.md` for `mimocode.json`, config precedence, and
  profile-owned permission posture.
- `references/instructions.md` for `AGENTS.md`, Claude compatibility, and
  instruction layering.
- `references/skills.md` for native skill directories and `SKILL.md` shape.
- `references/agents.md` for native agent and subagent definitions.
- `references/mcp.md` for MCP server definitions and the empty-server boundary.
- `references/plugins-tools-hooks.md` for native plugin, custom tool, and hook
  boundaries.
- `references/checklists.md` for creator/checker sequences.

Keep all generated runtime state, credentials, logs, caches, and private
validation evidence out of public setup content.
