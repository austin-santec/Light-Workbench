"""Seed approved, synthetic sample runs into a local development database.

The command is intentionally dry-run by default.  It never deletes or refreshes
records and refuses database targets that do not clearly identify a local test
or development database.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

# Allow the documented ``python tools/seed_sample_runs.py`` form as well as
# ``python -m tools.seed_sample_runs`` when launched from the repository root.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from application.sample_database_seeding import (
    SampleDatabaseSeeder,
    SampleScenarioError,
    load_scenario,
    scenario_summary,
)
from config.app_config import DEFAULT_PATHS
from config.database_config import DEFAULT_DATABASE_NAME, DEFAULT_DATABASE_SERVER
from infrastructure.database.runtime import build_database_primary_workflow
from infrastructure.database.settings_repository import DatabaseSettingsRepository


SCENARIO_ROOT = PROJECT_ROOT / "sample_data" / "scenarios"


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        scenarios = _select_scenarios(args)
        if args.list:
            _print_scenarios(scenarios)
            return 0
        settings = DatabaseSettingsRepository(Path(args.config)).load()
        _print_target(settings)
        if not _safe_database_target(settings):
            raise SampleScenarioError(
                "Refusing to seed this database. Use a local test/development "
                "database such as localhost\\SQLEXPRESS / LWBTestDB."
            )
        if args.apply:
            workflow = build_database_primary_workflow(
                database_config_path=Path(args.config)
            )
            seeder = SampleDatabaseSeeder(workflow)
            for scenario in scenarios:
                result = seeder.seed(scenario)
                print(
                    f"{result.scenario_id}: {result.action}; "
                    f"runs={len(result.run_ids)}, measurements={result.measurement_count}, "
                    f"replacements={result.replacement_count}, spares={result.spare_count}"
                )
                print(f"Verified {result.scenario_id} through the database read model.")
            return 0

        _print_dry_run(scenarios)
        if args.inspect_existing:
            try:
                workflow = build_database_primary_workflow(
                    database_config_path=Path(args.config)
                )
                seeder = SampleDatabaseSeeder(workflow)
                for scenario in scenarios:
                    state = seeder._existing_state(scenario)
                    print(f"Existing sample state: {scenario.scenario_id}: {state}")
            except Exception as error:  # Read-only inspection should not hide the plan.
                print(f"Existing-record inspection unavailable: {error}")
        print("No database writes performed. Use --apply after reviewing this plan.")
        return 0
    except (OSError, ValueError, SampleScenarioError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    except Exception as error:
        print(f"ERROR: database seeding could not be completed: {error}", file=sys.stderr)
        return 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Seed reusable Light Workbench sample runs into a safe local database."
    )
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--list", action="store_true", help="List available scenarios.")
    selection.add_argument(
        "--scenario",
        help="Scenario ID, JSON filename, or path under sample_data/scenarios.",
    )
    selection.add_argument("--all", action="store_true", help="Select every scenario.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the selected scenarios. Default is a read-only dry run.",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_PATHS.database_config_path),
        help="Database INI path (defaults to the normal application config).",
    )
    parser.add_argument(
        "--inspect-existing",
        action="store_true",
        help="During dry-run, inspect existing sample records if SQL Server is available.",
    )
    return parser


def _select_scenarios(args):
    paths = sorted(SCENARIO_ROOT.glob("*.json"))
    if args.list:
        return tuple(load_scenario(path) for path in paths)
    if args.scenario:
        requested = Path(args.scenario)
        candidates = [requested] if requested.is_file() else paths
        for path in candidates:
            scenario = load_scenario(path)
            if args.scenario in {scenario.scenario_id, path.name, path.stem}:
                return (scenario,)
        raise SampleScenarioError(f"Scenario not found: {args.scenario}")
    if args.all:
        if not paths:
            raise SampleScenarioError(f"No scenarios found in {SCENARIO_ROOT}")
        return tuple(load_scenario(path) for path in paths)
    raise SampleScenarioError("Choose --list, --scenario SCENARIO, or --all.")


def _print_scenarios(scenarios) -> None:
    for scenario in scenarios:
        summary = scenario_summary(scenario)
        print(
            f"{summary['scenario_id']}: {summary['description']} "
            f"(model={summary['model']}, runs={summary['runs']}, "
            f"measurements={summary['measurements']}, "
            f"replacements={summary['replacements']}, spares={summary['spares']})"
            f" station={summary['station_number']}"
        )


def _print_target(settings) -> None:
    print(f"Target SQL Server: {settings.server}")
    print(f"Target database: {settings.database}")
    print(f"Windows authentication: yes; enabled: {settings.enabled}")


def _print_dry_run(scenarios) -> None:
    print("Dry-run plan:")
    for scenario in scenarios:
        summary = scenario_summary(scenario)
        print(
            f"  {summary['scenario_id']}: unit=1, switch=1, assignment=1, "
            f"runs={summary['runs']}, measurements={summary['measurements']}, "
            f"replacements={summary['replacements']}, spares={summary['spares']}, "
            f"station={summary['station_number']}"
        )
    print("Writes planned: create-only sample records; no deletes or refreshes.")


def _safe_database_target(settings) -> bool:
    server = str(settings.server).strip().lower().replace(" ", "")
    database = str(settings.database).strip().lower()
    local_server = server in {
        DEFAULT_DATABASE_SERVER.lower().replace(" ", ""),
        "localhost",
        "127.0.0.1",
        ".\\sqlexpress",
    } or server.startswith("localhost\\")
    safe_name = (
        database == DEFAULT_DATABASE_NAME.lower()
        or any(token in database for token in ("test", "dev", "local", "sandbox"))
    ) and not any(token in database for token in ("prod", "production"))
    return bool(settings.enabled and local_server and safe_name)


if __name__ == "__main__":
    raise SystemExit(main())
