# Threat model

## Protected assets

GitHub credentials, local source code, filesystem outside the run workspace,
integrity of generated patches, and the developer's machine.

## Primary threats and controls

- Prompt injection in repository files: repository text is delimited and
  labelled untrusted; it cannot select tools or commands.
- Arbitrary command execution: command adapters accept argv arrays and an
  allowlist, never shell strings.
- Path traversal/symlink escape: all paths are resolved under a run root and
  symlinks are excluded.
- Destructive Git operations: merge, reset, clean, and force-push are absent.
- Secret leakage: structured events contain summaries, not environments,
  credentials, or arbitrary file contents.
- Malicious project tests: MVP is restricted to user-trusted repositories;
  container or microVM isolation is required before scanning arbitrary repos.
