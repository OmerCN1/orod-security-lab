# Threat model

## Protected assets

GitHub credentials, local source code, filesystem outside the run workspace,
integrity of generated patches, and the developer's machine.

## Primary threats and controls

- Other web pages reaching the local API: the API acts with the operator's GitHub
  credentials, so any page open in the browser is a potential caller. Host validation
  refuses non-loopback `Host` headers, which defeats DNS rebinding; every request needs
  the bearer token from `data/api-token` (mode 0600) or `OROD_API_TOKEN`; writes with a
  foreign `Origin` are refused. The dashboard's Vite proxy holds the token server-side
  and Vite itself refuses unknown hosts, so the browser never sees it and the token is
  never put in a URL, where access logs would record it.
- Prompt injection in repository files: repository text is delimited and
  labelled untrusted; it cannot select tools or commands.
- Arbitrary command execution: command adapters accept argv arrays and an
  allowlist, never shell strings. Bandit analysis uses Python isolated mode to avoid
  importing a repository-provided `bandit.py` before test consent.
- Patch scope: parse all file headers and hunk boundaries, require an exact match
  to `changed_files`, and reject renames, adds/deletes, mode changes, binary targets,
  hidden paths and symlink components before invoking `git apply`.
- Path traversal/symlink escape: repository inventory, dependency discovery, working
  source reads, patch target validation, Python summaries, the built-in scanner and
  container input copies share `RepositoryFiles`. Relative paths must be canonical;
  hidden/ignored paths and private-key filenames are excluded. Directory descriptors
  and `O_NOFOLLOW` reject symlink files and parent directories at open time, before
  resolution can hide the link. Only regular UTF-8 text files within the configured
  byte limit are read, with a bounded read rechecking size after metadata inspection.
  Git base reads also verify blob mode and size. Fixture copies preserve links so the
  common policy can reject them instead of first dereferencing their targets.
- Destructive Git operations: merge, reset, clean, and force-push are absent.
- Secret leakage: structured events contain summaries, not environments,
  credentials, or arbitrary file contents.
- Malicious project tests: explicit per-run trust is required, including for demos.
  GitHub validation uses an unprivileged, offline container with read-only root/input,
  writable size-limited tmpfs, dropped capabilities, process/CPU/memory limits and a
  deadline. Only a filtered temporary copy is mounted, never the original workspace,
  host home, Git metadata or Docker socket. Timeout/cancellation removes the container;
  output is drained with bounded tails and container logging is disabled.
  Missing Docker/image support blocks validation instead of executing on the host.
  Server-owned demo fixtures remain local after explicit consent.

## Remaining boundary

Container isolation covers validation only. Host-side cloning, static parsers, network
scanners and dependency discovery still handle untrusted repository data. This is not
a claim that arbitrary hostile repositories are fully sandboxed, and push-permission
restrictions remain in place. Containers share the daemon host kernel; use a dedicated
Docker VM/host for stronger isolation. Additional project dependencies belong in an
operator-maintained image; no repository-controlled installation commands run.
