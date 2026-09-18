"""Replacement-port recommendations for completed insertion-loss runs."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ReplacementReading:
    """A measured physical port with both wavelength losses."""

    port: int
    loss_1310: float
    loss_1550: float

    @property
    def worst_loss(self):
        return max(self.loss_1310, self.loss_1550)


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


def _production_reading(record):
    return ReplacementReading(
        record.physical_port if record.physical_port is not None else record.channel,
        record.loss_1310,
        record.loss_1550,
    )


def analyze_replacements(
    production_records,
    extra_readings,
    designed_channel_count,
    warning_limit,
    minimum_improvement=0.05,
    bottom_spare_count=2,
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

    production = {
        record.channel: _production_reading(record)
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
        candidates = [
            candidate
            for candidate in available.values()
            if candidate.loss_1310 <= warning_limit
            and candidate.loss_1550 <= warning_limit
            and current.worst_loss - candidate.worst_loss >= minimum_improvement
        ]
        if not candidates:
            continue
        candidate = min(candidates, key=lambda reading: reading.worst_loss)
        improvement = current.worst_loss - candidate.worst_loss
        result["recommendations"].append(
            {
                "logical_channel": channel,
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
            "within_warning_limit": reading.worst_loss <= warning_limit,
        }
        for reading in remaining[:bottom_spare_count]
    ]
    return result


def replacement_metadata(result: dict) -> dict[str, str]:
    """Convert analysis results into readable CSV metadata rows."""
    metadata = {
        "Replacement analysis": result["status"],
        "Designed channel count": str(result["designed_channel_count"]),
        "Replacement candidate ports": ", ".join(
            str(port) for port in result["extra_ports"]
        ) or "None",
        "Replacement warning limit dB": "%.4f" % result["warning_limit_db"],
        "Replacement minimum improvement dB": "%.4f"
        % result["minimum_improvement_db"],
    }
    if result["missing_channels"]:
        metadata["Replacement missing production channels"] = ", ".join(
            str(channel) for channel in result["missing_channels"]
        )
    if result["recommendations"]:
        for index, recommendation in enumerate(result["recommendations"], start=1):
            metadata["Replacement recommendation %d" % index] = (
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
    else:
        metadata["Recommended designated spares"] = "None available"
    return metadata
