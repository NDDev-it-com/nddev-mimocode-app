# Instructions

MiMo Code prefers `AGENTS.md` instructions. Claude-compatible files are a
compatibility surface, not the authoritative NDDev instruction source.

Creator sequence:

1. Put stable target behavior in the managed setup `AGENTS.md`.
2. Keep volatile release, hash, path inventory, and validator field lists in
   code-owned files.
3. Use the Claude bridge only where the public governance contract requires it.

Checker sequence:

1. Verify instruction files are regular files, not symlinks.
2. Verify the instructions do not point to development-only harness paths.
3. Verify public docs point to code owners instead of copying runtime facts.
