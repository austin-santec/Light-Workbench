"""Immutable accepted-reading history for a persisted hardware run.

Only readings accepted by the operator are represented here.  Temporary
measurements and support-log events are deliberately separate from this model
so a future database repository can use these records as its source of truth.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Iterable, Mapping
from uuid import uuid4

from .models import MeasurementRecord


@dataclass(frozen=True)
class MeasurementAttempt:
    """One immutable, two-wavelength reading accepted with Write IL."""

    attempt_id: str
    channel: int
    attempt_number: int
    loss_1310_db: float
    loss_1550_db: float
    physical_port: int | None = None
    accepted_at_utc: str = ""
    operator_initials: str = ""
    write_context: str = "initial"
    replaces_attempt_id: str | None = None
    reference_snapshot: dict | None = None
    run_id: str = ""

    def __post_init__(self):
        if not str(self.attempt_id).strip():
            raise ValueError("A measurement attempt ID is required.")
        if int(self.channel) <= 0 or int(self.attempt_number) <= 0:
            raise ValueError("Measurement channel and attempt number must be positive.")
        float(self.loss_1310_db)
        float(self.loss_1550_db)

    @property
    def is_legacy(self) -> bool:
        return self.write_context == "legacy_import"

    def as_dict(self) -> dict[str, object]:
        """Return the stable JSON/database DTO shape."""
        return {
            "attempt_id": str(self.attempt_id),
            "run_id": str(self.run_id or ""),
            "channel": int(self.channel),
            "physical_port": self.physical_port,
            "attempt_number": int(self.attempt_number),
            "loss_1310_db": float(self.loss_1310_db),
            "loss_1550_db": float(self.loss_1550_db),
            "accepted_at_utc": str(self.accepted_at_utc or ""),
            "operator_initials": str(self.operator_initials or ""),
            "write_context": str(self.write_context or "initial"),
            "replaces_attempt_id": self.replaces_attempt_id,
            "reference_snapshot": dict(self.reference_snapshot)
            if isinstance(self.reference_snapshot, Mapping)
            else None,
        }

    @classmethod
    def from_mapping(cls, values: Mapping[str, object], *, fallback_id: str = ""):
        """Load current records and the older in-memory attempt shape."""
        if not isinstance(values, Mapping):
            raise ValueError("Measurement attempt must be an object.")
        channel = int(values["channel"])
        attempt_number = int(values.get("attempt_number", 1))
        attempt_id = str(values.get("attempt_id") or fallback_id or uuid4().hex)
        timestamp = values.get("accepted_at_utc", values.get("timestamp", ""))
        context = values.get("write_context")
        if not context:
            context = "retest" if values.get("retest") else "initial"
        return cls(
            attempt_id=attempt_id,
            run_id=str(values.get("run_id") or ""),
            channel=channel,
            physical_port=(
                int(values["physical_port"])
                if values.get("physical_port") not in (None, "")
                else None
            ),
            attempt_number=attempt_number,
            loss_1310_db=float(values["loss_1310_db"]),
            loss_1550_db=float(values["loss_1550_db"]),
            accepted_at_utc=str(timestamp or ""),
            operator_initials=str(
                values.get("operator_initials", values.get("operator", "")) or ""
            ),
            write_context=str(context),
            replaces_attempt_id=(
                str(values["replaces_attempt_id"])
                if values.get("replaces_attempt_id")
                else None
            ),
            reference_snapshot=(
                dict(values["reference_snapshot"])
                if isinstance(values.get("reference_snapshot"), Mapping)
                else None
            ),
        )


def _legacy_id(run_id: str, record: MeasurementRecord, index: int) -> str:
    """Create a repeatable ID for a measurement imported from a legacy run."""
    source = json.dumps(
        {
            "run_id": run_id,
            "index": index,
            "channel": record.channel,
            "physical_port": record.physical_port,
            "loss_1310_db": record.loss_1310,
            "loss_1550_db": record.loss_1550,
        },
        sort_keys=True,
    ).encode("utf-8")
    return "legacy-" + hashlib.sha256(source).hexdigest()[:32]


def legacy_attempts_for_measurements(
    measurements: Iterable[MeasurementRecord], *, run_id: str = ""
) -> list[MeasurementAttempt]:
    """Represent latest-only legacy rows as unknown-metadata attempt 1 records."""
    return [
        MeasurementAttempt(
            attempt_id=_legacy_id(run_id, record, index),
            run_id=run_id,
            channel=record.channel,
            physical_port=record.physical_port,
            attempt_number=1,
            loss_1310_db=record.loss_1310,
            loss_1550_db=record.loss_1550,
            write_context="legacy_import",
            reference_snapshot=(
                dict(record.reference_snapshot)
                if isinstance(record.reference_snapshot, Mapping)
                else None
            ),
        )
        for index, record in enumerate(measurements)
    ]


def normalise_attempts(
    values: Iterable[MeasurementAttempt | Mapping[str, object]] | None,
    measurements: Iterable[MeasurementRecord],
    *,
    run_id: str = "",
) -> list[MeasurementAttempt]:
    """Load history while filling missing legacy rows without duplication."""
    attempts: list[MeasurementAttempt] = []
    for index, value in enumerate(values or []):
        if isinstance(value, MeasurementAttempt):
            attempt = value
        else:
            attempt = MeasurementAttempt.from_mapping(
                value,
                fallback_id="legacy-%s" % hashlib.sha256(
                    ("%s:%d" % (run_id, index)).encode("utf-8")
                ).hexdigest()[:32],
            )
        if not attempt.run_id and run_id:
            attempt = MeasurementAttempt(
                **{**attempt.as_dict(), "run_id": run_id}
            )
        attempts.append(attempt)

    known_channels = {attempt.channel for attempt in attempts}
    for attempt in legacy_attempts_for_measurements(measurements, run_id=run_id):
        if attempt.channel not in known_channels:
            attempts.append(attempt)

    by_channel: dict[int, set[int]] = {}
    by_id: dict[str, MeasurementAttempt] = {}
    for attempt in attempts:
        if attempt.attempt_id in by_id:
            raise ValueError("Duplicate measurement attempt ID: %s" % attempt.attempt_id)
        by_id[attempt.attempt_id] = attempt
        numbers = by_channel.setdefault(attempt.channel, set())
        if attempt.attempt_number in numbers:
            raise ValueError(
                "Duplicate measurement attempt %d for channel %d."
                % (attempt.attempt_number, attempt.channel)
            )
        numbers.add(attempt.attempt_number)
    for attempt in attempts:
        if attempt.replaces_attempt_id:
            prior = by_id.get(attempt.replaces_attempt_id)
            if prior is None:
                raise ValueError(
                    "Measurement attempt %s references a missing prior attempt."
                    % attempt.attempt_id
                )
            if prior.channel != attempt.channel:
                raise ValueError(
                    "Measurement attempt replacement links must stay on one channel."
                )
    return attempts


def latest_attempt_for_channel(
    attempts: Iterable[MeasurementAttempt], channel: int
) -> MeasurementAttempt | None:
    """Return the highest-numbered accepted attempt for one channel."""
    matching = [attempt for attempt in attempts if attempt.channel == int(channel)]
    return max(matching, key=lambda attempt: attempt.attempt_number, default=None)


def new_measurement_attempt(
    record: MeasurementRecord,
    *,
    prior: MeasurementAttempt | None = None,
    operator_initials: str = "",
    write_context: str = "initial",
    run_id: str = "",
    accepted_at_utc: str | None = None,
) -> MeasurementAttempt:
    """Create the next accepted attempt for a completed two-wavelength record."""
    if prior is not None:
        write_context = "retest"
    return MeasurementAttempt(
        attempt_id=uuid4().hex,
        run_id=run_id,
        channel=record.channel,
        physical_port=record.physical_port,
        attempt_number=(prior.attempt_number + 1) if prior else 1,
        loss_1310_db=record.loss_1310,
        loss_1550_db=record.loss_1550,
        accepted_at_utc=accepted_at_utc
        or datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        operator_initials=operator_initials,
        write_context=write_context,
        replaces_attempt_id=prior.attempt_id if prior else None,
        reference_snapshot=(
            dict(record.reference_snapshot)
            if isinstance(record.reference_snapshot, Mapping)
            else None
        ),
    )


__all__ = [
    "MeasurementAttempt",
    "latest_attempt_for_channel",
    "legacy_attempts_for_measurements",
    "new_measurement_attempt",
    "normalise_attempts",
]
