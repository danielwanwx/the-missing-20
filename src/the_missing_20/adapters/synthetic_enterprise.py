"""SQLite-backed synthetic enterprise systems with transactional business effects."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from the_missing_20.domain.enterprise import (
    BusinessEffect,
    EnterpriseActionOutcome,
    EnterpriseInvoiceState,
    EnterpriseMutationResult,
    EnterpriseSnapshot,
    ErpReceipt,
    FailedReceiptMessage,
    Invoice,
    MaterialDocument,
    MessageStatus,
    PurchaseOrderLine,
    ScenarioFixture,
    WarehouseReceipt,
)
from the_missing_20.domain.execution import (
    EffectType,
    ReleaseInvoiceParameters,
    RestartReceiptMessageParameters,
)
from the_missing_20.ports.enterprise_systems import EnterprisePreconditionFailed


class SyntheticEnterprise:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self._create_schema()

    @classmethod
    def seed_from_fixture(cls, database_path: Path, fixture_path: Path) -> SyntheticEnterprise:
        fixture = ScenarioFixture.model_validate_json(fixture_path.read_text(encoding="utf-8"))
        adapter = cls(database_path)
        with adapter._connect() as connection:
            existing = connection.execute("SELECT COUNT(*) FROM purchase_order_lines").fetchone()[0]
            if existing:
                raise ValueError("enterprise database is already seeded")
            connection.execute(
                "INSERT INTO purchase_order_lines VALUES (?, ?, ?, ?)",
                (
                    fixture.purchase_order.purchase_order_id,
                    fixture.purchase_order.line_id,
                    fixture.purchase_order.ordered_quantity,
                    fixture.purchase_order.unit,
                ),
            )
            connection.execute(
                "INSERT INTO warehouse_receipts VALUES (?, ?, ?, ?)",
                (
                    fixture.warehouse_receipt.receipt_id,
                    fixture.warehouse_receipt.purchase_order_id,
                    fixture.warehouse_receipt.line_id,
                    fixture.warehouse_receipt.quantity,
                ),
            )
            message = fixture.failed_message
            connection.execute(
                "INSERT INTO failed_messages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    message.message_id,
                    message.revision,
                    message.purchase_order_id,
                    message.line_id,
                    message.quantity,
                    message.error_code,
                    message.status.value,
                    int(message.retry_eligible),
                    int(message.lock_cleared),
                    message.consumed_by_execution_id,
                ),
            )
            erp = fixture.erp_receipt
            connection.execute(
                "INSERT INTO erp_receipts VALUES (?, ?, ?, ?)",
                (erp.purchase_order_id, erp.line_id, erp.quantity, erp.revision),
            )
            invoice = fixture.invoice
            connection.execute(
                "INSERT INTO invoices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    invoice.invoice_id,
                    invoice.revision,
                    invoice.purchase_order_id,
                    invoice.line_id,
                    invoice.quantity,
                    invoice.state.value,
                    invoice.hold_reason,
                    json.dumps(invoice.other_blocking_holds),
                    invoice.released_by_execution_id,
                ),
            )
        return adapter

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _create_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS purchase_order_lines (
                    purchase_order_id TEXT NOT NULL,
                    line_id TEXT NOT NULL,
                    ordered_quantity INTEGER NOT NULL,
                    unit TEXT NOT NULL,
                    PRIMARY KEY (purchase_order_id, line_id)
                );
                CREATE TABLE IF NOT EXISTS warehouse_receipts (
                    receipt_id TEXT PRIMARY KEY,
                    purchase_order_id TEXT NOT NULL,
                    line_id TEXT NOT NULL,
                    quantity INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS failed_messages (
                    message_id TEXT PRIMARY KEY,
                    revision INTEGER NOT NULL,
                    purchase_order_id TEXT NOT NULL,
                    line_id TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    error_code TEXT NOT NULL,
                    status TEXT NOT NULL,
                    retry_eligible INTEGER NOT NULL,
                    lock_cleared INTEGER NOT NULL,
                    consumed_by_execution_id TEXT
                );
                CREATE TABLE IF NOT EXISTS erp_receipts (
                    purchase_order_id TEXT NOT NULL,
                    line_id TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    revision INTEGER NOT NULL,
                    PRIMARY KEY (purchase_order_id, line_id)
                );
                CREATE TABLE IF NOT EXISTS invoices (
                    invoice_id TEXT PRIMARY KEY,
                    revision INTEGER NOT NULL,
                    purchase_order_id TEXT NOT NULL,
                    line_id TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    hold_reason TEXT,
                    other_blocking_holds_json TEXT NOT NULL,
                    released_by_execution_id TEXT
                );
                CREATE TABLE IF NOT EXISTS material_documents (
                    material_document_id TEXT PRIMARY KEY,
                    source_message_id TEXT NOT NULL UNIQUE,
                    purchase_order_id TEXT NOT NULL,
                    line_id TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    execution_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE
                );
                CREATE TABLE IF NOT EXISTS business_effects (
                    effect_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    trace_id TEXT NOT NULL,
                    execution_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    effect_type TEXT NOT NULL,
                    source_record_id TEXT NOT NULL,
                    result_record_ids_json TEXT NOT NULL,
                    committed_at TEXT NOT NULL
                );
                """
            )

    def read_snapshot(self) -> EnterpriseSnapshot:
        with self._connect() as connection:
            return self._snapshot(connection)

    def _snapshot(self, connection: sqlite3.Connection) -> EnterpriseSnapshot:
        po = connection.execute("SELECT * FROM purchase_order_lines").fetchone()
        warehouse = connection.execute("SELECT * FROM warehouse_receipts").fetchone()
        message = connection.execute("SELECT * FROM failed_messages").fetchone()
        erp = connection.execute("SELECT * FROM erp_receipts").fetchone()
        invoice = connection.execute("SELECT * FROM invoices").fetchone()
        if not all((po, warehouse, message, erp, invoice)):
            raise LookupError("enterprise database is not fully seeded")
        documents = connection.execute(
            "SELECT * FROM material_documents ORDER BY material_document_id"
        ).fetchall()
        effects = connection.execute(
            "SELECT * FROM business_effects ORDER BY committed_at, effect_id"
        ).fetchall()
        return EnterpriseSnapshot(
            purchase_order=PurchaseOrderLine(
                purchase_order_id=po["purchase_order_id"],
                line_id=po["line_id"],
                ordered_quantity=po["ordered_quantity"],
                unit=po["unit"],
            ),
            warehouse_receipt=WarehouseReceipt(
                receipt_id=warehouse["receipt_id"],
                purchase_order_id=warehouse["purchase_order_id"],
                line_id=warehouse["line_id"],
                quantity=warehouse["quantity"],
            ),
            failed_message=FailedReceiptMessage(
                message_id=message["message_id"],
                revision=message["revision"],
                purchase_order_id=message["purchase_order_id"],
                line_id=message["line_id"],
                quantity=message["quantity"],
                error_code=message["error_code"],
                status=MessageStatus(message["status"]),
                retry_eligible=bool(message["retry_eligible"]),
                lock_cleared=bool(message["lock_cleared"]),
                consumed_by_execution_id=message["consumed_by_execution_id"],
            ),
            erp_receipt=ErpReceipt(
                purchase_order_id=erp["purchase_order_id"],
                line_id=erp["line_id"],
                quantity=erp["quantity"],
                revision=erp["revision"],
            ),
            invoice=Invoice(
                invoice_id=invoice["invoice_id"],
                revision=invoice["revision"],
                purchase_order_id=invoice["purchase_order_id"],
                line_id=invoice["line_id"],
                quantity=invoice["quantity"],
                state=EnterpriseInvoiceState(invoice["state"]),
                hold_reason=invoice["hold_reason"],
                other_blocking_holds=tuple(json.loads(invoice["other_blocking_holds_json"])),
                released_by_execution_id=invoice["released_by_execution_id"],
            ),
            material_documents=tuple(self._document(row) for row in documents),
            business_effects=tuple(self._effect(row) for row in effects),
        )

    @staticmethod
    def _document(row: sqlite3.Row) -> MaterialDocument:
        return MaterialDocument(
            material_document_id=row["material_document_id"],
            source_message_id=row["source_message_id"],
            purchase_order_id=row["purchase_order_id"],
            line_id=row["line_id"],
            quantity=row["quantity"],
            execution_id=row["execution_id"],
            idempotency_key=row["idempotency_key"],
        )

    @staticmethod
    def _effect(row: sqlite3.Row) -> BusinessEffect:
        return BusinessEffect(
            effect_id=row["effect_id"],
            case_id=row["case_id"],
            trace_id=row["trace_id"],
            execution_id=row["execution_id"],
            idempotency_key=row["idempotency_key"],
            effect_type=EffectType(row["effect_type"]),
            source_record_id=row["source_record_id"],
            result_record_ids=tuple(json.loads(row["result_record_ids_json"])),
            committed_at=datetime.fromisoformat(row["committed_at"]),
        )

    def get_business_effect(self, idempotency_key: str) -> BusinessEffect | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM business_effects WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            return None if row is None else self._effect(row)

    def restart_receipt_message(
        self,
        *,
        case_id: str,
        trace_id: str,
        execution_id: str,
        idempotency_key: str,
        parameters: RestartReceiptMessageParameters,
        committed_at: datetime,
    ) -> EnterpriseMutationResult:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            pre_state = self._snapshot(connection)
            existing = connection.execute(
                "SELECT * FROM business_effects WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if existing is not None:
                effect = self._effect(existing)
                if effect.execution_id != execution_id:
                    raise EnterprisePreconditionFailed(
                        "idempotency key belongs to another execution"
                    )
                return EnterpriseMutationResult(
                    outcome=EnterpriseActionOutcome.SAFE_NOOP,
                    effect=effect,
                    pre_state=pre_state,
                    post_state=pre_state,
                )

            source_documents = tuple(
                document
                for document in pre_state.material_documents
                if document.source_message_id == parameters.message_id
            )
            source_effects = tuple(
                effect
                for effect in pre_state.business_effects
                if effect.effect_type is EffectType.EXTERNAL_RECEIPT
                and effect.source_record_id == parameters.message_id
            )
            externally_completed = (
                pre_state.failed_message.status is MessageStatus.CONSUMED
                and pre_state.erp_receipt.quantity == pre_state.purchase_order.ordered_quantity
                and len(source_documents) == 1
                and source_documents[0].purchase_order_id == parameters.purchase_order_id
                and source_documents[0].line_id == parameters.line_id
                and source_documents[0].quantity == parameters.quantity
                and len(source_effects) == 1
                and pre_state.failed_message.consumed_by_execution_id
                == source_documents[0].execution_id
                and source_documents[0].execution_id == source_effects[0].execution_id
                and source_documents[0].idempotency_key == source_effects[0].idempotency_key
                and source_effects[0].case_id == case_id
                and source_effects[0].trace_id == trace_id
                and source_effects[0].result_record_ids
                == (source_documents[0].material_document_id,)
            )
            if externally_completed:
                return EnterpriseMutationResult(
                    outcome=EnterpriseActionOutcome.SAFE_NOOP,
                    effect=source_effects[0],
                    pre_state=pre_state,
                    post_state=pre_state,
                )

            message = pre_state.failed_message
            erp = pre_state.erp_receipt
            expected = (
                message.message_id == parameters.message_id
                and message.revision == parameters.message_revision
                and message.purchase_order_id == parameters.purchase_order_id
                and message.line_id == parameters.line_id
                and message.quantity == parameters.quantity
                and message.error_code == parameters.expected_error_code
                and message.status.value == parameters.expected_message_status
                and message.retry_eligible
                and message.lock_cleared
                and not pre_state.material_documents
                and erp.quantity + parameters.quantity == pre_state.purchase_order.ordered_quantity
            )
            if not expected:
                raise EnterprisePreconditionFailed(
                    "receipt restart preconditions are not satisfied"
                )

            document_id = f"material-{parameters.message_id}"
            effect_id = f"effect-{execution_id}"
            connection.execute(
                "UPDATE failed_messages SET revision = revision + 1, status = ?, "
                "consumed_by_execution_id = ? WHERE message_id = ?",
                (MessageStatus.CONSUMED.value, execution_id, parameters.message_id),
            )
            connection.execute(
                "UPDATE erp_receipts SET quantity = quantity + ?, revision = revision + 1 "
                "WHERE purchase_order_id = ? AND line_id = ?",
                (parameters.quantity, parameters.purchase_order_id, parameters.line_id),
            )
            connection.execute(
                "INSERT INTO material_documents VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    document_id,
                    parameters.message_id,
                    parameters.purchase_order_id,
                    parameters.line_id,
                    parameters.quantity,
                    execution_id,
                    idempotency_key,
                ),
            )
            connection.execute(
                "INSERT INTO business_effects VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    effect_id,
                    case_id,
                    trace_id,
                    execution_id,
                    idempotency_key,
                    EffectType.RECEIPT_RESTART.value,
                    parameters.message_id,
                    json.dumps([document_id]),
                    committed_at.isoformat(),
                ),
            )
            effect = self._effect(
                connection.execute(
                    "SELECT * FROM business_effects WHERE effect_id = ?", (effect_id,)
                ).fetchone()
            )
            post_state = self._snapshot(connection)
            if erp.quantity + parameters.quantity != post_state.erp_receipt.quantity:
                raise RuntimeError("receipt mutation did not produce the expected quantity")
            return EnterpriseMutationResult(
                outcome=EnterpriseActionOutcome.EXECUTED,
                effect=effect,
                pre_state=pre_state,
                post_state=post_state,
            )

    def release_invoice(
        self,
        *,
        case_id: str,
        trace_id: str,
        execution_id: str,
        idempotency_key: str,
        parameters: ReleaseInvoiceParameters,
        committed_at: datetime,
    ) -> EnterpriseMutationResult:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            pre_state = self._snapshot(connection)
            existing = connection.execute(
                "SELECT * FROM business_effects WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if existing is not None:
                effect = self._effect(existing)
                if effect.execution_id != execution_id:
                    raise EnterprisePreconditionFailed(
                        "idempotency key belongs to another execution"
                    )
                return EnterpriseMutationResult(
                    outcome=EnterpriseActionOutcome.SAFE_NOOP,
                    effect=effect,
                    pre_state=pre_state,
                    post_state=pre_state,
                )

            source_effects = tuple(
                effect
                for effect in pre_state.business_effects
                if effect.effect_type is EffectType.EXTERNAL_INVOICE_RELEASE
                and effect.source_record_id == parameters.invoice_id
            )
            externally_completed = (
                pre_state.invoice.state is EnterpriseInvoiceState.RELEASED
                and pre_state.invoice.purchase_order_id == parameters.purchase_order_id
                and pre_state.invoice.line_id == parameters.line_id
                and pre_state.invoice.quantity == parameters.quantity
                and pre_state.invoice.hold_reason is None
                and not pre_state.invoice.other_blocking_holds
                and pre_state.erp_receipt.quantity == pre_state.purchase_order.ordered_quantity
                and len(source_effects) == 1
                and pre_state.invoice.released_by_execution_id == source_effects[0].execution_id
                and source_effects[0].case_id == case_id
                and source_effects[0].trace_id == trace_id
                and source_effects[0].result_record_ids == (parameters.invoice_id,)
            )
            if externally_completed:
                return EnterpriseMutationResult(
                    outcome=EnterpriseActionOutcome.SAFE_NOOP,
                    effect=source_effects[0],
                    pre_state=pre_state,
                    post_state=pre_state,
                )

            invoice = pre_state.invoice
            expected = (
                invoice.invoice_id == parameters.invoice_id
                and invoice.revision == parameters.invoice_revision
                and invoice.purchase_order_id == parameters.purchase_order_id
                and invoice.line_id == parameters.line_id
                and invoice.quantity == parameters.quantity
                and invoice.state is EnterpriseInvoiceState.HELD
                and invoice.hold_reason == parameters.expected_hold_reason
                and not invoice.other_blocking_holds
                and pre_state.erp_receipt.quantity == pre_state.purchase_order.ordered_quantity
            )
            if not expected:
                raise EnterprisePreconditionFailed(
                    "invoice release preconditions are not satisfied"
                )

            effect_id = f"effect-{execution_id}"
            connection.execute(
                "UPDATE invoices SET revision = revision + 1, state = ?, hold_reason = NULL, "
                "released_by_execution_id = ? WHERE invoice_id = ?",
                (EnterpriseInvoiceState.RELEASED.value, execution_id, parameters.invoice_id),
            )
            connection.execute(
                "INSERT INTO business_effects VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    effect_id,
                    case_id,
                    trace_id,
                    execution_id,
                    idempotency_key,
                    EffectType.INVOICE_RELEASE.value,
                    parameters.invoice_id,
                    json.dumps([parameters.invoice_id]),
                    committed_at.isoformat(),
                ),
            )
            effect = self._effect(
                connection.execute(
                    "SELECT * FROM business_effects WHERE effect_id = ?", (effect_id,)
                ).fetchone()
            )
            return EnterpriseMutationResult(
                outcome=EnterpriseActionOutcome.EXECUTED,
                effect=effect,
                pre_state=pre_state,
                post_state=self._snapshot(connection),
            )

    def set_erp_receipt_quantity_for_test(self, quantity: int) -> None:
        """Alter authoritative state through SQLite for postcondition-failure testing."""
        with self._connect() as connection:
            connection.execute(
                "UPDATE erp_receipts SET quantity = ?, revision = revision + 1",
                (quantity,),
            )

    def set_invoice_hold_for_test(self, hold_reason: str) -> None:
        """Reintroduce an authoritative hold for invoice verification testing."""
        with self._connect() as connection:
            connection.execute(
                "UPDATE invoices SET state = ?, hold_reason = ?, revision = revision + 1",
                (EnterpriseInvoiceState.HELD.value, hold_reason),
            )

    def simulate_external_receipt(
        self,
        *,
        case_id: str,
        trace_id: str,
        parameters: RestartReceiptMessageParameters,
        committed_at: datetime,
    ) -> EnterpriseMutationResult:
        """Apply a real competing receipt transaction before the local executor runs."""
        execution_id = f"external-receipt-{parameters.message_id}"
        result = self.restart_receipt_message(
            case_id=case_id,
            trace_id=trace_id,
            execution_id=execution_id,
            idempotency_key=f"external-receipt:{parameters.message_id}",
            parameters=parameters,
            committed_at=committed_at,
        )
        with self._connect() as connection:
            connection.execute(
                "UPDATE business_effects SET effect_type = ? WHERE effect_id = ?",
                (EffectType.EXTERNAL_RECEIPT.value, result.effect.effect_id),
            )
        return result.model_copy(
            update={
                "effect": result.effect.model_copy(
                    update={"effect_type": EffectType.EXTERNAL_RECEIPT}
                )
            }
        )

    def simulate_external_invoice_release(
        self,
        *,
        case_id: str,
        trace_id: str,
        parameters: ReleaseInvoiceParameters,
        committed_at: datetime,
    ) -> EnterpriseMutationResult:
        """Apply a real competing invoice transaction before the local executor runs."""
        execution_id = f"external-invoice-{parameters.invoice_id}"
        result = self.release_invoice(
            case_id=case_id,
            trace_id=trace_id,
            execution_id=execution_id,
            idempotency_key=f"external-invoice:{parameters.invoice_id}",
            parameters=parameters,
            committed_at=committed_at,
        )
        with self._connect() as connection:
            connection.execute(
                "UPDATE business_effects SET effect_type = ? WHERE effect_id = ?",
                (EffectType.EXTERNAL_INVOICE_RELEASE.value, result.effect.effect_id),
            )
        return result.model_copy(
            update={
                "effect": result.effect.model_copy(
                    update={"effect_type": EffectType.EXTERNAL_INVOICE_RELEASE}
                )
            }
        )
