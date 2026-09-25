# OROD evaluation report

Generated 2026-08-26T10:16:44+00:00 · commit `2507544` · 20 controlled cases · scanners: builtin-python, bandit

The corpus is hermetic: no network access, no external scanners, and every case is a self-contained Python repository with a known vulnerability and a known expected outcome.

## Model comparison

| Model | Detection F1 | Recall | Precision | Auto-fix rate | Patch validity | Policy | Regressions | Median run | Tokens | Cost |
|---|---|---|---|---|---|---|---|---|---|---|
| `deterministic-baseline` | 1.00 | 100% | 100% | 6% (1/16) | 12% | 2/2 | 0 | 0.2s | 0 | $0.00 |
| `qwen2.5-coder:14b` | 1.00 | 100% | 100% | 6% (1/16) | 12% | 2/2 | 0 | 21.5s | 18,926 | $0.00 |

`Auto-fix rate` counts cases that require a validated patch. `Policy` counts cases where the pipeline is expected to decline and defer to a human. `Regressions` counts cases where a patch introduced a new high or critical finding.

## Per-case results
### `deterministic-baseline`

Provider `deterministic` · 20/20 runs completed · 5/20 expected outcomes met.

| Case | CWE | Expected | Detected | Met | Detail | Run | Tokens |
|---|---|---|---|---|---|---|---|
| `assert-based-authorization` | CWE-617 | B101 | B101 | yes | finding reported and correctly left for manual review | 0.2s | 0 |
| `clean-repository` | none | none | none | yes | no findings and no patch | 0.1s | 0 |
| `eval-untrusted-input` | CWE-95 | B307 | B307 | no | no patch was applied: No patch to validate. | 0.2s | 0 |
| `exec-dynamic-code` | CWE-95 | B102 | B102 | no | no patch was applied: No patch to validate. | 0.2s | 0 |
| `flask-debug-enabled` | CWE-489 | B201 | B201 | no | no patch was applied: No patch to validate. | 0.2s | 0 |
| `hardcoded-password` | CWE-798 | B105 | B105 | no | no patch was applied: No patch to validate. | 0.2s | 0 |
| `hardcoded-tmp-path` | CWE-377 | B108 | B108 | no | no patch was applied: No patch to validate. | 0.2s | 0 |
| `insecure-random-token` | CWE-330 | B311 | B311 | yes | finding reported and correctly left for manual review | 0.1s | 0 |
| `jinja2-autoescape-disabled` | CWE-79 | B701 | B701 | no | no patch was applied: No patch to validate. | 0.2s | 0 |
| `paramiko-auto-add-host-key` | CWE-322 | B507 | B507 | no | no patch was applied: No patch to validate. | 0.2s | 0 |
| `partial-executable-path` | CWE-426 | B607 | B404, B603, B607 | yes | validated patch resolved the finding | 0.8s | 0 |
| `pickle-untrusted-data` | CWE-502 | B301 | B301, B403 | no | no patch was applied: No patch to validate. | 0.2s | 0 |
| `requests-verify-disabled` | CWE-295 | B501 | B501 | no | no patch was applied: No patch to validate. | 0.2s | 0 |
| `shell-injection` | CWE-78 | B602 | B404, B602 | no | validation failed: No patch to validate. | 0.7s | 0 |
| `silent-exception-pass` | CWE-390 | B110 | B110 | no | no patch was applied: No patch to validate. | 0.2s | 0 |
| `sql-injection-format` | CWE-89 | B608 | B608 | no | no patch was applied: No patch to validate. | 0.2s | 0 |
| `ssl-unverified-context` | CWE-295 | B323 | B323 | no | no patch was applied: No patch to validate. | 0.2s | 0 |
| `weak-hash-md5` | CWE-327 | B324 | B324 | no | no patch was applied: No patch to validate. | 0.2s | 0 |
| `xml-entity-expansion` | CWE-611 | B314 | B314, B405 | yes | finding reported; remediation is out of scope for this case | 0.2s | 0 |
| `yaml-unsafe-load` | CWE-502 | B506 | B506 | no | no patch was applied: No patch to validate. | 0.2s | 0 |

