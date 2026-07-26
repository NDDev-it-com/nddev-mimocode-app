# NDDev MiMo Code Full-Auto Setup

This target is owned by nddev-mimocode-app. Use MiMo Code through the
target-bound manager and keep all MiMo Code state under the explicit target.

Full-auto setup rules:

- Use autonomous MiMo Code permissions only within this isolated target.
- Destructive shell patterns and publish operations remain constrained by the
  managed `permission` policy.
- Use the `nddev-builder` skill and subagent for native setup artifact review.
- Do not read live auth files, provider secrets, or state outside
  `MIMOCODE_HOME`.
