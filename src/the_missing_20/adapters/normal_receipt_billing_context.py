"""Pure same-observation context for normal-receipt billing.

This module deliberately only derives a current read context.  It does not
refresh a journal, claim an attempt, call a transport, or infer ownership from
a business-field search.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, cast

from the_missing_20.adapters.normal_receipt_billing_journal import CommercialSource
from the_missing_20.adapters.normal_receipt_billing_native_request import (
    NativeDraftAcknowledgement,
    NativeInsertRequest,
    bind_native_insert_request,
    validate_native_draft_acknowledgement,
)
from the_missing_20.adapters.normal_receipt_billing_preview import (
    BillingPreview,
    SyntheticBillingBasis,
    validate_billing_preview,
)
from the_missing_20.adapters.normal_receipt_billing_source import NormalReceiptBillingSourceRead


def _canonical(value: object) -> object:
    """Accept only detached strict-JSON audit material."""

    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("source context mapping keys must be strings")
            result[key] = _canonical(item)
        return result
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("source context values must be finite")
        return value
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    raise ValueError(f"unsupported source context value: {type(value).__name__}")


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    result = _canonical(value)
    if not isinstance(result, dict):  # pragma: no cover - Mapping fixes this branch
        raise ValueError(f"{label} must be a mapping")
    return result


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw(item) for item in value]
    return value


def _frozen_mapping(value: object, label: str) -> Mapping[str, Any]:
    return cast(Mapping[str, Any], _freeze(_mapping(value, label)))


def _encoded(value: object) -> str:
    return json.dumps(_canonical(value), sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value: object) -> str:
    return hashlib.sha256(_encoded(value).encode("utf-8")).hexdigest()


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is required")
    return value


@dataclass(frozen=True, slots=True)
class NormalReceiptBillingAudit:
    """Complete raw source and exact-name readback retained outside the fingerprint."""

    source_read: Mapping[str, object]
    direct_known_document: Mapping[str, object] | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_read", _frozen_mapping(self.source_read, "source read"))
        if self.direct_known_document is not None:
            object.__setattr__(
                self,
                "direct_known_document",
                _frozen_mapping(self.direct_known_document, "direct known document"),
            )

    def record(self) -> dict[str, object]:
        return {
            "source_read": _canonical(self.source_read),
            "direct_known_document": _canonical(self.direct_known_document),
        }


@dataclass(frozen=True, slots=True)
class NormalReceiptBillingContext:
    """A pure context result; it grants neither approval nor transport authority."""

    preview: BillingPreview
    source_insert_request: NativeInsertRequest | None
    commercial_source: CommercialSource | None
    audit: NormalReceiptBillingAudit
    hold_reason: str | None

    @property
    def ready(self) -> bool:
        return (
            self.hold_reason is None
            and self.preview.status == "READY"
            and self.preview.read_only is True
            and self.preview.write_allowed is False
            and not self.preview.reasons
            and self.source_insert_request is not None
            and self.commercial_source is not None
        )


def _audit(
    source_read: NormalReceiptBillingSourceRead,
    direct: Mapping[str, object] | None,
) -> NormalReceiptBillingAudit:
    return NormalReceiptBillingAudit(
        source_read={
            "purchase_order": source_read.purchase_order,
            "purchase_receipt": source_read.purchase_receipt,
            "mapped_invoice": source_read.mapped_invoice,
            "related_documents_read": source_read.related_documents_read,
            "evidence_manifest": source_read.evidence_manifest,
            "observed_at": source_read.observed_at,
            "snapshot_digest": source_read.snapshot_digest,
            "preview": source_read.preview.record(),
        },
        direct_known_document=direct,
    )


def _source_inputs(
    audit: NormalReceiptBillingAudit,
) -> tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any], Mapping[str, Any], str, str]:
    raw = cast(dict[str, object], _thaw(audit.source_read))
    return (
        cast(Mapping[str, Any], _mapping(raw["purchase_order"], "purchase order")),
        cast(Mapping[str, Any], _mapping(raw["purchase_receipt"], "purchase receipt")),
        cast(Mapping[str, Any], _mapping(raw["mapped_invoice"], "mapped invoice")),
        cast(
            Mapping[str, Any],
            _mapping(raw["related_documents_read"], "related documents read"),
        ),
        _text(raw["snapshot_digest"], "snapshot digest"),
        _text(raw["observed_at"], "observed_at"),
    )


def _related_is_complete(related: Mapping[str, Any], basis: SyntheticBillingBasis) -> bool:
    expected_scope = {
        "company": basis.company,
        "supplier": basis.supplier,
        "purchase_order": basis.purchase_order,
        "purchase_order_item": basis.purchase_order_item,
        "purchase_receipt": basis.purchase_receipt,
        "purchase_receipt_item": basis.purchase_receipt_item,
    }
    pagination = related.get("pagination")
    coverage = related.get("coverage")
    return (
        related.get("status") == "COMPLETE"
        and related.get("pagination_complete") is True
        and isinstance(pagination, Mapping)
        and pagination.get("complete") is True
        and isinstance(coverage, Mapping)
        and all(
            coverage.get(name) is True
            for name in (
                "receipt_line_invoices",
                "receipt_returns",
                "bill_reference_collisions",
            )
        )
        and related.get("scope") == expected_scope
        and isinstance(related.get("documents"), list)
    )


def _requests_match(stored: NativeInsertRequest, current: NativeInsertRequest) -> bool:
    if (
        stored.method != current.method
        or stored.path != current.path
        or stored.bill_digest != current.bill_digest
    ):
        return False
    old_body = stored.record()["body"]
    new_body = current.record()["body"]
    if old_body == new_body:
        return True
    if not isinstance(old_body, dict) or not isinstance(new_body, dict):  # pragma: no cover
        return False
    if (
        type(old_body.get("set_posting_time")) is not int
        or old_body.get("set_posting_time") != 0
        or type(new_body.get("set_posting_time")) is not int
        or new_body.get("set_posting_time") != 0
        or "posting_time" not in old_body
        or "posting_time" not in new_body
    ):
        return False
    old_projection = dict(old_body)
    new_projection = dict(new_body)
    del old_projection["posting_time"]
    del new_projection["posting_time"]
    return old_projection == new_projection


def _ordered_documents(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError("related documents must be a list")
    return sorted((_canonical(document) for document in value), key=_encoded)


def _commercial_source(
    basis: SyntheticBillingBasis,
    *,
    purchase_order: Mapping[str, Any],
    purchase_receipt: Mapping[str, Any],
    related: Mapping[str, Any],
    snapshot_digest: str,
    observed_at: str,
    audit: NormalReceiptBillingAudit,
) -> CommercialSource:
    pagination = _mapping(related["pagination"], "related pagination")
    related_projection = {
        "status": related["status"],
        "pagination_complete": related["pagination_complete"],
        "pagination": {"complete": pagination["complete"]},
        "scope": related["scope"],
        "coverage": related["coverage"],
        "documents": _ordered_documents(related["documents"]),
    }
    return CommercialSource(
        identity={
            "company": basis.company,
            "supplier": basis.supplier,
            "purchase_order": basis.purchase_order,
            "purchase_order_item": basis.purchase_order_item,
            "purchase_receipt": basis.purchase_receipt,
            "purchase_receipt_item": basis.purchase_receipt_item,
            "item_code": basis.item_code,
        },
        revisions={
            "purchase_order": _text(purchase_order.get("modified"), "PO modified"),
            "purchase_receipt": _text(purchase_receipt.get("modified"), "PR modified"),
            "related_documents": _digest(related_projection),
        },
        decisive_values={
            "quantity": str(basis.quantity),
            "uom": basis.uom,
            "stock_uom": basis.stock_uom,
            "conversion_factor": str(basis.conversion_factor),
            "net_rate": str(basis.net_rate),
            "currency": basis.currency,
            "gross_amount": str(basis.gross_amount),
        },
        audit_snapshot_digest=snapshot_digest,
        observed_at=observed_at,
        audit_evidence=audit.record(),
    )


def _held(
    preview: BillingPreview,
    audit: NormalReceiptBillingAudit,
    reason: str,
) -> NormalReceiptBillingContext:
    return NormalReceiptBillingContext(preview, None, None, audit, reason)


def build_normal_receipt_billing_context(
    basis: SyntheticBillingBasis,
    source_read: NormalReceiptBillingSourceRead,
    *,
    stored_insert_request: NativeInsertRequest | None = None,
    acknowledgement: NativeDraftAcknowledgement | None = None,
    direct_known_document: Mapping[str, object] | None = None,
) -> NormalReceiptBillingContext:
    """Derive one current, read-only context from an immutable source observation.

    Before a known insert acknowledgement, raw complete eligibility is used as-is.
    Afterwards, only one exact acknowledgement-owned Purchase Invoice may be removed
    from a temporary comparison view; all raw evidence remains in ``audit``.
    """

    if not isinstance(basis, SyntheticBillingBasis):
        raise TypeError("source context requires SyntheticBillingBasis")
    if not isinstance(source_read, NormalReceiptBillingSourceRead):
        raise TypeError("source context requires NormalReceiptBillingSourceRead")
    if stored_insert_request is not None and not isinstance(
        stored_insert_request, NativeInsertRequest
    ):
        raise TypeError("source context stored request must be NativeInsertRequest")
    if acknowledgement is not None and not isinstance(acknowledgement, NativeDraftAcknowledgement):
        raise TypeError("source context acknowledgement must be NativeDraftAcknowledgement")

    audit = _audit(source_read, direct_known_document)
    try:
        (
            purchase_order,
            purchase_receipt,
            mapper,
            related,
            snapshot_digest,
            observed_at,
        ) = _source_inputs(audit)
        raw_preview = validate_billing_preview(
            basis,
            purchase_order=purchase_order,
            purchase_receipt=purchase_receipt,
            mapped_invoice=mapper,
            related_documents_read=related,
        )
    except (KeyError, TypeError, ValueError):
        return _held(source_read.preview, audit, "SOURCE_READ_INVALID")

    if acknowledgement is None:
        if direct_known_document is not None:
            return _held(raw_preview, audit, "DIRECT_DRAFT_REQUIRES_ACKNOWLEDGEMENT")
        if raw_preview.status != "READY":
            return _held(raw_preview, audit, "UNFILTERED_PREVIEW_NOT_READY")
        try:
            current = bind_native_insert_request(
                basis,
                purchase_order=purchase_order,
                purchase_receipt=purchase_receipt,
                mapper_document=mapper,
                related_documents_read=related,
                preview=raw_preview,
            )
            if stored_insert_request is not None and not _requests_match(
                stored_insert_request, current
            ):
                return _held(raw_preview, audit, "INSERT_REQUEST_MISMATCH")
            source = _commercial_source(
                basis,
                purchase_order=purchase_order,
                purchase_receipt=purchase_receipt,
                related=related,
                snapshot_digest=snapshot_digest,
                observed_at=observed_at,
                audit=audit,
            )
        except (KeyError, TypeError, ValueError):
            return _held(raw_preview, audit, "SOURCE_BINDING_INVALID")
        return NormalReceiptBillingContext(raw_preview, current, source, audit, None)

    if stored_insert_request is None:
        return _held(raw_preview, audit, "ACKNOWLEDGEMENT_REQUIRES_BOUND_REQUEST")
    if direct_known_document is None:
        return _held(raw_preview, audit, "DIRECT_DRAFT_READ_REQUIRED")
    if not _related_is_complete(related, basis):
        return _held(raw_preview, audit, "RELATED_SOURCE_INCOMPLETE")

    documents = related["documents"]
    assert isinstance(documents, list)  # guarded by _related_is_complete
    matching_indexes = [
        index
        for index, document in enumerate(documents)
        if isinstance(document, Mapping)
        and document.get("doctype") == "Purchase Invoice"
        and document.get("name") == acknowledgement.draft_name
    ]
    if len(matching_indexes) != 1:
        return _held(raw_preview, audit, "ACKNOWLEDGED_DRAFT_NOT_EXACTLY_ONCE")

    try:
        source_document = cast(Mapping[str, Any], documents[matching_indexes[0]])
        direct_document = cast(Mapping[str, Any], _thaw(audit.direct_known_document))
        source_acknowledgement = validate_native_draft_acknowledgement(
            basis,
            purchase_order=purchase_order,
            purchase_receipt=purchase_receipt,
            insert_request=stored_insert_request,
            document=source_document,
        )
        direct_acknowledgement = validate_native_draft_acknowledgement(
            basis,
            purchase_order=purchase_order,
            purchase_receipt=purchase_receipt,
            insert_request=stored_insert_request,
            document=direct_document,
        )
        if (
            acknowledgement.insert_body_digest != stored_insert_request.body_digest
            or source_acknowledgement.draft_name != acknowledgement.draft_name
            or direct_acknowledgement.draft_name != acknowledgement.draft_name
            or source_acknowledgement.document_digest != acknowledgement.document_digest
            or direct_acknowledgement.document_digest != acknowledgement.document_digest
        ):
            return _held(raw_preview, audit, "ACKNOWLEDGED_DRAFT_MISMATCH")
        comparison_related = cast(Mapping[str, Any], _thaw(related))
        comparison_documents = comparison_related["documents"]
        if not isinstance(comparison_documents, list):  # pragma: no cover - guarded above
            return _held(raw_preview, audit, "RELATED_SOURCE_INCOMPLETE")
        del comparison_documents[matching_indexes[0]]
        comparison_preview = validate_billing_preview(
            basis,
            purchase_order=purchase_order,
            purchase_receipt=purchase_receipt,
            mapped_invoice=mapper,
            related_documents_read=comparison_related,
        )
        if comparison_preview.status != "READY":
            return _held(comparison_preview, audit, "COMPARISON_PREVIEW_NOT_READY")
        current = bind_native_insert_request(
            basis,
            purchase_order=purchase_order,
            purchase_receipt=purchase_receipt,
            mapper_document=mapper,
            related_documents_read=comparison_related,
            preview=comparison_preview,
        )
        if not _requests_match(stored_insert_request, current):
            return _held(comparison_preview, audit, "INSERT_REQUEST_MISMATCH")
        source = _commercial_source(
            basis,
            purchase_order=purchase_order,
            purchase_receipt=purchase_receipt,
            related=comparison_related,
            snapshot_digest=snapshot_digest,
            observed_at=observed_at,
            audit=audit,
        )
    except (KeyError, TypeError, ValueError):
        return _held(raw_preview, audit, "ACKNOWLEDGED_DRAFT_INVALID")
    return NormalReceiptBillingContext(comparison_preview, current, source, audit, None)
