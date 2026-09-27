# ADR 0011: Local API access control, non-Python repositories and CI

## Context

The API listened on loopback without authentication and acts with the operator's GitHub
credentials once publishing is enabled. CORS stops other sites from reading responses,
but not from sending them: a page using DNS rebinding reaches `localhost:8000` under its
own origin and could start trusted runs, approve patches and open pull requests.

Separately, a repository with no Python code went through every stage and was reported
as clean, although no scanner, check or codemod applies to it. And every verification so
far had been run by hand.

## Decision

- `TrustedHostMiddleware` accepts only `OROD_ALLOWED_HOSTS` (loopback by default).
- Every API route requires a bearer token: `OROD_API_TOKEN`, or `data/api-token`,
  created on first start with `O_EXCL` and mode 0600 and reused afterwards.
- Writes carrying an `Origin` other than the dashboard's are refused, because the
  dashboard's proxy adds the token to whatever reaches it.
- The dashboard calls `/api/v1` same-origin through the Vite dev-server proxy, which
  reads the token file per request and adds the header server-side. The browser never
  holds the token, EventSource needs no token in its URL, and Vite's own host check
  covers the proxy against rebinding.
- The architect stops a repository with no Python source files with an explicit error,
  and warns when most source files are in another language.
- GitHub Actions runs, on every pull request and push to `main`: backend lint, strict
  mypy, tests and the deterministic evaluation, which fails if any case the recorded
  report met is no longer met, regressions rise or detection F1 falls; and frontend lint,
  tests, type check and build.

## Consequences

Direct API use (`curl`, `/docs`) needs the token from `data/api-token`. A production
build of the dashboard served without the dev proxy would need its own token handling.
The access control assumes a single operator on the machine: any local process that can
read `data/api-token` is trusted. CI cannot run the Docker isolation test or any model
suite; those stay manual.
