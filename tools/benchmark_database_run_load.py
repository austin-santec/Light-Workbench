"""Read-only timing benchmark for database-backed run loading."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from application.database_primary_workflow import DatabaseRunContext
from infrastructure.database.runtime import build_database_primary_workflow


def summarize_elapsed(values: list[int]) -> dict[str, float | int]:
    """Return stable summary statistics for measured milliseconds."""
    if not values:
        raise ValueError("At least one measured iteration is required")
    return {
        "minimum_ms": min(values),
        "median_ms": statistics.median(values),
        "average_ms": statistics.mean(values),
        "maximum_ms": max(values),
    }


def _context_report(context: DatabaseRunContext) -> dict[str, object]:
    summary = context.load_summary
    if summary is None:
        return {}
    return {
        "operation_id": summary.operation_id,
        "load_source": summary.source,
        "workflow_elapsed_ms": summary.elapsed_ms,
        "stage_timings_ms": dict(summary.stage_timings_ms),
        "counts": dict(summary.counts),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only benchmark for loading one database run."
    )
    parser.add_argument("--main-board-serial", required=True)
    parser.add_argument("--run-number", required=True, type=int)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--database-config", type=Path)
    parser.add_argument("--output-json", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.warmups < 0 or args.iterations < 1:
        print("warmups must be nonnegative and iterations must be positive", file=sys.stderr)
        return 2

    try:
        workflow = build_database_primary_workflow(
            database_config_path=args.database_config
        )
        for _ in range(args.warmups):
            workflow.load_for_unit(args.main_board_serial, args.run_number)

        elapsed_values: list[int] = []
        reports: list[dict[str, object]] = []
        for index in range(args.iterations):
            started = time.perf_counter()
            context = workflow.load_for_unit(
                args.main_board_serial, args.run_number
            )
            elapsed_ms = max(0, int((time.perf_counter() - started) * 1000))
            elapsed_values.append(elapsed_ms)
            report = {
                "iteration": index + 1,
                "elapsed_ms": elapsed_ms,
                "context": _context_report(context),
            }
            reports.append(report)
            print(
                "Iteration {0}: {1} ms (workflow {2} ms)".format(
                    index + 1,
                    elapsed_ms,
                    report["context"].get("workflow_elapsed_ms", "n/a"),
                )
            )

        output = {
            "main_board_serial": args.main_board_serial,
            "run_number": args.run_number,
            "warmups": args.warmups,
            "iterations": args.iterations,
            "summary": summarize_elapsed(elapsed_values),
            "reports": reports,
        }
        print("Summary: " + json.dumps(output["summary"], sort_keys=True))
        if args.output_json is not None:
            args.output_json.parent.mkdir(parents=True, exist_ok=True)
            args.output_json.write_text(
                json.dumps(output, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
    except Exception as error:
        print(
            "Database run-load benchmark failed: %s: %s"
            % (type(error).__name__, str(error)[:500]),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
