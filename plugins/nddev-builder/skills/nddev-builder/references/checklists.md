# Checklists

Creator checklist:

1. Identify the native artifact family.
2. Read the code-owned contract and baseline facts.
3. Make the smallest source change in the owning public file.
4. Keep development-only tests and evidence out of the public module.
5. Run the public validator.

Checker checklist:

1. Verify every referenced public path exists.
2. Verify no private harness path, generated cache, or secret marker appears.
3. Verify setup/profile separation is preserved.
4. Verify full-auto and safe posture are profile-owned.
5. Verify unsupported marketplace, fake MCP, and fake hook projections are
   absent.
