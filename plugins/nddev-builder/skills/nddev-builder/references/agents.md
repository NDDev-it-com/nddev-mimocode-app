# Agents

MiMo Code supports native primary agents and subagents through config and
agent markdown files. This toolkit ships an `nddev-builder` subagent for
artifact review and maintenance.

Creator sequence:

1. Use a narrow role and explicit scope.
2. Keep permissions consistent with the selected profile.
3. Reference managed instruction files instead of duplicating them.

Checker sequence:

1. Confirm the agent remains a subagent unless the setup contract changes.
2. Confirm prompt references resolve inside the target-owned config tree.
3. Confirm profile-owned permissions remain in profiles, not copied into the
   agent text.
