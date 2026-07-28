# Native Config

MiMo Code configuration is managed through native config files and environment
selection owned by the manager.

Creator sequence:

1. Read the active target with the manager `status` command.
2. Read the module contract for the supported setup/profile model.
3. Edit only source setup/profile files that belong to this module.
4. Keep provider/model choices out of the managed profile unless the caller
   explicitly owns that policy.

Checker sequence:

1. Confirm the config uses the current native `permission` field.
2. Confirm deprecated permission aliases are absent.
3. Confirm no live MCP server or plugin is introduced without a real native
   artifact and explicit intent.
4. Run the public validator after any public content change.
