"""Semantic change detector for polled external-system evidence.

Polling is transport; it is not activity.  This adapter converts only a new
provider-owned semantic sequence into a dashboard event and suppresses the
initial snapshot plus repeated reads of unchanged records.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from threading import Lock
from typing import Any


class ExternalSourceChangeDetector:
    """Track the last observed semantic sequence for each external source."""

    def __init__(self) -> None:
        self._last_sequences: dict[str, int] = {}
        self._last_records: dict[str, dict[str, str]] = {}
        self._lock = Lock()

    @staticmethod
    def _record_versions(projection: Mapping[str, Any]) -> dict[str, str]:
        raw_records = projection.get("documents") or projection.get("sources") or []
        versions: dict[str, str] = {}
        if not isinstance(raw_records, list):
            return versions
        for record in raw_records:
            if not isinstance(record, Mapping):
                continue
            record_id = str(record.get("name") or record.get("record_id") or "").strip()
            if not record_id:
                continue
            semantic = {
                key: value
                for key, value in record.items()
                if key not in {"occurred_at", "received_at", "changed_at"}
            }
            versions[record_id] = json.dumps(
                semantic, sort_keys=True, separators=(",", ":"), default=str
            )
        return versions

    def observe(self, source_id: str, projection: Mapping[str, Any]) -> dict[str, object] | None:
        sequence = int(projection.get("sequence") or 0)
        if sequence < 1:
            return None
        current_records = self._record_versions(projection)
        with self._lock:
            previous = self._last_sequences.get(source_id)
            previous_records = self._last_records.get(source_id)
            self._last_sequences[source_id] = max(sequence, previous or 0)
            self._last_records[source_id] = current_records
        # Sequence one is the initial read. A first observer that sees a later
        # version still emits it because the provider changed earlier in this
        # process (for example during a fresh agent evidence read).
        if (previous is None and sequence == 1) or (previous is not None and sequence <= previous):
            return None

        if previous_records is None:
            record_ids = sorted(current_records)
        else:
            record_ids = sorted(
                record_id
                for record_id in set(previous_records) | set(current_records)
                if previous_records.get(record_id) != current_records.get(record_id)
            )
        return {
            "source_id": source_id,
            "source_sequence": sequence,
            "status": str(projection.get("status") or "UNKNOWN"),
            "changed_at": str(projection.get("changed_at") or ""),
            "record_ids": record_ids,
            "change_count": len(record_ids),
        }


__all__ = ["ExternalSourceChangeDetector"]
