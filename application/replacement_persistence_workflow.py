"""Application workflow for append-only replacement and spare documentation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Iterable, Mapping, Sequence

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


@dataclass(frozen=True)
class ReplacementRecommendation:
    """One advisory analysis result resolved against the SQL channel map."""

    logical_channel: int
    current_effective_physical_port: int
    proposed_replacement_physical_port: int
    category: str
    improvement_db: float | None
    default_reason: str
    has_measurement_evidence: bool


@dataclass(frozen=True)
class ReplacementEditorModel:
    """Read-only database state and advisory choices presented by Qt."""

    assignment_id: int
    related_run_id: int
    unit_label: str
    switch_label: str
    default_operator: str
    channel_map: tuple[ChannelMapRecord, ...]
    replacement_history: tuple[ReplacementRecord, ...]
    existing_spares: tuple[int, ...]
    recommended_spares: tuple[int, ...]
    measured_physical_ports: tuple[int, ...]
    recommendations: tuple[ReplacementRecommendation, ...]

    def current_effective_port(self, logical_channel: int) -> int:
        for route in self.channel_map:
            if route.logical_channel == int(logical_channel):
                return route.effective_physical_port
        raise ValueError("Logical channel is not in the loaded assignment")


@dataclass(frozen=True)
class ReplacementChangeRequest:
    """Operator-entered replacement facts; database context is deliberately absent."""

    logical_channel: int
    replacement_physical_port: int
    reason: str
    replaced_by: str
    notes: str | None = None


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

    def build_editor_model(
        self,
        *,
        snapshot: AssignmentRoutingSnapshot,
        related_run_id: int,
        recommendations: Iterable[Mapping] = (),
        recommended_spares: Iterable[int] = (),
        measured_physical_ports: Iterable[int] = (),
        default_operator: str = "",
        unit_label: str = "",
        switch_label: str = "",
    ) -> ReplacementEditorModel:
        """Resolve analysis advice against the authoritative effective map."""
        effective = dict(snapshot.effective_channel_map)
        measured = tuple(sorted({int(value) for value in measured_physical_ports}))
        measured_set = set(measured)
        resolved = []
        for item in recommendations:
            logical_channel = int(item["logical_channel"])
            if logical_channel not in effective:
                continue
            category = str(item.get("category") or "optional").strip().lower()
            if category not in {"required", "optional"}:
                category = "optional"
            proposed = int(item["candidate_physical_port"])
            improvement = item.get("improvement_db")
            resolved.append(
                ReplacementRecommendation(
                    logical_channel=logical_channel,
                    current_effective_physical_port=effective[logical_channel],
                    proposed_replacement_physical_port=proposed,
                    category=category,
                    improvement_db=(
                        None if improvement is None else float(improvement)
                    ),
                    default_reason=(
                        "Formal insertion-loss failure"
                        if category == "required"
                        else "Insertion-loss optimization"
                    ),
                    has_measurement_evidence=proposed in measured_set,
                )
            )
        return ReplacementEditorModel(
            assignment_id=snapshot.assignment_id,
            related_run_id=int(related_run_id),
            unit_label=str(unit_label or ""),
            switch_label=str(switch_label or ""),
            default_operator=str(default_operator or "").strip(),
            channel_map=snapshot.channel_map,
            replacement_history=snapshot.replacement_history,
            existing_spares=tuple(sorted(set(snapshot.active_spares))),
            recommended_spares=tuple(
                sorted({int(value) for value in recommended_spares})
            ),
            measured_physical_ports=measured,
            recommendations=tuple(resolved),
        )

    def apply_changes(
        self,
        *,
        assignment_id: int,
        related_run_id: int,
        replacements: Sequence[ReplacementChangeRequest] = (),
        spares_to_designate: Iterable[int] = (),
        spares_to_undesignate: Iterable[int] = (),
        spare_operator: str,
        recorded_at_utc: datetime | None = None,
    ) -> AssignmentRoutingSnapshot:
        """Atomically append approved replacements and explicit spare changes."""
        snapshot = self.load_assignment(assignment_id)
        effective = dict(snapshot.effective_channel_map)
        timestamp = recorded_at_utc or utc_now()
        replacement_specs = []
        for request in replacements:
            logical_channel = int(request.logical_channel)
            if logical_channel not in effective:
                raise ValueError("Replacement logical channel is not in the assignment")
            previous_port = effective[logical_channel]
            replacement_port = int(request.replacement_physical_port)
            replacement_specs.append(
                ReplacementSpec(
                    assignment_id=assignment_id,
                    logical_channel=logical_channel,
                    previous_physical_port=previous_port,
                    replacement_physical_port=replacement_port,
                    reason=request.reason,
                    replaced_by=request.replaced_by,
                    replaced_at_utc=timestamp,
                    related_run_id=related_run_id,
                    notes=request.notes,
                )
            )
            effective[logical_channel] = replacement_port

        designate = {int(value) for value in spares_to_designate}
        undesignate = {int(value) for value in spares_to_undesignate}
        overlap = designate.intersection(undesignate)
        if overlap:
            raise ValueError("A spare port cannot be designated and undesignated together")
        active = set(snapshot.active_spares)
        if designate.intersection(active):
            raise ValueError("An existing designated spare was selected as new")
        if not undesignate.issubset(active):
            raise ValueError("Only existing designated spares can be undesignated")
        spare_specs = tuple(
            SpareEventSpec(
                assignment_id=assignment_id,
                physical_port=port,
                action=action,
                recorded_by=spare_operator,
                recorded_at_utc=timestamp,
                notes="Approved in Manage Port Replacements",
            )
            for action, ports in (
                ("designated", sorted(designate)),
                ("undesignated", sorted(undesignate)),
            )
            for port in ports
        )
        if not replacement_specs and not spare_specs:
            return snapshot
        channel_map, history, spare_history, active_spares = (
            self._repository.apply_routing_changes(
                tuple(replacement_specs), spare_specs
            )
        )
        return AssignmentRoutingSnapshot(
            assignment_id,
            channel_map,
            history,
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


__all__ = [
    "AssignmentRoutingSnapshot",
    "ReplacementChangeRequest",
    "ReplacementEditorModel",
    "ReplacementPersistenceWorkflow",
    "ReplacementRecommendation",
]
