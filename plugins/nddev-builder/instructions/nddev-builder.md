# NDDev Builder Instructions for MiMo Code

Maintain setup-manager artifacts as native MiMo Code configuration:

- `mimocode.json` owns permission, agent, skills, and instruction references.
- `AGENTS.md` provides global target instructions.
- `skills/nddev-builder/SKILL.md` provides the native builder skill.
- `agents/nddev-builder.md` provides the native builder subagent.

Keep marketplace support unset unless official MiMo Code documentation defines
a marketplace contract. Keep all provider auth and runtime state outside the
manager's read/write scope.
