"""Durable JSONL writing, redaction, rotation, and retention for support logs."""

import gzip
import json
import os
import re
from collections import deque
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Mapping

from config.app_config import (
    SUPPORT_LOG_COMPRESSION_AFTER_DAYS,
    SUPPORT_LOG_MAX_FILE_BYTES,
    SUPPORT_LOG_MAX_TOTAL_BYTES,
    SUPPORT_LOG_MEMORY_CAPACITY,
    SUPPORT_LOG_RETENTION_DAYS,
)


LOG_NAME_PATTERN = re.compile(
    r"^light-workbench-(\d{4}-\d{2}-\d{2})(?:-part(\d{2,}))?\.jsonl(?:\.gz)?$"
)
RAW_RESPONSE_LIMIT = 1024
DETAIL_LIMIT = 4096
PROHIBITED_KEY_PARTS = (
    "password",
    "token",
    "credential",
    "clipboard",
    "free_form_note",
    "environment",
    "native_handle",
)


def redact_path(value: object, user_profile: Path | None = None) -> str:
    """Replace a user-profile prefix in a path or message when present."""
    text = str(value or "")
    profile = str((user_profile or Path.home()).resolve())
    variants = {profile, profile.replace("\\", "/")}
    for candidate in sorted(variants, key=len, reverse=True):
        if candidate:
            text = re.sub(re.escape(candidate), "%USERPROFILE%", text, flags=re.I)
    return text


def sanitize_event_payload(
    payload: Mapping[str, object],
    *,
    user_profile: Path | None = None,
) -> dict[str, object]:
    """Return a bounded, JSON-safe copy of an allowlisted event payload."""

    def sanitize(key: str, value: object):
        lowered = key.lower()
        if any(part in lowered for part in PROHIBITED_KEY_PARTS):
            return None
        if isinstance(value, (str, Path)):
            result = redact_path(value, user_profile)
            limit = RAW_RESPONSE_LIMIT if "response" in lowered else DETAIL_LIMIT
            return result[:limit]
        if isinstance(value, bool) or value is None:
            return value
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, Mapping):
            return {
                str(child_key): sanitized
                for child_key, child_value in value.items()
                if not any(
                    part in str(child_key).lower()
                    for part in PROHIBITED_KEY_PARTS
                )
                if (sanitized := sanitize(str(child_key), child_value)) is not None
            }
        if isinstance(value, (list, tuple)):
            return [sanitize(key, item) for item in value[:100]]
        # Unknown objects may expose native handles, addresses, or arbitrary
        # representations. Only the explicitly supported JSON-safe types are
        # allowed into support logs.
        return None

    return {
        str(key): sanitized
        for key, value in payload.items()
        if not any(part in str(key).lower() for part in PROHIBITED_KEY_PARTS)
        if (sanitized := sanitize(str(key), value)) is not None
    }


