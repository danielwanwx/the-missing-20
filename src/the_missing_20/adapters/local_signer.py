"""HMAC signer used only by the deterministic local milestone."""

from __future__ import annotations

import hashlib
import hmac


class LocalSigner:
    def __init__(self, signing_key: bytes) -> None:
        if not signing_key:
            raise ValueError("signing key cannot be empty")
        self._signing_key = signing_key

    def sign(self, payload: str) -> str:
        return hmac.new(self._signing_key, payload.encode(), hashlib.sha256).hexdigest()

    def verify(self, payload: str, signature: str) -> bool:
        return hmac.compare_digest(self.sign(payload), signature)
