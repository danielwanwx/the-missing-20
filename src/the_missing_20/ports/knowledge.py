"""Versioned, read-only knowledge retrieval port."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class KnowledgeRecord:
    knowledge_id: str
    version: str
    title: str
    allowed_use: str
    excerpt: str
    content_digest: str


class KnowledgeRepository(Protocol):
    """Read-only interface exposed to the agent tool factory."""

    version: str

    def search(self, query: str, version: str) -> tuple[KnowledgeRecord, ...]:
        """Return stable, version-checked lexical matches."""

    def get(self, knowledge_id: str, version: str) -> KnowledgeRecord | None:
        """Return one exact versioned record, if present."""
