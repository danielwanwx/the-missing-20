"""Versioned, repository-local prompts for the Milestone 4 agent stages."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar


class PromptLoadError(ValueError):
    """A frozen prompt asset is missing or was changed without a version bump."""


@dataclass(frozen=True, slots=True)
class PromptSet:
    """The exact prompt text and digest used by one harness invocation."""

    version: str
    investigator: str
    synthesis: str
    evaluator: str
    digest: str

    VERSION: ClassVar[str] = "agent-v5"
    _EXPECTED_DIGESTS: ClassVar[dict[str, str]] = {
        "investigator.md": "78774f1d7ea1c5b982d3b1e6a2a7ca5749a21ad8377fe2b3109df54e4e8043ff",
        "synthesis.md": "e0591583ca775190cd25161cda13fe3c33c24cc45da1519ca108962dec0e8511",
        "evaluator.md": "893bde10424b896e659060118d4db6bb5113eba6204fced1a7544b8e24c09893",
    }

    @classmethod
    def load(cls, repository_root: Path | None = None) -> PromptSet:
        """Load only the checked-in ``agent-v5`` prompt assets.

        Prompt changes are an explicit promotion boundary.  A changed or missing
        file therefore fails closed instead of silently producing a trace whose
        version describes different instructions than the executed prompt.
        """

        root = repository_root or Path(__file__).resolve().parents[3]
        prompt_root = (root / "fixtures/prompts" / cls.VERSION).resolve()
        expected_root = (root / "fixtures/prompts" / cls.VERSION).resolve()
        if prompt_root != expected_root:
            raise PromptLoadError("prompt root is outside the frozen repository path")

        texts: dict[str, str] = {}
        for name, expected_digest in cls._EXPECTED_DIGESTS.items():
            path = prompt_root / name
            if not path.is_file() or not path.is_relative_to(prompt_root):
                raise PromptLoadError(f"missing prompt asset: {cls.VERSION}/{name}")
            try:
                raw = path.read_bytes()
            except OSError as exc:
                raise PromptLoadError(f"cannot read prompt asset: {name}") from exc
            digest = hashlib.sha256(raw).hexdigest()
            if digest != expected_digest:
                raise PromptLoadError(f"prompt asset digest changed: {cls.VERSION}/{name}")
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise PromptLoadError(f"prompt asset is not UTF-8: {name}") from exc
            if not text.strip():
                raise PromptLoadError(f"prompt asset is empty: {cls.VERSION}/{name}")
            texts[name] = text

        digest = hashlib.sha256(
            json.dumps(
                [(name, cls._EXPECTED_DIGESTS[name]) for name in cls._EXPECTED_DIGESTS],
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        return cls(
            version=cls.VERSION,
            investigator=texts["investigator.md"],
            synthesis=texts["synthesis.md"],
            evaluator=texts["evaluator.md"],
            digest=digest,
        )
