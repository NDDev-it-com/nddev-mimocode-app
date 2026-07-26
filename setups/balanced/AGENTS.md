# NDDev MiMo Code Balanced Setup

This target is owned by nddev-mimocode-app. Use MiMo Code through the
target-bound manager and keep all MiMo Code state under the explicit target.

Balanced setup rules:

- Read/search operations and common git inspection are allowed.
- Edits, shell execution, external network actions, and publishing remain
  approval-bound by the MiMo Code `permission` policy.
- Use the `nddev-builder` skill and subagent for native setup artifact review.
- Do not read live auth files, provider secrets, or state outside
  `MIMOCODE_HOME`.
