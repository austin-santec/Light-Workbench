"""Application workflow for append-only replacement and spare documentation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Mapping

from application.database_repositories import RoutingRepository
from domain.database_records import (
    ChannelMapRecord,
    ReplacementRecord,
    ReplacementSpec,
    SpareEventRecord,
    SpareEventSpec,
    utc_now,
)


@dataclass(frozen=True)
class AssignmentRoutingSnapshot:
    """Current routes plus complete append-only documentation history."""

    assignment_id: int
    channel_map: tuple[ChannelMapRecord, ...]
    replacement_history: tuple[ReplacementRecord, ...]
    spare_history: tuple[SpareEventRecord, ...]
    active_spares: tuple[int, ...]

    @property
    def effective_channel_map(self) -> Mapping[int, int]:
        return MappingProxyType(
            {
                item.logical_channel: item.effective_physical_port
                for item in self.channel_map
            }
        )


class ReplacementPersistenceWorkflow:
    """Document routing changes without commanding or querying switch routes."""

    def __init__(self, repository: RoutingRepository) -> None:
        self._repository = repository

    def load_assignment(self, assignment_id: int) -> AssignmentRoutingSnapshot:
        channel_map, replacements, spare_history, active_spares = (
            self._repository.routing_snapshot_for_assignment(assignment_id)
        )
        return AssignmentRoutingSnapshot(
            assignment_id,
            channel_map,
            replacements,
            spare_history,
            active_spares,
        )

    def record_replacement(
        self,
        *,
        assignment_id: int,
        logical_channel: int,
        previous_physical_port: int,
        replacement_physical_port: int,
        reason: str,
        replaced_by: str,
        related_run_id: int | None = None,
        notes: str | None = None,
        replaced_at_utc: datetime | None = None,
    ) -> ReplacementRecord:
        return self._repository.append(
            ReplacementSpec(
                assignment_id=assignment_id,
                logical_channel=logical_channel,
                previous_physical_port=previous_physical_port,
                replacement_physical_port=replacement_physical_port,
                reason=reason,
                replaced_by=replaced_by,
                replaced_at_utc=replaced_at_utc or utc_now(),
                related_run_id=related_run_id,
                notes=notes,
            )
        )

    def designate_spare(
        self,
        assignment_id: int,
        physical_port: int,
        recorded_by: str,
        *,
        notes: str | None = None,
        recorded_at_utc: datetime | None = None,
    ) -> SpareEventRecord:
        return self._record_spare_event(
            assignment_id,
            physical_port,
            "designated",
            recorded_by,
            notes,
            recorded_at_utc,
        )

    def undesignate_spare(
        self,
        assignment_id: int,
        physical_port: int,
        recorded_by: str,
        *,
        notes: str | None = None,
        recorded_at_utc: datetime | None = None,
    ) -> SpareEventRecord:
        return self._record_spare_event(
            assignment_id,
            physical_port,
            "undesignated",
            recorded_by,
            notes,
            recorded_at_utc,
        )

    def _record_spare_event(
        self,
        assignment_id: int,
        physical_port: int,
        action: str,
        recorded_by: str,
        notes: str | None,
        recorded_at_utc: datetime | None,
    ) -> SpareEventRecord:
        return self._repository.append_event(
            SpareEventSpec(
                assignment_id=assignment_id,
                physical_port=physical_port,
                action=action,
                recorded_by=recorded_by,
                recorded_at_utc=recorded_at_utc or utc_now(),
                notes=notes,
            )
        )


__all__ = ["AssignmentRoutingSnapshot", "ReplacementPersistenceWorkflow"]
