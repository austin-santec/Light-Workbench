"""Application service for loading and preparing persisted COC source runs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from domain.coc_preparation import CocPreparationResult, CocSourceRun, prepare_coc
from domain.limit_profiles import legacy_limit_profile
from domain.models import MeasurementRecord


@dataclass(frozen=True)
class CocRunOption:
    """One selectable persisted run and its prepared source data."""

    source: CocSourceRun

    @property
    def label(self) -> str:
        return "Run %d — %d written reading%s" % (
            self.source.run_number,
            len(self.source.measurements),
            "" if len(self.source.measurements) == 1 else "s",
        )


class CocWorkflow:
    """Load COC candidates through repositories and invoke domain validation."""

    def __init__(self, run_repository, unit_repository):
        self.run_repository = run_repository
        self.unit_repository = unit_repository

    def available_runs(self, unit_directory: str | Path) -> list[CocRunOption]:
        """Return readable numbered runs from one unit, ordered by run number."""
        unit_path = Path(unit_directory)
        record = self.unit_repository.load_record(unit_path)
        paths: dict[int, Path] = {}
        for entry in record.get("runs", []):
            if not isinstance(entry, dict):
                continue
            try:
                run_number = int(entry.get("run_number"))
            except (TypeError, ValueError):
                continue
            directory = str(entry.get("directory") or "").strip()
            csv_name = str(entry.get("csv_file") or "").strip()
            candidate = unit_path / directory / csv_name
            if directory and csv_name and candidate.is_file():
                paths[run_number] = candidate

        for run_number in self.unit_repository.available_run_numbers(unit_path):
            if run_number in paths:
                continue
            candidate = self.unit_repository.find_run_csv_for_number(
                unit_path, run_number
            )
            if candidate is not None and candidate.is_file():
                paths[run_number] = candidate

        options = []
        for run_number, path in sorted(paths.items()):
            try:
                source = self.load_source(path, fallback_run_number=run_number)
            except (OSError, ValueError, TypeError, KeyError):
                continue
            if source.measurements:
                options.append(CocRunOption(source))
        return options

    def load_source(
        self,
        csv_path: str | Path,
        *,
        fallback_run_number: int = 1,
    ) -> CocSourceRun:
        """Load accepted readings plus physical-port and criteria JSON details."""
        run_data = self.run_repository.load_csv(csv_path)
        criteria = None
        physical_ports = {}
        references = {}
        json_path = self.run_repository.find_json_path(csv_path)
        if json_path.is_file():
            payload = self.run_repository.load_json(json_path)
            for item in payload.get("measurements", []):
                if not isinstance(item, dict):
                    continue
                try:
                    channel = int(item["channel"])
                except (KeyError, TypeError, ValueError):
                    continue
                if item.get("physical_port") is not None:
                    physical_ports[channel] = int(item["physical_port"])
                if isinstance(item.get("reference"), dict):
                    references[channel] = item["reference"]
            saved_criteria = payload.get("criteria")
            if isinstance(saved_criteria, dict):
                criteria = dict(saved_criteria)
            else:
                criteria = legacy_limit_profile(
                    float(payload.get("warning_limit_db", 2.0))
                ).as_dict()

        measurements = tuple(
            MeasurementRecord(
                record.channel,
                record.loss_1310,
                record.loss_1550,
                physical_ports.get(record.channel),
                references.get(record.channel, record.reference_snapshot),
            )
            for record in run_data.measurements
        )
        try:
            run_number = int(
                run_data.metadata.get("Run number", fallback_run_number)
            )
        except (TypeError, ValueError):
            run_number = int(fallback_run_number)
        return CocSourceRun(
            run_number=run_number,
            source_path=Path(csv_path),
            measurements=measurements,
            metadata=dict(run_data.metadata),
            criteria=criteria,
        )

    def prepare(
        self,
        base_run: CocSourceRun,
        front_panel_channel_count: int,
        *,
        supplemental_run: CocSourceRun | None = None,
        completed_replacements=(),
        designated_spares=(),
    ) -> CocPreparationResult:
        """Prepare one validated COC result from explicit source selections."""
        return prepare_coc(
            base_run,
            front_panel_channel_count,
            supplemental_run=supplemental_run,
            completed_replacements=completed_replacements,
            designated_spares=designated_spares,
        )


__all__ = ["CocRunOption", "CocWorkflow"]
