"""Application workflow for append-only replacement and spare documentation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Iterable, Mapping, Sequence

from application.database_repositories import RoutingRepository
from domain.database_records import (
    ChannelMapRecord,
    ConfirmedExtraPortRecord,
    ReplacementRecord,
    ReplacementSpec,
    SpareEventRecord,
    SpareEventSpec,
    utc_now,
)


REPLACEMENT_REASON_PLACEHOLDER = "Select reason..."
NORMAL_REPLACEMENT_REASONS = (
    "Dirty/scratched fiber",
    "Issue with terminated boot",
    "Splicing issue",
    "Break in fiber",
    "Unknown cause of high loss",
)
CORRECTION_REASONS = (
    "Correction of previous mapping record",
    "Reversal to previous physical port",
    "Replacement changed again",
    "Other correction",
)


@dataclass(frozen=True)
class AssignmentRoutingSnapshot:
    """Current routes plus complete append-only documentation history."""

    assignment_id: int
    channel_map: tuple[ChannelMapRecord, ...]
    replacement_history: tuple[ReplacementRecord, ...]
    spare_history: tuple[SpareEventRecord, ...]
    active_spares: tuple[int, ...]
    confirmed_extra_ports: tuple[ConfirmedExtraPortRecord, ...] = ()

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
    candidate_loss_1310_db: float | None = None
    candidate_loss_1550_db: float | None = None
    candidate_worst_loss_db: float | None = None
    recommendation_id: int | None = None
    current_loss_1310_db: float | None = None
    current_loss_1550_db: float | None = None
    current_worst_loss_db: float | None = None


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
    source_recommendation_id: int | None = None
    expected_previous_physical_port: int | None = None
    category: str = ""
    improvement: str = ""
    is_correction: bool = False


class ReplacementBatchValidationError(ValueError):
    """A replacement batch is invalid before any database write begins."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        logical_channel: int | None = None,
        expected_previous_physical_port: int | None = None,
        actual_previous_physical_port: int | None = None,
        proposed_replacement_physical_port: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.operator_message = message
        self.logical_channel = logical_channel
        self.expected_previous_physical_port = expected_previous_physical_port
        self.actual_previous_physical_port = actual_previous_physical_port
        self.proposed_replacement_physical_port = (
            proposed_replacement_physical_port
        )


