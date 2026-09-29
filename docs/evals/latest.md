# OROD evaluation report

Generated 2026-09-29T12:06:53+00:00 · commit `44cab67` · 21 controlled cases · scanners: builtin-python, bandit, osv (recorded)

The corpus is hermetic: no network access, no external scanners, and every case is a self-contained Python repository with a known vulnerability and a known expected outcome.

## Model comparison

| Model | Detection F1 | Recall | Precision | Auto-fix rate | Patch validity | Policy | Regressions | Median run | Tokens | Cost |
|---|---|---|---|---|---|---|---|---|---|---|
| `deterministic-baseline` | 1.00 | 100% | 100% | 12% (2/17) | 17% | 2/2 | 0 | 0.6s | 0 | $0.00 |
| `qwen2.5-coder:14b` | 1.00 | 100% | 100% | 88% (15/17) | 100% | 2/2 | 0 | 7.6s | 13,437 | $0.00 |

`Auto-fix rate` counts cases that require a validated patch. `Policy` counts cases where the pipeline is expected to decline and defer to a human. `Regressions` counts cases where a patch introduced a new high or critical finding.

## Per-case results
### `deterministic-baseline`

Provider `deterministic` · 21/21 runs completed · 6/21 expected outcomes met.

| Case | CWE | Expected | Detected | Met | Detail | Run | Tokens |
|---|---|---|---|---|---|---|---|
| `assert-based-authorization` | CWE-617 | B101 | B101 | yes | finding reported and correctly left for manual review | 0.2s | 0 |
| `clean-repository` | none | none | none | yes | no findings and no patch | 0.2s | 0 |
| `eval-untrusted-input` | CWE-95 | B307 | B307 | no | no patch was applied: No patch to validate. | 0.6s | 0 |
| `exec-dynamic-code` | CWE-95 | B102 | B102 | no | no patch was applied: No patch to validate. | 0.5s | 0 |
| `flask-debug-enabled` | CWE-489 | B201 | B201 | no | no patch was applied: No patch to validate. | 0.5s | 0 |
| `hardcoded-password` | CWE-798 | B105 | B105 | no | no patch was applied: No patch to validate. | 0.5s | 0 |
| `hardcoded-tmp-path` | CWE-377 | B108 | B108 | no | no patch was applied: No patch to validate. | 0.6s | 0 |
| `insecure-random-token` | CWE-330 | B311 | B311 | yes | finding reported and correctly left for manual review | 0.2s | 0 |
| `jinja2-autoescape-disabled` | CWE-79 | B701 | B701 | no | no patch was applied: No patch to validate. | 0.5s | 0 |
| `paramiko-auto-add-host-key` | CWE-322 | B507 | B507 | no | no patch was applied: No patch to validate. | 0.6s | 0 |
| `partial-executable-path` | CWE-426 | B607 | B404, B603, B607 | yes | validated patch resolved the finding | 1.2s | 0 |
| `pickle-untrusted-data` | CWE-502 | B301 | B301, B403 | no | no patch was applied: No patch to validate. | 0.6s | 0 |
| `requests-verify-disabled` | CWE-295 | B501 | B501 | no | no patch was applied: No patch to validate. | 0.6s | 0 |
| `shell-injection` | CWE-78 | B602 | B404, B602 | no | validation failed: Validation failed: pytest: failed tests/test_app.py::test_echo_value_round_trips; pytest: 1 fewer passing test(s) than before the patch. | 1.8s | 0 |
| `silent-exception-pass` | CWE-390 | B110 | B110 | no | no patch was applied: No patch to validate. | 0.6s | 0 |
| `sql-injection-format` | CWE-89 | B608 | B608 | no | no patch was applied: No patch to validate. | 0.6s | 0 |
| `ssl-unverified-context` | CWE-295 | B323 | B323 | no | no patch was applied: No patch to validate. | 0.6s | 0 |
| `vulnerable-dependency` | CWE-20 | GHSA-8q59-q68h-6hv4 | GHSA-8q59-q68h-6hv4, PYSEC-2021-142 | yes | validated patch resolved the finding | 1.1s | 0 |
| `weak-hash-md5` | CWE-327 | B324 | B324 | no | no patch was applied: No patch to validate. | 0.6s | 0 |
| `xml-entity-expansion` | CWE-611 | B314 | B314, B405 | yes | finding reported; remediation is out of scope for this case | 0.6s | 0 |
| `yaml-unsafe-load` | CWE-502 | B506 | B506 | no | no patch was applied: No patch to validate. | 0.6s | 0 |