### `qwen2.5-coder:14b`

Provider `ollama` · 20/20 runs completed · 5/20 expected outcomes met. 15 case(s) failed because the generated diff would not apply.

| Case | CWE | Expected | Detected | Met | Detail | Run | Tokens |
|---|---|---|---|---|---|---|---|
| `assert-based-authorization` | CWE-617 | B101 | B101 | yes | finding reported and correctly left for manual review | 0.2s | 0 |
| `clean-repository` | none | none | none | yes | no findings and no patch | 0.1s | 0 |
| `eval-untrusted-input` | CWE-95 | B307 | B307 | no | no patch was applied: Patch rejected: error: corrupt patch at line 6 | 18.2s | 986 |
| `exec-dynamic-code` | CWE-95 | B102 | B102 | no | no patch was applied: Patch rejected: error: corrupt patch at line 9 | 21.4s | 1,133 |
| `flask-debug-enabled` | CWE-489 | B201 | B201 | no | no patch was applied: Patch rejected: error: corrupt patch at line 9 | 19.3s | 1,071 |
| `hardcoded-password` | CWE-798 | B105 | B105 | no | no patch was applied: Patch rejected: error: corrupt patch at line 10 | 22.5s | 1,140 |
| `hardcoded-tmp-path` | CWE-377 | B108 | B108 | no | no patch was applied: Patch rejected: error: corrupt patch at line 10 | 20.6s | 1,133 |
| `insecure-random-token` | CWE-330 | B311 | B311 | yes | finding reported and correctly left for manual review | 0.2s | 0 |
| `jinja2-autoescape-disabled` | CWE-79 | B701 | B701 | no | no patch was applied: Patch rejected: error: corrupt patch at line 7 | 22.0s | 1,130 |
| `paramiko-auto-add-host-key` | CWE-322 | B507 | B507 | no | no patch was applied: Patch rejected: error: corrupt patch at line 11 | 23.6s | 1,204 |
| `partial-executable-path` | CWE-426 | B607 | B404, B603, B607 | yes | validated patch resolved the finding | 13.0s | 610 |
| `pickle-untrusted-data` | CWE-502 | B301 | B301, B403 | no | validation failed: Patch rejected: error: app.py: patch does not apply | 24.1s | 1,300 |
| `requests-verify-disabled` | CWE-295 | B501 | B501 | no | no patch was applied: Patch rejected: error: corrupt patch at line 7 | 22.3s | 1,152 |
| `shell-injection` | CWE-78 | B602 | B404, B602 | no | no patch was applied: Patch rejected: error: corrupt patch at line 12 | 25.4s | 1,364 |
| `silent-exception-pass` | CWE-390 | B110 | B110 | no | no patch was applied: Patch rejected: error: corrupt patch at line 12 | 21.7s | 1,129 |
| `sql-injection-format` | CWE-89 | B608 | B608 | no | no patch was applied: Patch rejected: error: corrupt patch at line 8 | 24.4s | 1,197 |
| `ssl-unverified-context` | CWE-295 | B323 | B323 | no | no patch was applied: Patch rejected: error: corrupt patch at line 7 | 19.9s | 1,021 |
| `weak-hash-md5` | CWE-327 | B324 | B324 | no | no patch was applied: Patch rejected: error: corrupt patch at line 9 | 20.2s | 1,016 |
| `xml-entity-expansion` | CWE-611 | B314 | B314, B405 | yes | finding reported; remediation is out of scope for this case | 771.1s | 1,286 |
| `yaml-unsafe-load` | CWE-502 | B506 | B506 | no | no patch was applied: Patch rejected: error: corrupt patch at line 7 | 174.5s | 1,054 |