@dataclass(frozen=True)
class ReplacementSavePlan:
    """Immutable routing changes validated against one routing snapshot."""

    snapshot: AssignmentRoutingSnapshot
    replacement_specs: tuple[ReplacementSpec, ...]
    spare_event_specs: tuple[SpareEventSpec, ...]
    request_summary: tuple[tuple[int, int, int], ...]


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
            self._repository.confirmed_extra_ports_for_assignment(assignment_id),
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
        measured = tuple(
            sorted(
                {item.physical_port for item in snapshot.confirmed_extra_ports}
                | {int(value) for value in measured_physical_ports}
            )
        )
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
                    default_reason="",
                    has_measurement_evidence=proposed in measured_set,
                    candidate_loss_1310_db=(
                        None
                        if item.get("candidate_loss_1310_db") is None
                        else float(item["candidate_loss_1310_db"])
                    ),
                    candidate_loss_1550_db=(
                        None
                        if item.get("candidate_loss_1550_db") is None
                        else float(item["candidate_loss_1550_db"])
                    ),
                    candidate_worst_loss_db=(
                        None
                        if item.get("candidate_worst_loss_db") is None
                        else float(item["candidate_worst_loss_db"])
                    ),
                    recommendation_id=(
                        None
                        if item.get("recommendation_id") is None
                        else int(item["recommendation_id"])
                    ),
                    current_loss_1310_db=(
                        None
                        if item.get("current_loss_1310_db") is None
                        else float(item["current_loss_1310_db"])
                    ),
                    current_loss_1550_db=(
                        None
                        if item.get("current_loss_1550_db") is None
                        else float(item["current_loss_1550_db"])
                    ),
                    current_worst_loss_db=(
                        None
                        if item.get("current_worst_loss_db") is None
                        else float(item["current_worst_loss_db"])
                    ),
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
        plan = self.plan_changes(
            assignment_id=assignment_id,
            related_run_id=related_run_id,
            replacements=replacements,
            spares_to_designate=spares_to_designate,
            spares_to_undesignate=spares_to_undesignate,
            spare_operator=spare_operator,
            recorded_at_utc=recorded_at_utc,
        )
        return self.apply_plan(plan)

    def apply_plan(self, plan: ReplacementSavePlan) -> AssignmentRoutingSnapshot:
        """Persist an already planned batch as one atomic routing change."""
        if not plan.replacement_specs and not plan.spare_event_specs:
            return plan.snapshot
        channel_map, history, spare_history, active_spares = (
            self._repository.apply_routing_changes(
                plan.replacement_specs, plan.spare_event_specs
            )
        )
        return AssignmentRoutingSnapshot(
            plan.snapshot.assignment_id,
            channel_map,
            history,
            spare_history,
            active_spares,
            self._repository.confirmed_extra_ports_for_assignment(
                plan.snapshot.assignment_id
            ),
        )

    def plan_changes(
        self,
        *,
        assignment_id: int,
        related_run_id: int,
        replacements: Sequence[ReplacementChangeRequest] = (),
        spares_to_designate: Iterable[int] = (),
        spares_to_undesignate: Iterable[int] = (),
        spare_operator: str,
        recorded_at_utc: datetime | None = None,
    ) -> ReplacementSavePlan:
        """Validate a complete routing batch before repository persistence."""
        snapshot = self.load_assignment(assignment_id)
        effective = dict(snapshot.effective_channel_map)
        timestamp = recorded_at_utc or utc_now()
        replacement_specs = []
        request_summary = []
        seen_logical_channels: set[int] = set()
        seen_replacement_ports: dict[int, int] = {}
        seen_recommendations: set[int] = set()
        confirmed_extra_ports = {
            item.physical_port for item in snapshot.confirmed_extra_ports
        }
        for request in replacements:
            logical_channel = int(request.logical_channel)
            replacement_port = int(request.replacement_physical_port)
            expected_port = request.expected_previous_physical_port
            if expected_port is not None:
                expected_port = int(expected_port)
            if logical_channel in seen_logical_channels:
                raise ReplacementBatchValidationError(
                    "duplicate_logical_channel",
                    "Channel %d is included more than once in the replacement "
                    "save request." % logical_channel,
                    logical_channel=logical_channel,
                    proposed_replacement_physical_port=replacement_port,
                )
            if logical_channel not in effective:
                raise ReplacementBatchValidationError(
                    "logical_channel_not_in_assignment",
                    "Logical channel %d is not in the loaded assignment."
                    % logical_channel,
                    logical_channel=logical_channel,
                    proposed_replacement_physical_port=replacement_port,
                )
            previous_port = effective[logical_channel]
            if expected_port is None:
                expected_port = previous_port
            if expected_port != previous_port:
                raise ReplacementBatchValidationError(
                    "stale_mapping",
                    "Channel %d was expected to use physical port %d, but the "
                    "database now reports port %d. Reload the replacement "
                    "window before continuing."
                    % (logical_channel, expected_port, previous_port),
                    logical_channel=logical_channel,
                    expected_previous_physical_port=expected_port,
                    actual_previous_physical_port=previous_port,
                    proposed_replacement_physical_port=replacement_port,
                )
            if replacement_port <= 0:
                raise ReplacementBatchValidationError(
                    "invalid_replacement_port",
                    "Replacement physical port must be positive.",
                    logical_channel=logical_channel,
                    actual_previous_physical_port=previous_port,
                    proposed_replacement_physical_port=replacement_port,
                )
            if replacement_port == previous_port:
                raise ReplacementBatchValidationError(
                    "replacement_is_current_port",
                    "Channel %d cannot be recorded as %d → %d. Select a "
                    "physical port different from its current effective port."
                    % (logical_channel, previous_port, replacement_port),
                    logical_channel=logical_channel,
                    expected_previous_physical_port=expected_port,
                    actual_previous_physical_port=previous_port,
                    proposed_replacement_physical_port=replacement_port,
                )
            prior_logical = seen_replacement_ports.get(replacement_port)
            if prior_logical is not None:
                raise ReplacementBatchValidationError(
                    "duplicate_replacement_port",
                    "Physical port %d is proposed for more than one logical "
                    "channel (%d and %d)."
                    % (replacement_port, prior_logical, logical_channel),
                    logical_channel=logical_channel,
                    actual_previous_physical_port=previous_port,
                    proposed_replacement_physical_port=replacement_port,
                )
            owner = next(
                (
                    channel
                    for channel, port in effective.items()
                    if channel != logical_channel and port == replacement_port
                ),
                None,
            )
            if owner is not None:
                raise ReplacementBatchValidationError(
                    "replacement_port_in_use",
                    "Replacement physical port %d is already in use by logical "
                    "channel %d." % (replacement_port, owner),
                    logical_channel=logical_channel,
                    actual_previous_physical_port=previous_port,
                    proposed_replacement_physical_port=replacement_port,
                )
            if not request.is_correction and replacement_port not in confirmed_extra_ports:
                raise ReplacementBatchValidationError(
                    "unconfirmed_replacement_port",
                    "Replacement physical port %d has no valid committed extra-port "
                    "measurement for this hardware assignment." % replacement_port,
                    logical_channel=logical_channel,
                    actual_previous_physical_port=previous_port,
                    proposed_replacement_physical_port=replacement_port,
                )
            recommendation_id = request.source_recommendation_id
            if recommendation_id is not None:
                recommendation_id = int(recommendation_id)
                if recommendation_id in seen_recommendations:
                    raise ReplacementBatchValidationError(
                        "duplicate_source_recommendation",
                        "Source replacement recommendation %d was submitted more "
                        "than once." % recommendation_id,
                        logical_channel=logical_channel,
                        actual_previous_physical_port=previous_port,
                        proposed_replacement_physical_port=replacement_port,
                    )
                seen_recommendations.add(recommendation_id)
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
                    source_recommendation_id=recommendation_id,
                    is_correction=bool(request.is_correction),
                )
            )
            seen_logical_channels.add(logical_channel)
            seen_replacement_ports[replacement_port] = logical_channel
            request_summary.append(
                (logical_channel, previous_port, replacement_port)
            )

        designate = {int(value) for value in spares_to_designate}
        undesignate = {int(value) for value in spares_to_undesignate}
        overlap = designate.intersection(undesignate)
        if overlap:
            raise ValueError("A spare port cannot be designated and undesignated together")
        active = set(snapshot.active_spares)
        consumed_spares = {
            int(spec.replacement_physical_port)
            for spec in replacement_specs
            if int(spec.replacement_physical_port) in active
        }
        # A designated spare stops being available as soon as it becomes an
        # effective route. Preserve that state transition as another append-only
        # spare event in the same transaction as the replacement.
        undesignate.update(consumed_spares)
        if designate.intersection(active):
            raise ValueError("An existing designated spare was selected as new")
        if not undesignate.issubset(active):
            raise ValueError("Only existing designated spares can be undesignated")
        unconfirmed_spares = designate.difference(confirmed_extra_ports)
        if unconfirmed_spares:
            raise ValueError(
                "Designated spare ports require valid committed extra-port "
                "measurements: %s"
                % ", ".join(str(value) for value in sorted(unconfirmed_spares))
            )
        mapped_ports = set(effective.values())
        mapped_spares = designate.intersection(mapped_ports)
        if mapped_spares:
            raise ValueError(
                "Mapped physical ports cannot be designated as spares: %s"
                % ", ".join(str(value) for value in sorted(mapped_spares))
            )
        spare_specs = tuple(
            SpareEventSpec(
                assignment_id=assignment_id,
                physical_port=port,
                action=action,
                recorded_by=spare_operator,
                recorded_at_utc=timestamp,
                notes=(
                    "Consumed by recorded replacement"
                    if action == "undesignated" and port in consumed_spares
                    else "Approved in Manage Port Replacements"
                ),
            )
            for action, ports in (
                ("designated", sorted(designate)),
                ("undesignated", sorted(undesignate)),
            )
            for port in ports
        )
        return ReplacementSavePlan(
            snapshot=snapshot,
            replacement_specs=tuple(replacement_specs),
            spare_event_specs=spare_specs,
            request_summary=tuple(request_summary),
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
                source_recommendation_id=None,
                is_correction=False,
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
    "CORRECTION_REASONS",
    "NORMAL_REPLACEMENT_REASONS",
    "REPLACEMENT_REASON_PLACEHOLDER",
    "AssignmentRoutingSnapshot",
    "ReplacementBatchValidationError",
    "ReplacementChangeRequest",
    "ReplacementEditorModel",
    "ReplacementPersistenceWorkflow",
    "ReplacementRecommendation",
    "ReplacementSavePlan",
]
