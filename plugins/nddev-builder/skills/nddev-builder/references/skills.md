# Skills

MiMo Code discovers native skills from `SKILL.md` files in configured skill
directories. The manager projects this toolkit into the target-owned config
tree.

Creator sequence:

1. Give each skill a narrow name and description.
2. Put routing and workflow guidance in `SKILL.md`.
3. Put longer reusable details in adjacent `references/` files.

Checker sequence:

1. Confirm every local reference named by a skill exists.
2. Confirm no generated evidence, cache, or private validation path is copied
   into public skill content.
3. Confirm volatile upstream facts remain owned by the baseline ledger.
