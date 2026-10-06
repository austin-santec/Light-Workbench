"""Schema versions and compatibility migrations for persisted payloads."""

from collections.abc import Mapping


CURRENT_RUN_SCHEMA_VERSION = 3
CURRENT_UNIT_SCHEMA_VERSION = 3


def _version(payload: Mapping[str, object]) -> int:
    """Read a legacy-compatible integer schema version."""
    try:
        return int(payload.get("schema_version", 0))
    except (TypeError, ValueError):
        raise ValueError("Persisted data contains an invalid schema version.")


def migrate_run_payload(payload: Mapping[str, object]) -> dict:
    """Return a current run payload while accepting older JSON layouts."""
    if not isinstance(payload, Mapping):
        raise ValueError("Run JSON must contain an object at its root.")
    version = _version(payload)
    if version > CURRENT_RUN_SCHEMA_VERSION:
        raise ValueError(
            "Run JSON schema version %d is newer than this application supports."
            % version
        )

    migrated = dict(payload)
    migrated.setdefault("metadata", {})
    migrated.setdefault("measurements", [])
    migrated.setdefault("switch_test_sessions", [])
    migrated.setdefault("criteria", None)
    migrated.setdefault("reference_snapshots", [])
    migrated["schema_version"] = CURRENT_RUN_SCHEMA_VERSION
    return migrated


def migrate_unit_payload(payload: Mapping[str, object]) -> dict:
    """Return a current unit payload while accepting legacy unit JSON."""
    if not isinstance(payload, Mapping):
        raise ValueError("Unit JSON must contain an object at its root.")
    version = _version(payload)
    if version > CURRENT_UNIT_SCHEMA_VERSION:
        raise ValueError(
            "Unit JSON schema version %d is newer than this application supports."
            % version
        )

    migrated = dict(payload)
    migrated.setdefault("unit_metadata", {})
    migrated.setdefault("completed_replacements", [])
    migrated.setdefault("replacement_history", None)
    migrated.setdefault("designated_spares", [])
    migrated.setdefault("runs", [])
    migrated["schema_version"] = CURRENT_UNIT_SCHEMA_VERSION
    return migrated


__all__ = [
    "CURRENT_RUN_SCHEMA_VERSION",
    "CURRENT_UNIT_SCHEMA_VERSION",
    "migrate_run_payload",
    "migrate_unit_payload",
]
