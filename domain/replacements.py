"""Replacement-port recommendations and manual replacement history."""

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4


@dataclass(frozen=True)
class ReplacementReading:
    """A measured physical port with both wavelength losses."""

    port: int
    loss_1310: float
    loss_1550: float

    @property
    def worst_loss(self):
        return max(self.loss_1310, self.loss_1550)


REPLACEMENT_RECORDED = "replacement_recorded"
REPLACEMENT_VOIDED = "replacement_voided"


def _utc_timestamp():
    """Return an unambiguous UTC timestamp for replacement history."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def new_replacement_event(
    current_port,
    replacement_port,
    reason,
    operator,
    *,
    reason_details="",
    previous_record_id=None,
    root_port=None,
    source_run_number=None,
    main_board_serial="",
    switch_serial="",
    record_id=None,
    recorded_at_utc=None,
):
    """Create one append-only event for a manually completed replacement."""
    try:
        current_port = int(current_port)
        replacement_port = int(replacement_port)
    except (TypeError, ValueError):
        raise ValueError("Replacement ports must be whole numbers.")
    if current_port < 1 or replacement_port < 1:
        raise ValueError("Replacement ports must be positive numbers.")
    if current_port == replacement_port:
        raise ValueError("Current Port and Replacement Port must be different.")
    reason = str(reason or "").strip()
    operator = str(operator or "").strip()
    if not reason:
        raise ValueError("A reason is required for a replacement record.")
    if not operator:
        raise ValueError("An operator is required for a replacement record.")
    if root_port is None:
        root_port = current_port
    try:
        root_port = int(root_port)
    except (TypeError, ValueError):
        raise ValueError("The original port must be a whole number.")
    event = {
        "event_id": str(record_id or uuid4()),
        "event_type": REPLACEMENT_RECORDED,
        "root_port": root_port,
        "current_port": current_port,
        "replacement_port": replacement_port,
        "reason": reason,
        "reason_details": str(reason_details or "").strip(),
        "operator": operator,
        "recorded_at_utc": (
            _utc_timestamp() if recorded_at_utc is None else str(recorded_at_utc)
        ),
    }
    if previous_record_id:
        event["previous_record_id"] = str(previous_record_id)
    if source_run_number not in (None, ""):
        try:
            event["source_run_number"] = int(source_run_number)
        except (TypeError, ValueError):
            pass
    if str(main_board_serial or "").strip():
        event["main_board_serial_at_recording"] = str(main_board_serial).strip()
    if str(switch_serial or "").strip():
        event["switch_serial_at_recording"] = str(switch_serial).strip()
    return event


def new_replacement_void_event(record_id, operator, reason):
    """Create an append-only event that voids an earlier record."""
    operator = str(operator or "").strip()
    reason = str(reason or "").strip()
    if not operator:
        raise ValueError("An operator is required to void a replacement record.")
    if not reason:
        raise ValueError("A reason is required to void a replacement record.")
    return {
        "event_id": str(uuid4()),
        "event_type": REPLACEMENT_VOIDED,
        "target_record_id": str(record_id),
        "reason": reason,
        "operator": operator,
        "recorded_at_utc": _utc_timestamp(),
    }


def normalise_replacement_history(events):
    """Validate history events while preserving their audit fields."""
    normalized = []
    seen_ids = set()
    for index, event in enumerate(events or [], start=1):
        if not isinstance(event, dict):
            raise ValueError("Replacement history event %d is not a record." % index)
        event_type = str(event.get("event_type") or REPLACEMENT_RECORDED)
        event_id = str(event.get("event_id") or "").strip()
        if not event_id:
            event_id = "legacy-replacement-%d" % index
        if event_id in seen_ids:
            raise ValueError("Replacement history contains duplicate event IDs.")
        seen_ids.add(event_id)
        if event_type == REPLACEMENT_RECORDED:
            try:
                current_port = int(event.get("current_port"))
                replacement_port = int(event.get("replacement_port"))
            except (TypeError, ValueError):
                raise ValueError("Replacement history contains invalid ports.")
            if current_port < 1 or replacement_port < 1:
                raise ValueError("Replacement history ports must be positive.")
            if current_port == replacement_port:
                raise ValueError("A replacement event cannot use the same port twice.")
            normalized_event = dict(event)
            normalized_event.update(
                {
                    "event_id": event_id,
                    "event_type": REPLACEMENT_RECORDED,
                    "current_port": current_port,
                    "replacement_port": replacement_port,
                    "root_port": int(event.get("root_port") or current_port),
                    "reason": str(event.get("reason") or "Not recorded"),
                    "reason_details": str(event.get("reason_details") or ""),
                    "operator": str(event.get("operator") or "Not recorded"),
                    "recorded_at_utc": str(event.get("recorded_at_utc") or ""),
                }
            )
            if event.get("previous_record_id"):
                normalized_event["previous_record_id"] = str(
                    event["previous_record_id"]
                )
            normalized.append(normalized_event)
        elif event_type == REPLACEMENT_VOIDED:
            target = str(event.get("target_record_id") or "").strip()
            if not target:
                raise ValueError("A void event must identify its target record.")
            normalized.append(
                {
                    **event,
                    "event_id": event_id,
                    "event_type": REPLACEMENT_VOIDED,
                    "target_record_id": target,
                    "reason": str(event.get("reason") or "Not recorded"),
                    "operator": str(event.get("operator") or "Not recorded"),
                    "recorded_at_utc": str(event.get("recorded_at_utc") or ""),
                }
            )
        else:
            raise ValueError("Unsupported replacement history event type: %s" % event_type)
    return normalized


def legacy_replacement_history(records):
    """Represent old two-port records as imported history events."""
    history = []
    for index, record in enumerate(records or [], start=1):
        try:
            current_port = int(record.get("current_port"))
            replacement_port = int(record.get("replacement_port"))
        except (AttributeError, TypeError, ValueError):
            continue
        if current_port < 1 or replacement_port < 1 or current_port == replacement_port:
            continue
        history.append(
            new_replacement_event(
                current_port,
                replacement_port,
                "Not recorded (legacy replacement)",
                "Not recorded",
                record_id="legacy-replacement-%d" % index,
                recorded_at_utc="",
            )
        )
    return history


def effective_replacements(history, *, include_audit_fields=True):
    """Return the active two-port projection derived from append-only history."""
    history = normalise_replacement_history(history)
    records = {}
    superseded = set()
    voided = set()
    for event in history:
        if event["event_type"] == REPLACEMENT_RECORDED:
            previous_id = event.get("previous_record_id")
            if previous_id:
                superseded.add(str(previous_id))
            records[event["event_id"]] = event
        elif event["event_type"] == REPLACEMENT_VOIDED:
            voided.add(event["target_record_id"])
    active = []
    for event_id, event in records.items():
        if event_id in superseded or event_id in voided:
            continue
        active.append(
            {
                **event,
                "current_port": int(event.get("root_port") or event["current_port"]),
                "replacement_port": int(event["replacement_port"]),
            }
        )
    active = sorted(
        active, key=lambda item: (item["current_port"], item["replacement_port"])
    )
    if include_audit_fields:
        return active
    return [
        {
            "current_port": item["current_port"],
            "replacement_port": item["replacement_port"],
        }
        for item in active
    ]


def parse_extra_readings(value: str) -> list[ReplacementReading]:
    """Parse one spare-port reading per line: port, 1310 loss, 1550 loss."""
    readings = []
    seen_ports = set()
    for line_number, line in enumerate(value.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        parts = [part.strip() for part in line.replace(";", ",").split(",")]
        if len(parts) != 3:
            raise ValueError(
                "Line %d must contain port, 1310 nm loss, and 1550 nm loss."
                % line_number
            )
        try:
            port = int(parts[0])
            loss_1310 = float(parts[1])
            loss_1550 = float(parts[2])
        except ValueError:
            raise ValueError("Line %d contains a non-numeric value." % line_number)
        if port < 1:
            raise ValueError("Line %d has an invalid physical port." % line_number)
        if port in seen_ports:
            raise ValueError("Physical port %d is listed more than once." % port)
        seen_ports.add(port)
        readings.append(ReplacementReading(port, loss_1310, loss_1550))
    return readings


def _production_reading(record, wavelengths=(1310, 1550)):
    return ReplacementReading(
        record.physical_port if record.physical_port is not None else record.channel,
        record.loss_for(wavelengths[0]),
        record.loss_for(wavelengths[1]),
    )


def recommendation_category(recommendation, warning_limit):
    """Return required for any over-limit current wavelength, otherwise optional."""
    category = recommendation.get("category")
    if category in ("required", "optional"):
        return category
    current_1310 = recommendation.get("current_loss_1310_db")
    current_1550 = recommendation.get("current_loss_1550_db")
    if current_1310 is not None and current_1550 is not None:
        is_over_limit = current_1310 > warning_limit or current_1550 > warning_limit
    else:
        is_over_limit = recommendation.get("current_worst_loss_db", 0) > warning_limit
    return "required" if is_over_limit else "optional"


def analyze_replacements(
    production_records,
    extra_readings,
    designed_channel_count,
    warning_limit,
    minimum_improvement=0.05,
    bottom_spare_count=2,
    *,
    fail_limit=None,
    model="",
    too_good_limit=None,
    wavelengths=(1310, 1550),
):
    """Recommend worthwhile one-to-one replacements and designated spares.

    Candidate replacements must improve the target's worst wavelength by at
    least ``minimum_improvement`` and remain at or below ``warning_limit`` at
    both wavelengths. After recommendations are allocated, the displaced
    production ports join the unused extras and the combined pool is ranked
    best-first for designated-spare selection. Designated spares do not need
    to be within the warning limit because they are emergency-use backups.
    """
    if designed_channel_count < 1:
        raise ValueError("Designed channel count must be at least 1.")
    if warning_limit < -100 or warning_limit > 100:
        raise ValueError("Warning limit is outside the supported range.")
    if minimum_improvement < 0:
        raise ValueError("Minimum improvement cannot be negative.")
    if bottom_spare_count < 0:
        raise ValueError("Designated spare count cannot be negative.")
    if fail_limit is None:
        fail_limit = warning_limit
    if fail_limit < -100 or fail_limit > 100:
        raise ValueError("Fail limit is outside the supported range.")
    optimization_limit = warning_limit

    production = {
        record.channel: _production_reading(record, wavelengths)
        for record in production_records
        if 1 <= record.channel <= designed_channel_count
    }
    missing_channels = [
        channel
        for channel in range(1, designed_channel_count + 1)
        if channel not in production
    ]
    extras = {reading.port: reading for reading in extra_readings}
    production_ports = {reading.port for reading in production.values()}
    overlapping_ports = sorted(production_ports.intersection(extras))
    if overlapping_ports:
        raise ValueError(
            "Extra physical port(s) already used by production readings: %s."
            % ", ".join(str(port) for port in overlapping_ports)
        )

    result = {
        "applicable": bool(extras),
        "status": "Performed" if extras else "Not applicable - no extra physical ports",
        "designed_channel_count": designed_channel_count,
        "extra_ports": sorted(extras),
        "warning_limit_db": float(warning_limit),
        "optimization_limit_db": float(optimization_limit),
        "fail_limit_db": float(fail_limit),
        "model": model,
        "wavelengths_nm": tuple(int(value) for value in wavelengths),
        "too_good_below_db": too_good_limit,
        "minimum_improvement_db": float(minimum_improvement),
        "bottom_spare_count": int(bottom_spare_count),
        "missing_channels": missing_channels,
        "recommendations": [],
        "bottom_spares": [],
        "remaining_extras": [],
    }
    if not extras:
        return result

    available = dict(extras)
    displaced_production = []
    targets = sorted(
        production.items(),
        key=lambda item: item[1].worst_loss,
        reverse=True,
    )
    for channel, current in targets:
        # Only optimize ports above the model's optimization threshold. For
        # OSX-100 this is the fail limit, so no warning-based replacements are
        # produced.
        if model and current.worst_loss <= optimization_limit:
            continue
        candidates = [
            candidate
            for candidate in available.values()
            if candidate.loss_1310 <= optimization_limit
            and candidate.loss_1550 <= optimization_limit
            and current.worst_loss - candidate.worst_loss >= minimum_improvement
        ]
        if not candidates:
            continue
        candidate = min(candidates, key=lambda reading: reading.worst_loss)
        improvement = current.worst_loss - candidate.worst_loss
        result["recommendations"].append(
            {
                "logical_channel": channel,
                "category": recommendation_category(
                    {
                        "current_loss_1310_db": current.loss_1310,
                        "current_loss_1550_db": current.loss_1550,
                    },
                    fail_limit,
                ),
                "current_physical_port": current.port,
                "current_loss_1310_db": current.loss_1310,
                "current_loss_1550_db": current.loss_1550,
                "current_worst_loss_db": current.worst_loss,
                "candidate_physical_port": candidate.port,
                "candidate_loss_1310_db": candidate.loss_1310,
                "candidate_loss_1550_db": candidate.loss_1550,
                "candidate_worst_loss_db": candidate.worst_loss,
                "improvement_db": improvement,
            }
        )
        del available[candidate.port]
        displaced_production.append(current)

    # A production port made available by a replacement is now a valid spare.
    # Keep it out of the replacement candidate pool above so each recommendation
    # remains a one-to-one swap from an originally measured extra port.
    spare_pool = dict(available)
    for reading in displaced_production:
        spare_pool.setdefault(reading.port, reading)

    remaining = sorted(spare_pool.values(), key=lambda reading: reading.worst_loss)
    result["remaining_extras"] = [reading.port for reading in remaining]
    result["bottom_spares"] = [
        {
            "physical_port": reading.port,
            "loss_1310_db": reading.loss_1310,
            "loss_1550_db": reading.loss_1550,
            "worst_loss_db": reading.worst_loss,
            "within_warning_limit": reading.worst_loss <= optimization_limit,
            "within_optimization_limit": reading.worst_loss <= optimization_limit,
            "too_good": (
                too_good_limit is not None and reading.worst_loss < too_good_limit
            ),
        }
        for reading in remaining[:bottom_spare_count]
    ]
    return result


def normalise_completed_replacements(records):
    """Validate and normalize current-port to replacement-port records.

    The former record schema also stored a logical channel. Continue accepting
    it when loading older run JSON, but normalize it to the two-port schema.
    """
    normalized = []
    current_ports = set()
    replacement_ports = set()
    for index, record in enumerate(records or [], start=1):
        if not isinstance(record, dict):
            raise ValueError("Completed replacement %d is not a record." % index)
        try:
            current_port = int(
                record.get("current_port", record.get("original_physical_port"))
            )
            replacement_port = int(
                record.get("replacement_port", record.get("replacement_physical_port"))
            )
        except (KeyError, TypeError, ValueError):
            raise ValueError("Completed replacement %d contains invalid ports." % index)
        if current_port < 1 or replacement_port < 1:
            raise ValueError("Completed replacement ports must be positive numbers.")
        if current_port in current_ports:
            raise ValueError(
                "Current Port %d is recorded more than once." % current_port
            )
        if replacement_port in replacement_ports:
            raise ValueError(
                "Replacement Port %d is recorded more than once."
                % replacement_port
            )
        current_ports.add(current_port)
        replacement_ports.add(replacement_port)
        normalized.append(
            {
                "current_port": current_port,
                "replacement_port": replacement_port,
            }
        )
    return normalized


def completed_replacement_metadata(records):
    """Convert completed replacement records into readable CSV metadata."""
    records = normalise_completed_replacements(records)
    metadata = {
        "Completed replacements": str(len(records)) if records else "None recorded"
    }
    for index, record in enumerate(records, start=1):
        metadata["Completed replacement %d" % index] = (
            "Current Port %d -> Replacement Port %d"
            % (record["current_port"], record["replacement_port"])
        )
    return metadata


def replacement_metadata(result: dict) -> dict[str, str]:
    """Convert analysis results into readable CSV metadata rows."""
    recommendations = result["recommendations"]
    required_recommendations = [
        recommendation
        for recommendation in recommendations
        if recommendation_category(recommendation, result["warning_limit_db"])
        == "required"
    ]
    optional_recommendations = [
        recommendation
        for recommendation in recommendations
        if recommendation not in required_recommendations
    ]
    metadata = {
        "Replacement analysis": result["status"],
        "Replacement model": result.get("model", "") or "Legacy",
        "Designed channel count": str(result["designed_channel_count"]),
        "Replacement candidate ports": ", ".join(
            str(port) for port in result["extra_ports"]
        ) or "None",
        "Replacement warning limit dB": "%.4f" % result["warning_limit_db"],
        "Replacement fail limit dB": "%.4f" % result.get("fail_limit_db", result["warning_limit_db"]),
        "Replacement minimum improvement dB": "%.4f"
        % result["minimum_improvement_db"],
        "Required replacements": str(len(required_recommendations)),
        "Optional Replacements": str(len(optional_recommendations)),
    }
    if result["missing_channels"]:
        metadata["Replacement missing production channels"] = ", ".join(
            str(channel) for channel in result["missing_channels"]
        )
    if recommendations:
        for category, categorized in (
            ("Required", required_recommendations),
            ("Optional", optional_recommendations),
        ):
            for index, recommendation in enumerate(categorized, start=1):
                metadata["%s replacement recommendation %d" % (category, index)] = (
                    "Logical %d (physical %d, 1310 %.4f dB, 1550 %.4f dB) -> "
                    "Physical %d (1310 %.4f dB, 1550 %.4f dB); improvement %.4f dB"
                    % (
                        recommendation["logical_channel"],
                        recommendation["current_physical_port"],
                        recommendation["current_loss_1310_db"],
                        recommendation["current_loss_1550_db"],
                        recommendation["candidate_physical_port"],
                        recommendation["candidate_loss_1310_db"],
                        recommendation["candidate_loss_1550_db"],
                        recommendation["improvement_db"],
                    )
                )

        for index, recommendation in enumerate(recommendations, start=1):
            category_label = recommendation_category(
                recommendation, result["warning_limit_db"]
            ).title()
            metadata["Replacement recommendation %d" % index] = category_label + (
                "Logical %d (physical %d, 1310 %.4f dB, 1550 %.4f dB) -> "
                "Physical %d (1310 %.4f dB, 1550 %.4f dB); improvement %.4f dB"
                % (
                    recommendation["logical_channel"],
                    recommendation["current_physical_port"],
                    recommendation["current_loss_1310_db"],
                    recommendation["current_loss_1550_db"],
                    recommendation["candidate_physical_port"],
                    recommendation["candidate_loss_1310_db"],
                    recommendation["candidate_loss_1550_db"],
                    recommendation["improvement_db"],
                )
            )
    else:
        metadata["Replacement recommendations"] = "None"

    if result["bottom_spares"]:
        for index, spare in enumerate(result["bottom_spares"], start=1):
            metadata["Recommended designated spare %d" % index] = (
                "Physical %d; worst loss %.4f dB%s"
                % (
                    spare["physical_port"],
                    spare["worst_loss_db"],
                    "" if spare["within_warning_limit"] else " (over warning limit)",
                )
            )
            if spare.get("too_good"):
                metadata["Recommended designated spare %d" % index] += " (too-good warning)"
    else:
        metadata["Recommended designated spares"] = "None available"
    return metadata
