# Plugins, Tools, And Hooks

MiMo Code supports local plugins, custom tools, and plugin hook APIs. This
setup does not ship a marketplace, fake hook, fake server, or default plugin.

Creator sequence:

1. Use native plugin or custom-tool files only when the implementation is real.
2. Keep deterministic adapters as regular files with bounded behavior.
3. Document the runtime boundary in code-owned surfaces before enabling a new
   artifact family.

Checker sequence:

1. Reject marketplace assumptions.
2. Reject placeholder hooks or empty adapters that imply unsupported behavior.
3. Confirm the config names only shipped native artifacts.
