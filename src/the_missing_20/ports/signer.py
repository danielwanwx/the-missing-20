"""Port for local and later KMS-compatible grant signatures."""

from __future__ import annotations

from typing import Protocol


class Signer(Protocol):
    def sign(self, payload: str) -> str: ...

    def verify(self, payload: str, signature: str) -> bool: ...
