"""Deterministic retrieval over the checked-in synthetic knowledge corpus."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from the_missing_20.ports.knowledge import KnowledgeRecord, KnowledgeRepository


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9_]+", value.lower()) if len(token) > 1}


def _frontmatter(path: Path) -> tuple[dict[str, str], str]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if len(lines) < 3 or lines[0].strip() != "---":
        raise ValueError(f"knowledge file lacks frontmatter: {path.name}")
    end = next((index for index, line in enumerate(lines[1:], 1) if line.strip() == "---"), None)
    if end is None:
        raise ValueError(f"knowledge file has unterminated frontmatter: {path.name}")
    fields: dict[str, str] = {}
    for line in lines[1:end]:
        key, separator, value = line.partition(":")
        if not separator or not key.strip() or not value.strip():
            raise ValueError(f"invalid knowledge frontmatter in {path.name}")
        fields[key.strip()] = value.strip()
    body = "\n".join(lines[end + 1 :]).strip()
    return fields, body


class LocalKnowledgeRepository(KnowledgeRepository):
    """Read-only local corpus with immutable manifest and stable ranking."""

    def __init__(self, corpus_root: Path) -> None:
        self.corpus_root = corpus_root.resolve()
        manifest_path = self.corpus_root / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("schema_version") != "knowledge-manifest/v1":
            raise ValueError("unsupported knowledge manifest")
        self.version = str(manifest["corpus_version"])
        records: list[KnowledgeRecord] = []
        manifest_rows = manifest.get("records")
        if not isinstance(manifest_rows, list):
            raise ValueError("knowledge manifest records must be a list")
        for row in manifest_rows:
            if not isinstance(row, dict):
                raise ValueError("knowledge manifest record must be an object")
            relative_path = Path(str(row["path"]))
            if relative_path.is_absolute() or ".." in relative_path.parts:
                raise ValueError("knowledge manifest path must be repository relative")
            path = self.corpus_root.parent.parent / relative_path
            if not path.is_file() or not path.resolve().is_relative_to(
                self.corpus_root.parent.parent.resolve()
            ):
                raise ValueError("knowledge manifest path must exist inside repository")
            if hashlib.sha256(path.read_bytes()).hexdigest() != row["content_sha256"]:
                raise ValueError(f"knowledge digest mismatch: {relative_path.as_posix()}")
            fields, body = _frontmatter(path)
            expected = {
                "knowledge_id": str(row["knowledge_id"]),
                "version": str(row["version"]),
                "title": str(row["title"]),
                "allowed_use": str(row["allowed_use"]),
            }
            if any(fields.get(key) != value for key, value in expected.items()):
                raise ValueError(f"knowledge metadata mismatch: {relative_path.as_posix()}")
            records.append(
                KnowledgeRecord(
                    knowledge_id=expected["knowledge_id"],
                    version=expected["version"],
                    title=expected["title"],
                    allowed_use=expected["allowed_use"],
                    excerpt=body,
                    content_digest=str(row["content_sha256"]),
                )
            )
        self._records = tuple(sorted(records, key=lambda item: item.knowledge_id))
        computed_manifest = [
            {
                "knowledge_id": item.knowledge_id,
                "version": item.version,
                "title": item.title,
                "allowed_use": item.allowed_use,
                "path": f"fixtures/knowledge/{item.knowledge_id}.md",
                "content_sha256": item.content_digest,
            }
            for item in self._records
        ]
        self.manifest_digest = _digest(computed_manifest)
        if manifest.get("corpus_digest") != self.manifest_digest:
            raise ValueError("knowledge corpus digest mismatch")

    @property
    def records(self) -> tuple[KnowledgeRecord, ...]:
        return self._records

    def get(self, knowledge_id: str, version: str) -> KnowledgeRecord | None:
        if version != self.version:
            return None
        return next((item for item in self._records if item.knowledge_id == knowledge_id), None)

    def search(self, query: str, version: str) -> tuple[KnowledgeRecord, ...]:
        if version != self.version:
            raise ValueError("knowledge corpus version is not available")
        query_tokens = _tokens(query)
        ranked: list[tuple[int, KnowledgeRecord]] = []
        for record in self._records:
            score = len(query_tokens & _tokens(f"{record.title} {record.excerpt}"))
            if score:
                ranked.append((score, record))
        ranked.sort(key=lambda item: (-item[0], item[1].knowledge_id))
        return tuple(item[1] for item in ranked)
