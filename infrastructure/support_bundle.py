"""Explicit, local-only export of engineering support bundles."""

import hashlib
import json
import os
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Mapping

from domain.support_events import SUPPORT_LOG_SCHEMA_VERSION
from infrastructure.support_log_writer import (
    LOG_NAME_PATTERN,
    redact_path,
    sanitize_event_payload,
)


@dataclass(frozen=True)
class SupportBundleResult:
    path: Path
    included_log_count: int
    included_file_count: int


def _available_destination(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix or ".zip"
    number = 2
    while True:
        candidate = path.with_name("%s-%d%s" % (stem, number, suffix))
        if not candidate.exists():
            return candidate
        number += 1


def _managed_date(path: Path) -> date | None:
    match = LOG_NAME_PATTERN.match(path.name)
    if not match:
        return None
    try:
        return date.fromisoformat(match.group(1))
    except ValueError:
        return None


def select_support_logs(
    log_root: str | Path,
    start_date: date,
    end_date: date,
) -> list[Path]:
    """Return only managed support logs whose local dates are in range."""
    root = Path(log_root)
    if not root.is_dir():
        return []
    return sorted(
        path
        for path in root.iterdir()
        if path.is_file()
        and (managed_date := _managed_date(path)) is not None
        and start_date <= managed_date <= end_date
    )


def export_support_bundle(
    destination: str | Path,
    *,
    log_root: str | Path,
    start_date: date,
    end_date: date,
    application_name: str,
    application_version: str,
    dependency_report: str,
    configuration_summary: Mapping[str, object],
    log_schema_version: int = SUPPORT_LOG_SCHEMA_VERSION,
) -> SupportBundleResult:
    """Create one collision-safe ZIP without including production run data."""
    if end_date < start_date:
        raise ValueError("Support bundle end date cannot be before its start date.")
    output = Path(destination)
    if output.suffix.lower() != ".zip":
        output = output.with_suffix(".zip")
    output.parent.mkdir(parents=True, exist_ok=True)
    output = _available_destination(output)
    logs = select_support_logs(log_root, start_date, end_date)
    temporary = output.with_suffix(output.suffix + ".tmp")
    hashes = {}
    entries = []

    readme = (
        "Light Workbench engineering support bundle\n\n"
        "This bundle contains structured local support logs, a dependency report, "
        "and sanitized configuration. It does not include run CSV/JSON files, COC "
        "workbooks, diagnostic-history exports, clipboard data, passwords, or tokens.\n\n"
        "Logs may contain equipment identifiers, operator initials, routed channels, "
        "optical measurements, references, and calculated insertion loss. They are "
        "editable diagnostic evidence, not an authoritative production record or a "
        "tamper-proof audit trail.\n"
    ).encode("utf-8")
    configuration = json.dumps(
        sanitize_event_payload(configuration_summary),
        indent=2,
        sort_keys=True,
    ).encode("utf-8") + b"\n"
    dependency = redact_path(dependency_report).encode("utf-8")

    def add_bytes(archive, archive_name, content):
        archive.writestr(archive_name, content)
        hashes[archive_name] = hashlib.sha256(content).hexdigest()
        entries.append(archive_name)

    try:
        with zipfile.ZipFile(
            temporary,
            "w",
            compression=zipfile.ZIP_DEFLATED,
        ) as archive:
            for log_path in logs:
                content = log_path.read_bytes()
                add_bytes(archive, "logs/%s" % log_path.name, content)
            add_bytes(archive, "dependency-report.txt", dependency)
            add_bytes(archive, "sanitized-configuration.json", configuration)
            add_bytes(archive, "README.txt", readme)
            manifest = {
                "exported_at_utc": datetime.now(timezone.utc).isoformat(
                    timespec="milliseconds"
                ).replace("+00:00", "Z"),
                "selected_start_date": start_date.isoformat(),
                "selected_end_date": end_date.isoformat(),
                "application_name": application_name,
                "application_version": application_version,
                "log_schema_version": log_schema_version,
                "files": [
                    {"path": name, "sha256": hashes[name]} for name in entries
                ],
                "source_log_root": redact_path(log_root),
            }
            archive.writestr(
                "manifest.json",
                json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
                + b"\n",
            )
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)

    return SupportBundleResult(
        path=output,
        included_log_count=len(logs),
        included_file_count=len(entries) + 1,
    )


__all__ = [
    "SupportBundleResult",
    "export_support_bundle",
    "select_support_logs",
]