class SupportLogWriter:
    """Write managed daily files and degrade safely if disk I/O is unavailable."""

    def __init__(
        self,
        preferred_root: str | Path,
        fallback_root: str | Path,
        *,
        now: Callable[[], datetime] | None = None,
        max_file_bytes: int = SUPPORT_LOG_MAX_FILE_BYTES,
        retention_days: int | None = SUPPORT_LOG_RETENTION_DAYS,
        compression_after_days: int = SUPPORT_LOG_COMPRESSION_AFTER_DAYS,
        max_total_bytes: int = SUPPORT_LOG_MAX_TOTAL_BYTES,
        memory_capacity: int = SUPPORT_LOG_MEMORY_CAPACITY,
    ):
        self.preferred_root = Path(preferred_root)
        self.fallback_root = Path(fallback_root)
        self.now = now or (lambda: datetime.now().astimezone())
        self.max_file_bytes = int(max_file_bytes)
        self.retention_days = (
            None if retention_days is None else int(retention_days)
        )
        self.compression_after_days = int(compression_after_days)
        self.max_total_bytes = int(max_total_bytes)
        self.memory_events = deque(maxlen=max(1, int(memory_capacity)))
        self.active_root: Path | None = None
        self.active_path: Path | None = None
        self.fallback_active = False
        self.last_error = ""
        self._active_date: date | None = None
        self._closed = False
        self._select_root()
        if self.active_root is not None:
            self.active_path = self._latest_log_for_date(self.now().date())
            self._run_maintenance()

    @property
    def healthy(self) -> bool:
        return self.active_root is not None and not self.fallback_active

    @property
    def degraded(self) -> bool:
        return not self.healthy

    def _select_root(self) -> None:
        errors = []
        roots = ((self.preferred_root, False), (self.fallback_root, True))
        seen = set()
        for root, fallback in roots:
            try:
                resolved = root.resolve()
            except OSError:
                resolved = root
            if resolved in seen:
                continue
            seen.add(resolved)
            try:
                root.mkdir(parents=True, exist_ok=True)
                probe = root / ".support-log-write-test.tmp"
                with probe.open("a", encoding="utf-8"):
                    pass
                probe.unlink(missing_ok=True)
                self.active_root = root
                self.fallback_active = fallback
                self.last_error = "; ".join(errors)
                return
            except Exception as error:
                errors.append("%s: %s" % (redact_path(root), error))
        self.active_root = None
        self.fallback_active = True
        self.last_error = "; ".join(errors) or "No writable support-log directory."

    def write(self, payload: Mapping[str, object]) -> None:
        """Append one sanitized JSON object; never raise into the caller."""
        if self._closed:
            return
        safe_payload = sanitize_event_payload(payload)
        try:
            line = json.dumps(
                safe_payload,
                ensure_ascii=False,
                separators=(",", ":"),
            ) + "\n"
        except Exception as error:
            self.last_error = "Could not serialize support event: %s" % error
            return

        if self.active_root is None:
            self.memory_events.append(safe_payload)
            return
        try:
            current = self.now()
            local_day = current.date()
            encoded_length = len(line.encode("utf-8"))
            path = self._path_for_write(local_day, encoded_length)
            with path.open("a", encoding="utf-8", newline="") as stream:
                stream.write(line)
                stream.flush()
            self.active_path = path
            if self._active_date != local_day:
                self._active_date = local_day
                self._run_maintenance()
        except Exception as error:
            self.last_error = "Support-log write failed: %s" % redact_path(error)
            self.memory_events.append(safe_payload)
            self._switch_to_fallback()

    def _switch_to_fallback(self) -> None:
        if self.fallback_active:
            self.active_root = None
            self.active_path = None
            return
        try:
            self.fallback_root.mkdir(parents=True, exist_ok=True)
            self.active_root = self.fallback_root
            self.active_path = None
            self._active_date = None
            self.fallback_active = True
        except Exception as error:
            self.active_root = None
            self.active_path = None
            self.fallback_active = True
            self.last_error += "; fallback failed: %s" % redact_path(error)

    def _path_for_write(self, local_day: date, encoded_length: int) -> Path:
        day_text = local_day.isoformat()
        candidates = sorted(
            (
                path
                for path in self.active_root.iterdir()
                if self._managed_date(path) == local_day and path.suffix == ".jsonl"
            ),
            key=self._part_number,
        )
        path = candidates[-1] if candidates else self._part_path(day_text, 1)
        try:
            current_size = path.stat().st_size
        except FileNotFoundError:
            current_size = 0
        if current_size and current_size + encoded_length > self.max_file_bytes:
            path = self._part_path(day_text, self._part_number(path) + 1)
        return path

    def _latest_log_for_date(self, local_day: date) -> Path | None:
        candidates = sorted(
            (
                path
                for path in self.active_root.iterdir()
                if self._managed_date(path) == local_day and path.suffix == ".jsonl"
            ),
            key=self._part_number,
        )
        return candidates[-1] if candidates else None

    def _part_path(self, day_text: str, part: int) -> Path:
        suffix = "" if part == 1 else "-part%02d" % part
        return self.active_root / ("light-workbench-%s%s.jsonl" % (day_text, suffix))

    @staticmethod
    def _part_number(path: Path) -> int:
        match = LOG_NAME_PATTERN.match(path.name)
        return int(match.group(2) or 1) if match else 0

    @staticmethod
    def _managed_date(path: Path) -> date | None:
        match = LOG_NAME_PATTERN.match(path.name)
        if not match:
            return None
        try:
            return date.fromisoformat(match.group(1))
        except ValueError:
            return None

    def managed_files(self) -> list[Path]:
        if self.active_root is None or not self.active_root.is_dir():
            return []
        return sorted(
            path
            for path in self.active_root.iterdir()
            if path.is_file() and LOG_NAME_PATTERN.match(path.name)
        )

    @property
    def total_size_bytes(self) -> int:
        """Return the size of all managed logs in the active log directory."""
        total = 0
        for path in self.managed_files():
            try:
                total += path.stat().st_size
            except OSError:
                continue
        return total

    @property
    def over_size_limit(self) -> bool:
        """Indicate that operator archiving/deletion should be considered."""
        return self.total_size_bytes > self.max_total_bytes

    def _run_maintenance(self) -> None:
        """Apply retention and compression only to managed inactive files."""
        if self.active_root is None:
            return
        today = self.now().date()
        active = self.active_path
        try:
            for path in self.managed_files():
                managed_day = self._managed_date(path)
                if managed_day is None or path == active:
                    continue
                age = (today - managed_day).days
                if (
                    self.retention_days is not None
                    and age > self.retention_days
                ):
                    path.unlink(missing_ok=True)
                elif (
                    age > self.compression_after_days
                    and path.suffix == ".jsonl"
                ):
                    self._compress(path)
        except Exception as error:
            self.last_error = "Support-log maintenance failed: %s" % redact_path(error)

    @staticmethod
    def _compress(path: Path) -> None:
        target = path.with_suffix(path.suffix + ".gz")
        temporary = target.with_suffix(target.suffix + ".tmp")
        try:
            with path.open("rb") as source, gzip.open(temporary, "wb") as destination:
                destination.write(source.read())
            os.replace(temporary, target)
            path.unlink()
        finally:
            temporary.unlink(missing_ok=True)

    def flush(self) -> None:
        """Writes are flushed per event; retained for the service contract."""

    def close(self) -> None:
        self._closed = True


__all__ = [
    "DETAIL_LIMIT",
    "LOG_NAME_PATTERN",
    "PROHIBITED_KEY_PARTS",
    "RAW_RESPONSE_LIMIT",
    "SupportLogWriter",
    "redact_path",
    "sanitize_event_payload",
]
