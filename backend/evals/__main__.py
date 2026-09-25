from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

from evals.manifest import CASES_ROOT, load_cases
from evals.metrics import EvalReport
from evals.report import git_commit, publish, render_comparison_table, write_report
from evals.runner import DEFAULT_CASE_TIMEOUT_SECONDS, run_suite

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
BASELINE_LABEL = "deterministic-baseline"
SCANNERS = ["builtin-python", "bandit"]


def _progress(label: str, index: int, total: int, case_id: str) -> None:
    print(f"  [{label}] {index}/{total} {case_id}", file=sys.stderr, flush=True)


async def _run(args: argparse.Namespace) -> int:
    cases = load_cases(CASES_ROOT, args.case or None)
    if not cases:
        print("no cases selected", file=sys.stderr)
        return 1

    suites_to_run: list[tuple[str, str, bool]] = []
    if not args.no_baseline:
        suites_to_run.append((BASELINE_LABEL, "deterministic", False))
    for model in args.model:
        suites_to_run.append((model, model, True))

    scratch = Path(args.scratch or (BACKEND_ROOT / ".eval-scratch"))
    scratch.mkdir(parents=True, exist_ok=True)

    report = EvalReport(
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        git_commit=git_commit(REPO_ROOT),
        corpus_size=len(cases),
        scanners=SCANNERS,
    )
    for label, model, use_llm in suites_to_run:
        print(f"running suite {label} over {len(cases)} case(s)", file=sys.stderr, flush=True)
        suite = await run_suite(
            label,
            model,
            use_llm,
            cases,
            scratch_root=scratch,
            case_timeout=args.case_timeout,
            command_timeout=args.command_timeout,
            progress=_progress,
        )
        if suite.skipped_reason:
            print(f"  skipped: {suite.skipped_reason}", file=sys.stderr, flush=True)
        report.suites.append(suite)

    out_dir = Path(args.out) if args.out else BACKEND_ROOT / "evals" / "reports" / (
        report.generated_at.replace(":", "-")
    )
    json_path, markdown_path = write_report(report, cases, out_dir)
    print(f"\nwrote {json_path}\nwrote {markdown_path}\n", file=sys.stderr)
    print(render_comparison_table(report))

    if args.publish:
        for path in publish(report, cases, REPO_ROOT):
            print(f"published {path}", file=sys.stderr)

    if args.fail_under is not None:
        graded = [s for s in report.suites if not s.skipped_reason and s.label != BASELINE_LABEL]
        below = [s for s in graded if s.totals.outcome_rate < args.fail_under]
        if below:
            names = ", ".join(suite.label for suite in below)
            print(
                f"outcome rate below {args.fail_under:.0%} for: {names}",
                file=sys.stderr,
            )
            return 1
    return 0


def _list(args: argparse.Namespace) -> int:
    del args
    cases = load_cases()
    print(f"{len(cases)} case(s) in {CASES_ROOT}\n")
    for case in cases:
        expected = ", ".join(item.rule_id for item in case.expected_findings) or "none"
        print(f"  {case.id:<30} {case.expected_outcome:<14} {case.cwe:<9} {expected}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m evals",
        description="Replay the controlled vulnerability corpus through the OROD pipeline.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run the corpus and write a report")
    run.add_argument(
        "--model",
        action="append",
        default=[],
        metavar="MODEL",
        help="model to evaluate; repeatable (e.g. qwen2.5-coder:14b, claude-opus-5)",
    )
    run.add_argument(
        "--no-baseline",
        action="store_true",
        help="skip the deterministic codemod baseline suite",
    )
    run.add_argument("--case", action="append", default=[], help="restrict to a case id")
    run.add_argument("--out", help="report output directory")
    run.add_argument("--scratch", help="scratch directory for run workspaces")
    run.add_argument(
        "--case-timeout",
        type=float,
        default=DEFAULT_CASE_TIMEOUT_SECONDS,
        help="per-case wall-clock timeout in seconds",
    )
    run.add_argument("--command-timeout", type=int, default=120)
    run.add_argument(
        "--publish",
        action="store_true",
        help="also write docs/evals/latest.* and refresh the README table",
    )
    run.add_argument(
        "--fail-under",
        type=float,
        default=None,
        metavar="RATIO",
        help="exit non-zero if a model suite meets fewer than this share of expected outcomes",
    )
    run.set_defaults(handler=lambda args: asyncio.run(_run(args)))

    listing = sub.add_parser("list", help="list the corpus")
    listing.set_defaults(handler=_list)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    handler = args.handler
    result = handler(args)
    return int(result)


if __name__ == "__main__":
    raise SystemExit(main())
