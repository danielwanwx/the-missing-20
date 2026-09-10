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
SUBMIT_PATH = "/api/method/frappe.client.submit"


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


def _required_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is required")
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

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> NativeInsertRequest:
        expected_fields = {"method", "path", "body", "bill_digest", "body_digest"}
        if set(record) != expected_fields:
            raise ValueError("native insert request record fields are invalid")
        method = record["method"]
        path = record["path"]
        body = record["body"]
        bill_digest = record["bill_digest"]
        body_digest = record["body_digest"]
        if (
            not isinstance(method, str)
            or not isinstance(path, str)
            or not isinstance(body, Mapping)
            or not isinstance(bill_digest, str)
            or not isinstance(body_digest, str)
        ):
            raise ValueError("native insert request record values are invalid")
        request = cls(
            method=method,
            path=path,
            body=cast(Mapping[str, object], body),
            bill_digest=bill_digest,
        )
        if request.body_digest != body_digest:
            raise ValueError("native insert request record digest does not match body")
        return request


@dataclass(frozen=True, slots=True)
class NativeDraftAcknowledgement:
    """A complete native draft response tied to one frozen insert body.

    This is structured adapter testimony, not a generic provider-verification
    flag. The caller must obtain it from the one marked insert response and
    validate it against current PO/PR evidence with the factory below.
    """

    insert_body_digest: str
    draft_name: str
    document: Mapping[str, object]
    document_digest: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "insert_body_digest",
            _digest_text(self.insert_body_digest, "insert_body_digest"),
        )
        draft_name = _required_text(self.draft_name, "draft_name")
        document = _mapping(self.document, "native draft acknowledgement document")
        if document.get("name") != draft_name:
            raise ValueError("native draft acknowledgement name does not match document")
        object.__setattr__(self, "draft_name", draft_name)
        object.__setattr__(self, "document", cast(Mapping[str, Any], _frozen(document)))
        object.__setattr__(self, "document_digest", _digest(document))

    def record(self) -> dict[str, object]:
        return {
            "insert_body_digest": self.insert_body_digest,
            "draft_name": self.draft_name,
            "document": _canonical(self.document),
            "document_digest": self.document_digest,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> NativeDraftAcknowledgement:
        expected_fields = {"insert_body_digest", "draft_name", "document", "document_digest"}
        if set(record) != expected_fields:
            raise ValueError("native draft acknowledgement record fields are invalid")
        insert_body_digest = record["insert_body_digest"]
        draft_name = record["draft_name"]
        document = record["document"]
        document_digest = record["document_digest"]
        if (
            not isinstance(insert_body_digest, str)
            or not isinstance(draft_name, str)
            or not isinstance(document, Mapping)
            or not isinstance(document_digest, str)
        ):
            raise ValueError("native draft acknowledgement record values are invalid")
        acknowledgement = cls(
            insert_body_digest=insert_body_digest,
            draft_name=draft_name,
            document=cast(Mapping[str, object], document),
        )
        if acknowledgement.document_digest != document_digest:
            raise ValueError("native draft acknowledgement record digest does not match document")
        return acknowledgement


@dataclass(frozen=True, slots=True)
class NativeSubmitRequest:
    """The one full-document native submit request derived from an acknowledged draft."""

    method: str
    path: str
    body: Mapping[str, object]
    draft_name: str
    body_digest: str = field(init=False)
    document_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if self.method != "POST":
            raise ValueError("native submit request method must be POST")
        if self.path != SUBMIT_PATH:
            raise ValueError("native submit request path is not allowlisted")
        draft_name = _required_text(self.draft_name, "native submit request draft_name")
        body = _mapping(self.body, "native submit request body")
        if set(body) != {"doc"} or not isinstance(body["doc"], Mapping):
            raise ValueError("native submit request body must contain exactly one document")
        document = _mapping(cast(Mapping[str, object], body["doc"]), "native submit document")
        if document.get("name") != draft_name:
            raise ValueError("native submit document name does not match draft_name")
        frozen_body = _frozen({"doc": document})
        object.__setattr__(self, "draft_name", draft_name)
        object.__setattr__(self, "body", cast(Mapping[str, Any], frozen_body))
        object.__setattr__(self, "document_digest", _digest(document))
        object.__setattr__(self, "body_digest", _digest({"doc": document}))

    @classmethod
    def from_draft(cls, draft: NativeDraftAcknowledgement) -> NativeSubmitRequest:
        if not isinstance(draft, NativeDraftAcknowledgement):
            raise TypeError("native submit request requires NativeDraftAcknowledgement")
        return cls(
            method="POST",
            path=SUBMIT_PATH,
            body={"doc": draft.document},
            draft_name=draft.draft_name,
        )

    def record(self) -> dict[str, object]:
        return {
            "method": self.method,
            "path": self.path,
            "body": _canonical(self.body),
            "draft_name": self.draft_name,
            "body_digest": self.body_digest,
            "document_digest": self.document_digest,
        }


@dataclass(frozen=True, slots=True)
class NativeSubmittedReadback:
    """A complete exact-name submitted document tied to the frozen draft document."""

    draft_name: str
    draft_document_digest: str
    document: Mapping[str, object]
    document_digest: str = field(init=False)

    def __post_init__(self) -> None:
        draft_name = _required_text(self.draft_name, "submitted readback draft_name")
        object.__setattr__(
            self,
            "draft_document_digest",
            _digest_text(self.draft_document_digest, "draft_document_digest"),
        )
        document = _mapping(self.document, "native submitted readback document")
        if document.get("name") != draft_name:
            raise ValueError("native submitted readback name does not match draft_name")
        object.__setattr__(self, "draft_name", draft_name)
        object.__setattr__(self, "document", cast(Mapping[str, Any], _frozen(document)))
        object.__setattr__(self, "document_digest", _digest(document))

    def record(self) -> dict[str, object]:
        return {
            "draft_name": self.draft_name,
            "draft_document_digest": self.draft_document_digest,
            "document": _canonical(self.document),
            "document_digest": self.document_digest,
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


def validate_native_draft_acknowledgement(
    basis: SyntheticBillingBasis,
    *,
    purchase_order: Mapping[str, Any],
    purchase_receipt: Mapping[str, Any],
    insert_request: NativeInsertRequest,
    document: Mapping[str, Any],
) -> NativeDraftAcknowledgement:
    """Admit a complete known-name insert response through the shared validator."""

    if not isinstance(basis, SyntheticBillingBasis):
        raise TypeError("native draft acknowledgement requires SyntheticBillingBasis")
    if not isinstance(insert_request, NativeInsertRequest):
        raise TypeError("native draft acknowledgement requires NativeInsertRequest")
    if insert_request.bill_digest != basis.bill_digest:
        raise ValueError("native insert request bill digest does not match the bill basis")
    bound_body = _mapping(insert_request.body, "native insert request body")
    validate_native_purchase_invoice(
        basis,
        purchase_order=purchase_order,
        purchase_receipt=purchase_receipt,
        document=cast(Mapping[str, Any], bound_body),
        state="MAPPED",
        expected_bill_reference=basis.bill_reference,
        expected_bill_date=basis.bill_date,
    )
    draft = _mapping(document, "native draft acknowledgement document")
    name = _required_text(draft.get("name"), "native draft acknowledgement name")
    validate_native_purchase_invoice(
        basis,
        purchase_order=purchase_order,
        purchase_receipt=purchase_receipt,
        document=draft,
        state="DRAFT",
        expected_name=name,
        expected_bill_reference=basis.bill_reference,
        expected_bill_date=basis.bill_date,
    )
    return NativeDraftAcknowledgement(
        insert_body_digest=insert_request.body_digest,
        draft_name=name,
        document=draft,
    )


def validate_native_submitted_readback(
    basis: SyntheticBillingBasis,
    *,
    purchase_order: Mapping[str, Any],
    purchase_receipt: Mapping[str, Any],
    draft: NativeDraftAcknowledgement,
    document: Mapping[str, Any],
) -> NativeSubmittedReadback:
    """Admit an exact known-name submitted document through the shared validator."""

    if not isinstance(basis, SyntheticBillingBasis):
        raise TypeError("native submitted readback requires SyntheticBillingBasis")
    if not isinstance(draft, NativeDraftAcknowledgement):
        raise TypeError("native submitted readback requires NativeDraftAcknowledgement")
    draft_document = _mapping(draft.document, "native draft acknowledgement document")
    validate_native_purchase_invoice(
        basis,
        purchase_order=purchase_order,
        purchase_receipt=purchase_receipt,
        document=cast(Mapping[str, Any], draft_document),
        state="DRAFT",
        expected_name=draft.draft_name,
        expected_bill_reference=basis.bill_reference,
        expected_bill_date=basis.bill_date,
    )
    submitted = _mapping(document, "native submitted readback document")
    validate_native_purchase_invoice(
        basis,
        purchase_order=purchase_order,
        purchase_receipt=purchase_receipt,
        document=submitted,
        state="SUBMITTED",
        expected_name=draft.draft_name,
        expected_bill_reference=basis.bill_reference,
        expected_bill_date=basis.bill_date,
    )
    return NativeSubmittedReadback(
        draft_name=draft.draft_name,
        draft_document_digest=draft.document_digest,
        document=submitted,
    )
