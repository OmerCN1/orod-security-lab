# OROD evaluation report

Generated 2026-09-27T13:00:42+00:00 · commit `cbdff93` · 20 controlled cases · scanners: builtin-python, bandit

The corpus is hermetic: no network access, no external scanners, and every case is a self-contained Python repository with a known vulnerability and a known expected outcome.

## Model comparison

| Model | Detection F1 | Recall | Precision | Auto-fix rate | Patch validity | Policy | Regressions | Median run | Tokens | Cost |
|---|---|---|---|---|---|---|---|---|---|---|
| `deterministic-baseline` | 1.00 | 100% | 100% | 6% (1/16) | 12% | 2/2 | 0 | 0.6s | 0 | $0.00 |
| `qwen2.5-coder:14b` | 1.00 | 100% | 100% | 69% (11/16) | 100% | 2/2 | 0 | 7.2s | 12,373 | $0.00 |

`Auto-fix rate` counts cases that require a validated patch. `Policy` counts cases where the pipeline is expected to decline and defer to a human. `Regressions` counts cases where a patch introduced a new high or critical finding.

## Per-case results
### `deterministic-baseline`

Provider `deterministic` · 20/20 runs completed · 5/20 expected outcomes met.

| Case | CWE | Expected | Detected | Met | Detail | Run | Tokens |
|---|---|---|---|---|---|---|---|
| `assert-based-authorization` | CWE-617 | B101 | B101 | yes | finding reported and correctly left for manual review | 0.2s | 0 |
| `clean-repository` | none | none | none | yes | no findings and no patch | 0.2s | 0 |
| `eval-untrusted-input` | CWE-95 | B307 | B307 | no | no patch was applied: No patch to validate. | 0.7s | 0 |
| `exec-dynamic-code` | CWE-95 | B102 | B102 | no | no patch was applied: No patch to validate. | 0.6s | 0 |
| `flask-debug-enabled` | CWE-489 | B201 | B201 | no | no patch was applied: No patch to validate. | 0.6s | 0 |
| `hardcoded-password` | CWE-798 | B105 | B105 | no | no patch was applied: No patch to validate. | 0.6s | 0 |
| `hardcoded-tmp-path` | CWE-377 | B108 | B108 | no | no patch was applied: No patch to validate. | 0.6s | 0 |
| `insecure-random-token` | CWE-330 | B311 | B311 | yes | finding reported and correctly left for manual review | 0.2s | 0 |
| `jinja2-autoescape-disabled` | CWE-79 | B701 | B701 | no | no patch was applied: No patch to validate. | 0.6s | 0 |
| `paramiko-auto-add-host-key` | CWE-322 | B507 | B507 | no | no patch was applied: No patch to validate. | 0.6s | 0 |
| `partial-executable-path` | CWE-426 | B607 | B404, B603, B607 | yes | validated patch resolved the finding | 1.1s | 0 |
| `pickle-untrusted-data` | CWE-502 | B301 | B301, B403 | no | no patch was applied: No patch to validate. | 0.6s | 0 |
| `requests-verify-disabled` | CWE-295 | B501 | B501 | no | no patch was applied: No patch to validate. | 0.6s | 0 |
| `shell-injection` | CWE-78 | B602 | B404, B602 | no | validation failed: Validation failed: pytest: failed tests/test_app.py::test_echo_value_round_trips; pytest: 1 fewer passing test(s) than before the patch. | 1.7s | 0 |
| `silent-exception-pass` | CWE-390 | B110 | B110 | no | no patch was applied: No patch to validate. | 0.6s | 0 |
| `sql-injection-format` | CWE-89 | B608 | B608 | no | no patch was applied: No patch to validate. | 0.7s | 0 |
| `ssl-unverified-context` | CWE-295 | B323 | B323 | no | no patch was applied: No patch to validate. | 0.6s | 0 |
| `weak-hash-md5` | CWE-327 | B324 | B324 | no | no patch was applied: No patch to validate. | 0.6s | 0 |
| `xml-entity-expansion` | CWE-611 | B314 | B314, B405 | yes | finding reported; remediation is out of scope for this case | 0.6s | 0 |
| `yaml-unsafe-load` | CWE-502 | B506 | B506 | no | no patch was applied: No patch to validate. | 0.6s | 0 |

### `qwen2.5-coder:14b`

Provider `ollama` · 20/20 runs completed · 15/20 expected outcomes met.

| Case | CWE | Expected | Detected | Met | Detail | Run | Tokens |
|---|---|---|---|---|---|---|---|
| `assert-based-authorization` | CWE-617 | B101 | B101 | yes | finding reported and correctly left for manual review | 0.2s | 0 |
| `clean-repository` | none | none | none | yes | no findings and no patch | 0.2s | 0 |
| `eval-untrusted-input` | CWE-95 | B307 | B307 | no | validation failed: Validation failed: ruff: F821 app.py Undefined name `ast`; pytest: failed tests/test_app.py::test_parse_setting_reads_a_mapping; pytest: 1 fewer passing test(s) than before the patch. | 12.9s | 961 |
| `exec-dynamic-code` | CWE-95 | B102 | B102 | yes | validated patch resolved the finding | 7.1s | 487 |
| `flask-debug-enabled` | CWE-489 | B201 | B201 | yes | validated patch resolved the finding | 5.9s | 486 |
| `hardcoded-password` | CWE-798 | B105 | B105 | no | validation failed: Validation failed: ruff: F821 app.py Undefined name `os`; pytest: error tests/test_app.py. | 13.0s | 991 |
| `hardcoded-tmp-path` | CWE-377 | B108 | B108 | no | validation failed: Validation failed: pytest: failed tests/test_app.py::test_append_audit_returns_the_log_path; pytest: 1 fewer passing test(s) than before the patch. | 13.7s | 1,031 |
| `insecure-random-token` | CWE-330 | B311 | B311 | yes | finding reported and correctly left for manual review | 0.2s | 0 |
| `jinja2-autoescape-disabled` | CWE-79 | B701 | B701 | yes | validated patch resolved the finding | 6.6s | 488 |
| `paramiko-auto-add-host-key` | CWE-322 | B507 | B507 | no | validation failed: Patch did not resolve selected findings: B507 in app.py | 14.6s | 1,034 |
| `partial-executable-path` | CWE-426 | B607 | B404, B603, B607 | yes | validated patch resolved the finding | 10.5s | 609 |
| `pickle-untrusted-data` | CWE-502 | B301 | B301, B403 | no | validation failed: Patch did not resolve selected findings: B301 in app.py, B403 in app.py | 24.2s | 1,411 |
| `requests-verify-disabled` | CWE-295 | B501 | B501 | yes | validated patch resolved the finding | 7.3s | 485 |
| `shell-injection` | CWE-78 | B602 | B404, B602 | yes | validated patch resolved the finding | 8.6s | 614 |
| `silent-exception-pass` | CWE-390 | B110 | B110 | yes | validated patch resolved the finding | 6.0s | 473 |
| `sql-injection-format` | CWE-89 | B608 | B608 | yes | validated patch resolved the finding | 8.5s | 547 |
| `ssl-unverified-context` | CWE-295 | B323 | B323 | yes | validated patch resolved the finding | 6.2s | 471 |
| `weak-hash-md5` | CWE-327 | B324 | B324 | yes | validated patch resolved the finding | 7.0s | 477 |
| `xml-entity-expansion` | CWE-611 | B314 | B314, B405 | yes | finding reported; remediation is out of scope for this case | 20.9s | 1,335 |
| `yaml-unsafe-load` | CWE-502 | B506 | B506 | yes | validated patch resolved the finding | 7.1s | 473 |
