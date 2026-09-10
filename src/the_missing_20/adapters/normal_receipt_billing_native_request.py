"""Pure binding for one validated native Purchase Invoice insert request.

This module does not call a transport, journal, model, or ERP.  It turns an
already-admitted native mapper document into the exact immutable body that a
later journal may bind to an intent before approval.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, cast

from the_missing_20.adapters.normal_receipt_billing_preview import (
    BillingPreview,
    SyntheticBillingBasis,
    validate_billing_preview,
    validate_native_purchase_invoice,
)

INSERT_PATH = "/api/resource/Purchase%20Invoice"


def _canonical(value: object) -> object:
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("native request mapping keys must be strings")
            result[key] = _canonical(item)
        return result
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("native request values must be finite")
        return value
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    raise ValueError(f"unsupported native request value: {type(value).__name__}")


def _mapping(value: Mapping[str, object], label: str) -> dict[str, object]:
    canonical = _canonical(value)
    if not isinstance(canonical, dict):  # pragma: no cover - Mapping guarantees a mapping result
        raise ValueError(f"{label} must be a mapping")
    return canonical


def _frozen(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _frozen(item) for key, item in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_frozen(item) for item in value)
    return value


def _digest(value: object) -> str:
    encoded = json.dumps(_canonical(value), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _digest_text(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"{label} must be a SHA-256 digest")
    try:
        int(value, 16)
    except ValueError:
        raise ValueError(f"{label} must be a SHA-256 digest") from None
    return value


def _require_ready_preview(
    preview: BillingPreview,
    basis: SyntheticBillingBasis,
    *,
    label: str,
) -> None:
    if (
        preview.status != "READY"
        or preview.read_only is not True
        or preview.write_allowed is not False
        or preview.reasons
        or preview.bill_digest != basis.bill_digest
    ):
        raise ValueError(f"native request binding requires an admitted READY {label}")


@dataclass(frozen=True, slots=True)
class NativeInsertRequest:
    """An immutable exact body for the only later insert endpoint."""

    method: str
    path: str
    body: Mapping[str, object]
    bill_digest: str
    body_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if self.method != "POST":
            raise ValueError("native insert request method must be POST")
        if self.path != INSERT_PATH:
            raise ValueError("native insert request path is not allowlisted")
        body = _mapping(self.body, "native insert request body")
        object.__setattr__(self, "body", cast(Mapping[str, Any], _frozen(body)))
        object.__setattr__(self, "bill_digest", _digest_text(self.bill_digest, "bill_digest"))
        object.__setattr__(self, "body_digest", _digest(body))

    def record(self) -> dict[str, object]:
        return {
            "method": self.method,
            "path": self.path,
            "body": _canonical(self.body),
            "bill_digest": self.bill_digest,
            "body_digest": self.body_digest,
        }


def bind_native_insert_request(
    basis: SyntheticBillingBasis,
    *,
    purchase_order: Mapping[str, Any],
    purchase_receipt: Mapping[str, Any],
    mapper_document: Mapping[str, Any],
    related_documents_read: Mapping[str, Any],
    preview: BillingPreview,
) -> NativeInsertRequest:
    """Bind only a currently re-admitted READY mapper to disclosed bill fields."""

    if not isinstance(basis, SyntheticBillingBasis):
        raise TypeError("native request binding requires SyntheticBillingBasis")
    if not isinstance(preview, BillingPreview):
        raise TypeError("native request binding requires BillingPreview")
    _require_ready_preview(preview, basis, label="detached preview")
    current_preview = validate_billing_preview(
        basis,
        purchase_order=purchase_order,
        purchase_receipt=purchase_receipt,
        mapped_invoice=mapper_document,
        related_documents_read=related_documents_read,
    )
    _require_ready_preview(current_preview, basis, label="current source preview")
    if current_preview.source_digest != preview.source_digest:
        raise ValueError("native request binding source digest does not match current source")
    if current_preview.bill_digest != preview.bill_digest:
        raise ValueError("native request binding bill digest does not match current source")
    if current_preview.exact_ids != preview.exact_ids:
        raise ValueError("native request binding exact IDs do not match current source")
    validate_native_purchase_invoice(
        basis,
        purchase_order=purchase_order,
        purchase_receipt=purchase_receipt,
        document=mapper_document,
        state="MAPPED",
    )
    body = _mapping(mapper_document, "native mapper document")
    body["bill_no"] = basis.bill_reference
    body["bill_date"] = basis.bill_date
    validate_native_purchase_invoice(
        basis,
        purchase_order=purchase_order,
        purchase_receipt=purchase_receipt,
        document=body,
        state="MAPPED",
        expected_bill_reference=basis.bill_reference,
        expected_bill_date=basis.bill_date,
    )
    return NativeInsertRequest(
        method="POST",
        path=INSERT_PATH,
        body=body,
        bill_digest=basis.bill_digest,
    )
