"""Run-local catalog for immutable production-reference snapshots.

References are identified by their immutable snapshot ID when available.  A
content fingerprint is used only for legacy records that predate snapshot IDs,
so old files can still be deduplicated without inventing a new measurement
identity.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import hashlib
import json


def _snapshot_copy(snapshot: Mapping[str, object]) -> dict[str, object]:
    """Return a JSON-safe shallow snapshot copy with independent mappings."""
    return json.loads(json.dumps(dict(snapshot), default=str))


def _snapshot_identity(snapshot: Mapping[str, object]) -> tuple[str, str]:
    """Return the stable identity used to deduplicate one snapshot."""
    snapshot_id = str(snapshot.get("snapshot_id") or "").strip()
    if snapshot_id:
        return ("snapshot_id", snapshot_id)
    canonical = json.dumps(
        dict(snapshot),
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return ("legacy_fingerprint", hashlib.sha256(canonical.encode("utf-8")).hexdigest())


def _snapshot_content(snapshot: Mapping[str, object]) -> str:
    """Return canonical content for detecting duplicate-ID corruption."""
    values = dict(snapshot)
    values.pop("reference_key", None)
    return json.dumps(values, sort_keys=True, separators=(",", ":"), default=str)


@dataclass(frozen=True)
class ReferenceCatalogEntry:
    """One readable run-local label and its immutable snapshot."""

    reference_key: str
    snapshot: dict[str, object]

    def as_dict(self) -> dict[str, object]:
        """Return the persisted catalog entry shape."""
        snapshot = _snapshot_copy(self.snapshot)
        snapshot["reference_key"] = self.reference_key
        return {
            "reference_key": self.reference_key,
            "snapshot": snapshot,
        }


class ReferenceCatalog:
    """Assign and resolve stable ``Ref N`` labels within one run."""

    def __init__(self, entries: Iterable[Mapping[str, object]] | None = None):
        self._entries: list[ReferenceCatalogEntry] = []
        self._by_identity: dict[tuple[str, str], ReferenceCatalogEntry] = {}
        self._by_key: dict[str, ReferenceCatalogEntry] = {}
        for entry in entries or ():
            if not isinstance(entry, Mapping):
                raise ValueError("Reference catalog entries must be objects.")
            snapshot = entry.get("snapshot")
            if not isinstance(snapshot, Mapping):
                snapshot = entry
            key = str(
                entry.get("reference_key")
                or snapshot.get("reference_key")
                or ""
            ).strip()
            self.register(snapshot, preferred_key=key or None)

    def register(
        self,
        snapshot: Mapping[str, object] | None,
        *,
        preferred_key: str | None = None,
    ) -> str | None:
        """Register a snapshot and return its stable run-local label."""
        if not isinstance(snapshot, Mapping) or not snapshot:
            return None
        identity = _snapshot_identity(snapshot)
        existing = self._by_identity.get(identity)
        requested_key = str(
            preferred_key or snapshot.get("reference_key") or ""
        ).strip()
        if existing is not None:
            if _snapshot_content(existing.snapshot) != _snapshot_content(snapshot):
                raise ValueError(
                    "Reference snapshot %s contains conflicting data."
                    % identity[1]
                )
            if requested_key and requested_key != existing.reference_key:
                raise ValueError(
                    "Reference snapshot %s has conflicting labels %s and %s."
                    % (identity[1], existing.reference_key, requested_key)
                )
            return existing.reference_key

        key = requested_key or "Ref %d" % (len(self._entries) + 1)
        other = self._by_key.get(key)
        if other is not None:
            if _snapshot_identity(other.snapshot) != identity:
                raise ValueError(
                    "Reference label %s is assigned to conflicting snapshots." % key
                )
            return key

        stored = _snapshot_copy(snapshot)
        stored["reference_key"] = key
        entry = ReferenceCatalogEntry(key, stored)
        self._entries.append(entry)
        self._by_identity[identity] = entry
        self._by_key[key] = entry
        return key

    def label_for(self, snapshot: Mapping[str, object] | None) -> str | None:
        """Return the existing or newly assigned label for a snapshot."""
        if not isinstance(snapshot, Mapping) or not snapshot:
            return None
        return self.register(snapshot)

    def snapshot_for(self, reference_key: str) -> dict[str, object] | None:
        """Return a copy of the snapshot identified by a run-local label."""
        entry = self._by_key.get(str(reference_key or "").strip())
        return _snapshot_copy(entry.snapshot) if entry is not None else None

    def entries(self) -> tuple[ReferenceCatalogEntry, ...]:
        """Return entries in stable first-use order."""
        return tuple(self._entries)

    def snapshots(self) -> list[dict[str, object]]:
        """Return full snapshots once each, including their reference keys."""
        return [
            _snapshot_copy(entry.snapshot)
            for entry in self._entries
        ]

    def persisted_entries(self) -> list[dict[str, object]]:
        """Return the explicit JSON catalog representation."""
        return [entry.as_dict() for entry in self._entries]


def build_reference_catalog(
    attempts: Iterable[object] | None,
    measurements: Iterable[object] | None,
) -> ReferenceCatalog:
    """Build a catalog from historical attempts followed by current rows.

    Attempts are processed first so references used only by superseded retests
    retain a label when the current table projection no longer contains them.
    """
    catalog = ReferenceCatalog()
    for value in attempts or ():
        snapshot = (
            value.reference_snapshot
            if hasattr(value, "reference_snapshot")
            else value.get("reference_snapshot")
            if isinstance(value, Mapping)
            else None
        )
        if isinstance(snapshot, Mapping):
            catalog.register(snapshot)
    for value in measurements or ():
        snapshot = getattr(value, "reference_snapshot", None)
        if isinstance(snapshot, Mapping):
            catalog.register(snapshot)
    return catalog


__all__ = [
    "ReferenceCatalog",
    "ReferenceCatalogEntry",
    "build_reference_catalog",
]
