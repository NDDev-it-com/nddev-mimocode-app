# MCP

MiMo Code supports MCP server definitions in native configuration. This public
setup ships an empty MCP object because it owns no real server.

Creator sequence:

1. Add a server only when the server command or URL is real and owned.
2. Keep local server commands deterministic and target-safe.
3. Keep authentication outside public setup content.

Checker sequence:

1. Reject placeholder, fake, or documentation-only servers.
2. Confirm remote servers have explicit intent and authentication boundaries.
3. Confirm the public validator still accepts the config.
