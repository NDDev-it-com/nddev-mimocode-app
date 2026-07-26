# NDDev MiMo Code Safe Setup

This target is owned by nddev-mimocode-app. Use MiMo Code through the
target-bound manager and keep all MiMo Code state under the explicit target.

Safe setup rules:

- Treat this profile as read-first and planning-only.
- Do not execute shell commands or edit files unless the caller explicitly
  changes setup profile.
- Use the `nddev-builder` skill and subagent for native setup artifact review.
- Do not read live auth files, provider secrets, or state outside
  `MIMOCODE_HOME`.
