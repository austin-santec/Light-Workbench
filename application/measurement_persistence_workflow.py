"""Atomic persistence workflow for accepted two-wavelength measurements."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from uuid import UUID, uuid4

from application.database_repositories import MeasurementRepository
from domain.database_records import (
    MeasurementRecord,
    MeasurementWriteSpec,
    utc_now,
)


class MeasurementPersistenceWorkflow:
    """Prepare retryable Write IL data and publish it only after commit."""

    def __init__(self, repository: MeasurementRepository) -> None:
        self._repository = repository

    def prepare_measurement(
        self,
        *,
        run_id: int,
        logical_channel: int,
        wavelength_1_nm: int,
        wavelength_1_il_db,
        wavelength_2_nm: int,
        wavelength_2_il_db,
        reference_snapshot: Mapping,
        written_by: str,
        physical_port: int | None = None,
        measurement_uuid: UUID | None = None,
        written_at_utc: datetime | None = None,
    ) -> MeasurementWriteSpec:
        """Create the immutable pending value retained across commit retries."""
        return MeasurementWriteSpec(
            measurement_uuid=measurement_uuid or uuid4(),
            run_id=run_id,
            logical_channel=logical_channel,
            wavelength_1_nm=wavelength_1_nm,
            wavelength_1_il_db=wavelength_1_il_db,
            wavelength_2_nm=wavelength_2_nm,
            wavelength_2_il_db=wavelength_2_il_db,
            reference_snapshot=reference_snapshot,
            written_at_utc=written_at_utc or utc_now(),
            written_by=written_by,
            physical_port=physical_port,
        )

    def commit(
        self,
        pending: MeasurementWriteSpec,
        on_committed: Callable[[MeasurementRecord], None] | None = None,
    ) -> MeasurementRecord:
        """Commit atomically, then notify the caller that acceptance is safe."""
        record = self._repository.append_next(pending)
        if on_committed is not None:
            on_committed(record)
        return record


__all__ = ["MeasurementPersistenceWorkflow"]
