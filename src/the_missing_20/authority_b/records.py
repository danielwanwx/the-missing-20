"""Durable immutable Authority-B record helpers."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from the_missing_20.authority_b.models import OperationalDecision, canonical_json

RecordT = TypeVar("RecordT", bound=BaseModel)


class AuthorityBRecordConflict(RuntimeError):
    """A durable Authority-B record was overwritten with different bytes."""


class AuthorityBArtifactStore:
    """Small append-only JSON store used by offline proofs and later UI adapters."""

    def __init__(self, root: Path) -> None:
        self.root = root

    @staticmethod
    def _bytes(record: BaseModel) -> bytes:
        return (canonical_json(record.model_dump(mode="json")) + "\n").encode("utf-8")

    def _path(self, kind: str, case_id: str, case_version: int) -> Path:
        safe_case = "".join(char if char.isalnum() or char in "-_" else "_" for char in case_id)
        if not safe_case:
            raise ValueError("case ID cannot be empty")
        if case_version < 0:
            raise ValueError("case version cannot be negative")
        return self.root / kind / f"{safe_case}-v{case_version}.json"

    def save_decision(self, decision: OperationalDecision) -> Path:
        path = self._path("operational-decisions", decision.case_id, decision.case_version)
        self._save(path, decision)
        return path

    def save(
        self,
        *,
        kind: str,
        case_id: str,
        case_version: int,
        record: RecordT,
    ) -> Path:
        path = self._path(kind, case_id, case_version)
        self._save(path, record)
        return path

    def load(self, path: Path, record_type: type[RecordT]) -> RecordT:
        return record_type.model_validate_json(path.read_bytes())

    def _save(self, path: Path, record: BaseModel) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        encoded = self._bytes(record)
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            try:
                existing = path.read_bytes()
            except OSError as exc:
                raise AuthorityBRecordConflict("existing Authority-B record is unreadable") from exc
            if existing != encoded:
                raise AuthorityBRecordConflict("Authority-B record is immutable") from None
            return
        try:
            with os.fdopen(descriptor, "wb") as handle:
                descriptor = -1
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
        finally:
            if descriptor >= 0:
                os.close(descriptor)


__all__ = ["AuthorityBArtifactStore", "AuthorityBRecordConflict"]
