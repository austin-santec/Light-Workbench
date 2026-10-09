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
    loss_1310_db: float | None
    loss_1550_db: float | None
    physical_port: int | None = None
    accepted_at_utc: str = ""
    operator_initials: str = ""
    write_context: str = "initial"
    replaces_attempt_id: str | None = None
    reference_snapshot: dict | None = None
    run_id: str = ""
    wavelength_mode: str = "SM"
    losses_by_wavelength: dict[int, float] | None = None
    measurement_classification: str = "native"
    opm_wavelengths_nm: tuple[int, int] = (1310, 1550)
    source_wavelengths_nm: tuple[int, int] = (1310, 1550)
    source_ids: tuple[int, int] = (0, 1)

    def __post_init__(self):
        if not str(self.attempt_id).strip():
            raise ValueError("A measurement attempt ID is required.")
        if int(self.channel) <= 0 or int(self.attempt_number) <= 0:
            raise ValueError("Measurement channel and attempt number must be positive.")
        losses = {
            int(wavelength): float(value)
            for wavelength, value in (self.losses_by_wavelength or {}).items()
        }
        if not losses:
            if self.loss_1310_db is None or self.loss_1550_db is None:
                raise ValueError("Both configured wavelength losses are required.")
            losses = {
                int(self.opm_wavelengths_nm[0]): float(self.loss_1310_db),
                int(self.opm_wavelengths_nm[1]): float(self.loss_1550_db),
            }
        object.__setattr__(self, "losses_by_wavelength", losses)

    @property
    def is_legacy(self) -> bool:
        return self.write_context == "legacy_import"

    def as_dict(self) -> dict[str, object]:
        """Return the stable JSON/database DTO shape."""
        values = {
            "attempt_id": str(self.attempt_id),
            "run_id": str(self.run_id or ""),
            "channel": int(self.channel),
            "physical_port": self.physical_port,
            "attempt_number": int(self.attempt_number),
            "wavelength_mode": str(self.wavelength_mode),
            "losses_by_wavelength": {
                str(wavelength): value
                for wavelength, value in self.losses_by_wavelength.items()
            },
            "measurement_classification": str(self.measurement_classification),
            "opm_wavelengths_nm": list(self.opm_wavelengths_nm),
            "source_wavelengths_nm": list(self.source_wavelengths_nm),
            "source_ids": list(self.source_ids),
            "accepted_at_utc": str(self.accepted_at_utc or ""),
            "operator_initials": str(self.operator_initials or ""),
            "write_context": str(self.write_context or "initial"),
            "replaces_attempt_id": self.replaces_attempt_id,
            "reference_snapshot": dict(self.reference_snapshot)
            if isinstance(self.reference_snapshot, Mapping)
            else None,
        }
        if self.wavelength_mode == "SM":
            values["loss_1310_db"] = float(self.losses_by_wavelength[1310])
            values["loss_1550_db"] = float(self.losses_by_wavelength[1550])
        return values

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
        mode = str(values.get("wavelength_mode") or "SM").upper()
        configured = values.get("opm_wavelengths_nm")
        if not isinstance(configured, (list, tuple)) or len(configured) != 2:
            configured = (1310, 1550) if mode == "SM" else (850, 1300)
        raw_losses = values.get("losses_by_wavelength")
        if isinstance(raw_losses, Mapping):
            losses = {int(key): float(value) for key, value in raw_losses.items()}
        else:
            losses = {
                1310: float(values["loss_1310_db"]),
                1550: float(values["loss_1550_db"]),
            }
        source_wavelengths = values.get("source_wavelengths_nm", (1310, 1550))
        source_ids = values.get("source_ids", (0, 1))
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
            loss_1310_db=losses.get(1310),
            loss_1550_db=losses.get(1550),
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
            wavelength_mode=mode,
            losses_by_wavelength=losses,
            measurement_classification=str(
                values.get("measurement_classification") or "native"
            ),
            opm_wavelengths_nm=tuple(int(value) for value in configured),
            source_wavelengths_nm=tuple(int(value) for value in source_wavelengths),
            source_ids=tuple(int(value) for value in source_ids),
        )


def _legacy_id(run_id: str, record: MeasurementRecord, index: int) -> str:
    """Create a repeatable ID for a measurement imported from a legacy run."""
    source = json.dumps(
        {
            "run_id": run_id,
            "index": index,
            "channel": record.channel,
            "physical_port": record.physical_port,
            "losses_by_wavelength": record.losses_by_wavelength,
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
            wavelength_mode=record.wavelength_mode,
            losses_by_wavelength=dict(record.losses_by_wavelength),
            measurement_classification=record.measurement_classification,
            opm_wavelengths_nm=record.opm_wavelengths_nm,
            source_wavelengths_nm=record.source_wavelengths_nm,
            source_ids=record.source_ids,
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
            attempt = MeasurementAttempt.from_mapping(
                {**attempt.as_dict(), "run_id": run_id}
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
        wavelength_mode=record.wavelength_mode,
        losses_by_wavelength=dict(record.losses_by_wavelength),
        measurement_classification=record.measurement_classification,
        opm_wavelengths_nm=record.opm_wavelengths_nm,
        source_wavelengths_nm=record.source_wavelengths_nm,
        source_ids=record.source_ids,
    )


__all__ = [
    "MeasurementAttempt",
    "latest_attempt_for_channel",
    "legacy_attempts_for_measurements",
    "new_measurement_attempt",
    "normalise_attempts",
]
