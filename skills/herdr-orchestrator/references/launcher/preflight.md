# Runtime preflight

Require `HERDR_ENV=1` and resolve the canonical project root. Then invoke the
packaged thin runtime for the selected role.

The runtime loads the accepted project config and Workspace Protocol, validates
their repository binding and the exact configured recipe needed for this
launch, then uses Herdr pane and agent operations. Stop on validation or Herdr
failure. An invalid accepted configuration requires setup/update; runtime never
substitutes another harness, model, profile, or authority envelope.

Preflight is complete when the environment and project root are resolved. The
runtime performs the launch-specific validation immediately before start.