### `qwen2.5-coder:14b`

Provider `ollama` · 21/21 runs completed · 19/21 expected outcomes met.

| Case | CWE | Expected | Detected | Met | Detail | Run | Tokens |
|---|---|---|---|---|---|---|---|
| `assert-based-authorization` | CWE-617 | B101 | B101 | yes | finding reported and correctly left for manual review | 0.2s | 0 |
| `clean-repository` | none | none | none | yes | no findings and no patch | 0.2s | 0 |
| `eval-untrusted-input` | CWE-95 | B307 | B307 | yes | validated patch resolved the finding | 23.8s | 1,114 |
| `exec-dynamic-code` | CWE-95 | B102 | B102 | yes | validated patch resolved the finding | 7.5s | 487 |
| `flask-debug-enabled` | CWE-489 | B201 | B201 | yes | validated patch resolved the finding | 7.1s | 486 |
| `hardcoded-password` | CWE-798 | B105 | B105 | no | validation failed: Validation failed: ruff: F401 app.py `os` imported but unused; ruff: F821 app.py Undefined name `os`; pytest: error tests/test_app.py. | 17.8s | 1,206 |
| `hardcoded-tmp-path` | CWE-377 | B108 | B108 | no | validation failed: Validation failed: pytest: failed tests/test_app.py::test_append_audit_returns_the_log_path; pytest: 1 fewer passing test(s) than before the patch. | 14.3s | 1,151 |
| `insecure-random-token` | CWE-330 | B311 | B311 | yes | finding reported and correctly left for manual review | 0.2s | 0 |
| `jinja2-autoescape-disabled` | CWE-79 | B701 | B701 | yes | validated patch resolved the finding | 7.3s | 488 |
| `paramiko-auto-add-host-key` | CWE-322 | B507 | B507 | yes | validated patch resolved the finding | 15.6s | 1,200 |
| `partial-executable-path` | CWE-426 | B607 | B404, B603, B607 | yes | validated patch resolved the finding | 11.7s | 608 |
| `pickle-untrusted-data` | CWE-502 | B301 | B301, B403 | yes | validated patch resolved the finding | 26.9s | 1,635 |
| `requests-verify-disabled` | CWE-295 | B501 | B501 | yes | validated patch resolved the finding | 7.5s | 485 |
| `shell-injection` | CWE-78 | B602 | B404, B602 | yes | validated patch resolved the finding | 10.1s | 612 |
| `silent-exception-pass` | CWE-390 | B110 | B110 | yes | validated patch resolved the finding | 7.0s | 473 |
| `sql-injection-format` | CWE-89 | B608 | B608 | yes | validated patch resolved the finding | 10.7s | 568 |
| `ssl-unverified-context` | CWE-295 | B323 | B323 | yes | validated patch resolved the finding | 7.4s | 471 |
| `vulnerable-dependency` | CWE-20 | GHSA-8q59-q68h-6hv4 | GHSA-8q59-q68h-6hv4, PYSEC-2021-142 | yes | validated patch resolved the finding | 1.2s | 0 |
| `weak-hash-md5` | CWE-327 | B324 | B324 | yes | validated patch resolved the finding | 7.6s | 477 |
| `xml-entity-expansion` | CWE-611 | B314 | B314, B405 | yes | finding reported; remediation is out of scope for this case | 22.4s | 1,499 |
| `yaml-unsafe-load` | CWE-502 | B506 | B506 | yes | validated patch resolved the finding | 7.6s | 477 |
