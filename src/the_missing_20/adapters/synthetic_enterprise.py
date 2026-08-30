"""SQLite-backed synthetic enterprise systems with transactional business effects."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from the_missing_20.domain.enterprise import (
    BusinessEffect,
    EnterpriseActionOutcome,
    EnterpriseInvoiceState,
    EnterpriseMutationResult,
    EnterpriseSnapshot,
    ErpReceipt,
    EvidenceReadStatus,
    FailedReceiptMessage,
    Invoice,
    MaterialDocument,
    MaterialDocumentRead,
    MessageStatus,
    PurchaseOrderLine,
    ScenarioFixture,
    SupplyUnit,
    SupplyUnitStage,
    SupplyUnitStatus,
    WarehouseReceipt,
)
from the_missing_20.domain.execution import (
    EXTERNAL_ID_NAMESPACE,
    EffectType,
    ReleaseInvoiceParameters,
    RestartReceiptMessageParameters,
)
from the_missing_20.ports.enterprise_systems import EnterprisePreconditionFailed


@dataclass(frozen=True)
class SourceConditionMutation:
    """Authoritative before/after reads for one synthetic source transaction."""

    pre_state: EnterpriseSnapshot
    post_state: EnterpriseSnapshot
    affected_unit_ids: tuple[str, ...]
    transition_id: str = "source-transition:retryable-document-lock"
    committed_at: datetime | None = None


@dataclass(frozen=True)
class SourceConditionOutbox:
    """Immutable source transition envelope committed with the source mutation.

    The enterprise database is the source system and the public event ledger is a
    projection.  Keeping this envelope in the same SQLite transaction as the
    source rows gives the projector a durable recovery point when a ledger append
    fails after the source commit.
    """

    transition_id: str
    condition: str
    pre_state: EnterpriseSnapshot
    post_state: EnterpriseSnapshot
    affected_unit_ids: tuple[str, ...]
    committed_at: datetime


class SyntheticEnterprise:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self._material_document_unavailable_reason: str | None = None
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
            # The healthy control room view uses the same stable 100-unit order but
            # starts after the queue has reconciled.  Keep it as a separate
            # synthetic fixture so switching scenarios never rewrites the active
            # incident ledger or fabricates a browser-only count.
            units = fixture.supply_units or cls._units_for_fixture(fixture)
            if len(units) != fixture.purchase_order.ordered_quantity:
                raise ValueError("synthetic fixture must contain one unit per ordered item")
            if len({item.unit_id for item in units}) != len(units):
                raise ValueError("synthetic fixture unit IDs must be unique")
            failed_units = tuple(
                item for item in units if item.status is SupplyUnitStatus.QUEUE_FAILED
            )
            recorded_units = tuple(
                item for item in units if item.status is SupplyUnitStatus.ERP_RECORDED
            )
            expected_failed_quantity = (
                0 if fixture.scenario_id == "healthy-flow" else fixture.failed_message.quantity
            )
            if len(failed_units) != expected_failed_quantity:
                raise ValueError("synthetic fixture units must bind the exact failed quantity")
            if len(recorded_units) + len(failed_units) != len(units):
                raise ValueError("synthetic fixture units contain an unsupported status")
            if any(
                item.source_message_id != fixture.failed_message.message_id for item in failed_units
            ):
                raise ValueError("queue-failed units must bind the failed message")
            for unit in units:
                if (
                    unit.purchase_order_id != fixture.purchase_order.purchase_order_id
                    or unit.line_id != fixture.purchase_order.line_id
                ):
                    raise ValueError("synthetic fixture units must share the purchase-order line")
                connection.execute(
                    "INSERT INTO supply_units VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        unit.unit_id,
                        unit.purchase_order_id,
                        unit.line_id,
                        unit.current_stage.value,
                        unit.status.value,
                        unit.source_message_id,
                        unit.revision,
                    ),
                )
            for document in fixture.material_documents:
                connection.execute(
                    "INSERT INTO material_documents VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        document.material_document_id,
                        document.source_message_id,
                        document.purchase_order_id,
                        document.line_id,
                        document.quantity,
                        document.execution_id,
                        document.idempotency_key,
                    ),
                )
            for effect in fixture.business_effects:
                connection.execute(
                    "INSERT INTO business_effects VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        effect.effect_id,
                        effect.case_id,
                        effect.trace_id,
                        effect.execution_id,
                        effect.idempotency_key,
                        effect.effect_type.value,
                        effect.source_record_id,
                        json.dumps(effect.result_record_ids),
                        effect.committed_at.isoformat(),
                    ),
                )
        return adapter

    @staticmethod
    def _units_for_fixture(fixture: ScenarioFixture) -> tuple[SupplyUnit, ...]:
        """Expand the aggregate fixture into stable unit records.

        The fixture's failed-message quantity is the exact Missing 20 set.  Unit
        IDs are deterministic and portable across a fresh database, so a client
        can safely correlate a visual unit with the recovery transaction.
        """

        ordered = fixture.purchase_order.ordered_quantity
        missing = 0 if fixture.scenario_id == "healthy-flow" else fixture.failed_message.quantity
        recorded = ordered - missing
        if recorded < 0:
            raise ValueError("failed-message quantity cannot exceed ordered quantity")
        return tuple(
            SupplyUnit(
                unit_id=(
                    f"{fixture.purchase_order.purchase_order_id}-"
                    f"{fixture.purchase_order.line_id}-unit-{index:03d}"
                ),
                purchase_order_id=fixture.purchase_order.purchase_order_id,
                line_id=fixture.purchase_order.line_id,
                current_stage=(
                    SupplyUnitStage.ERP if index <= recorded else SupplyUnitStage.MESSAGE_QUEUE
                ),
                status=(
                    SupplyUnitStatus.ERP_RECORDED
                    if index <= recorded
                    else SupplyUnitStatus.QUEUE_FAILED
                ),
                source_message_id=(
                    None if index <= recorded else fixture.failed_message.message_id
                ),
            )
            for index in range(1, ordered + 1)
        )

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
                CREATE TABLE IF NOT EXISTS supply_units (
                    unit_id TEXT PRIMARY KEY,
                    purchase_order_id TEXT NOT NULL,
                    line_id TEXT NOT NULL,
                    current_stage TEXT NOT NULL,
                    status TEXT NOT NULL,
                    source_message_id TEXT,
                    revision INTEGER NOT NULL
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
                CREATE TABLE IF NOT EXISTS source_condition_outbox (
                    transition_id TEXT PRIMARY KEY,
                    condition TEXT NOT NULL,
                    pre_state_json TEXT NOT NULL,
                    post_state_json TEXT NOT NULL,
                    affected_unit_ids_json TEXT NOT NULL,
                    committed_at TEXT NOT NULL
                );
                """
            )

    def read_snapshot(self) -> EnterpriseSnapshot:
        with self._connect() as connection:
            return self._snapshot(connection)

    @staticmethod
    def _source_transition_snapshot(snapshot: EnterpriseSnapshot) -> dict[str, object]:
        """Serialize every source row needed to recover one transition exactly."""

        return {
            "purchase_order": snapshot.purchase_order.model_dump(mode="json"),
            "warehouse_receipt": snapshot.warehouse_receipt.model_dump(mode="json"),
            "failed_message": snapshot.failed_message.model_dump(mode="json"),
            "erp_receipt": snapshot.erp_receipt.model_dump(mode="json"),
            "invoice": snapshot.invoice.model_dump(mode="json"),
            "supply_units": [item.model_dump(mode="json") for item in snapshot.supply_units],
            "material_documents": [
                item.model_dump(mode="json") for item in snapshot.material_documents
            ],
            "business_effects": [
                item.model_dump(mode="json") for item in snapshot.business_effects
            ],
        }

    @staticmethod
    def _source_transition_snapshot_from_json(raw: str) -> EnterpriseSnapshot:
        """Restore a typed source snapshot from the durable outbox envelope."""

        value = json.loads(raw)
        if not isinstance(value, dict):
            raise EnterprisePreconditionFailed("source transition envelope is malformed")
        try:
            purchase_order = PurchaseOrderLine(**value["purchase_order"])
            warehouse_receipt = WarehouseReceipt(**value["warehouse_receipt"])
            message_value = value["failed_message"]
            failed_message = FailedReceiptMessage(
                **{
                    **message_value,
                    "status": MessageStatus(message_value["status"]),
                },
            )
            erp_receipt = ErpReceipt(**value["erp_receipt"])
            invoice_value = value["invoice"]
            invoice = Invoice(
                **{
                    **invoice_value,
                    "state": EnterpriseInvoiceState(invoice_value["state"]),
                    "other_blocking_holds": tuple(invoice_value["other_blocking_holds"]),
                },
            )
            supply_units = tuple(
                SupplyUnit(
                    **{
                        **item,
                        "current_stage": SupplyUnitStage(item["current_stage"]),
                        "status": SupplyUnitStatus(item["status"]),
                    },
                )
                for item in value["supply_units"]
            )
            material_documents = tuple(
                MaterialDocument(**item) for item in value["material_documents"]
            )
            business_effects = tuple(
                BusinessEffect(
                    **{
                        **item,
                        "effect_type": EffectType(item["effect_type"]),
                        "result_record_ids": tuple(item["result_record_ids"]),
                        "committed_at": datetime.fromisoformat(item["committed_at"]),
                    },
                )
                for item in value["business_effects"]
            )
            return EnterpriseSnapshot(
                purchase_order=purchase_order,
                warehouse_receipt=warehouse_receipt,
                failed_message=failed_message,
                erp_receipt=erp_receipt,
                invoice=invoice,
                supply_units=supply_units,
                material_documents=material_documents,
                business_effects=business_effects,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise EnterprisePreconditionFailed("source transition envelope is malformed") from exc

    @classmethod
    def _source_condition_outbox_row(
        cls, row: sqlite3.Row | None
    ) -> SourceConditionOutbox | None:
        if row is None:
            return None
        try:
            committed_at = datetime.fromisoformat(row["committed_at"])
            if committed_at.tzinfo is None or committed_at.utcoffset() is None:
                raise ValueError("outbox timestamp is not timezone aware")
            affected_raw = json.loads(row["affected_unit_ids_json"])
            if not isinstance(affected_raw, list) or not all(
                isinstance(item, str) and item for item in affected_raw
            ):
                raise ValueError("outbox unit IDs are malformed")
            return SourceConditionOutbox(
                transition_id=row["transition_id"],
                condition=row["condition"],
                pre_state=cls._source_transition_snapshot_from_json(row["pre_state_json"]),
                post_state=cls._source_transition_snapshot_from_json(row["post_state_json"]),
                affected_unit_ids=tuple(affected_raw),
                committed_at=committed_at,
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise EnterprisePreconditionFailed("source transition outbox is malformed") from exc

    def read_source_condition_outbox(self) -> SourceConditionOutbox | None:
        """Read the immutable source transition awaiting public publication."""

        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM source_condition_outbox ORDER BY committed_at, transition_id LIMIT 1"
            ).fetchone()
        return self._source_condition_outbox_row(row)

    def list_units(self) -> tuple[SupplyUnit, ...]:
        """Return the authoritative unit records in stable ID order."""

        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM supply_units ORDER BY unit_id").fetchall()
            return tuple(self._unit(row) for row in rows)

    def read_material_documents(self) -> MaterialDocumentRead:
        if self._material_document_unavailable_reason is not None:
            return MaterialDocumentRead(
                status=EvidenceReadStatus.UNAVAILABLE,
                reason_code=self._material_document_unavailable_reason,
            )
        snapshot = self.read_snapshot()
        return MaterialDocumentRead(
            status=EvidenceReadStatus.AVAILABLE,
            documents=snapshot.material_documents,
            business_effects=snapshot.business_effects,
        )

    def set_material_document_source_unavailable(self, reason_code: str) -> None:
        self._material_document_unavailable_reason = reason_code

    def advance_failed_message_revision(self) -> FailedReceiptMessage:
        """Record a real authoritative message revision before a fresh evidence read."""
        with self._connect() as connection:
            connection.execute(
                "UPDATE failed_messages SET revision = revision + 1 WHERE message_id = "
                "(SELECT message_id FROM failed_messages LIMIT 1)"
            )
        return self.read_snapshot().failed_message

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
        units = connection.execute("SELECT * FROM supply_units ORDER BY unit_id").fetchall()
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
            supply_units=tuple(self._unit(row) for row in units),
            material_documents=tuple(self._document(row) for row in documents),
            business_effects=tuple(self._effect(row) for row in effects),
        )

    @staticmethod
    def _unit(row: sqlite3.Row) -> SupplyUnit:
        return SupplyUnit(
            unit_id=row["unit_id"],
            purchase_order_id=row["purchase_order_id"],
            line_id=row["line_id"],
            current_stage=SupplyUnitStage(row["current_stage"]),
            status=SupplyUnitStatus(row["status"]),
            source_message_id=row["source_message_id"],
            revision=row["revision"],
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

    def inject_retryable_document_lock(
        self,
        *,
        purchase_order_id: str = "PO-10001",
        line_id: str = "10",
        message_id: str = "RECEIPT-MESSAGE-020",
        quantity: int = 20,
    ) -> SourceConditionMutation:
        """Atomically turn the healthy source into the retryable-lock condition.

        This is the only source-condition write used by Scenario Lab.  It starts
        from the frozen healthy-flow state, validates the complete aggregate and
        per-unit preconditions, and commits the queue, ERP, invoice, message, and
        exact unit-set changes in one SQLite transaction.  A stale or partially
        changed source fails closed before any row is updated.
        """

        expected_purchase_order_id = "PO-10001"
        expected_line_id = "10"
        expected_message_id = "RECEIPT-MESSAGE-020"
        expected_quantity = 20
        if (
            purchase_order_id != expected_purchase_order_id
            or line_id != expected_line_id
            or message_id != expected_message_id
            or quantity != expected_quantity
        ):
            raise EnterprisePreconditionFailed(
                "retryable lock must target the frozen PO-10001 line 10 message and quantity"
            )

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing_outbox = self._source_condition_outbox_row(
                connection.execute(
                    "SELECT * FROM source_condition_outbox "
                    "ORDER BY committed_at, transition_id LIMIT 1"
                ).fetchone()
            )
            if existing_outbox is not None:
                raise EnterprisePreconditionFailed(
                    "retryable lock source transition has already been committed"
                )
            pre_state = self._snapshot(connection)
            purchase_order = pre_state.purchase_order
            message = pre_state.failed_message
            erp = pre_state.erp_receipt
            invoice = pre_state.invoice
            units = pre_state.supply_units
            expected_unit_ids = tuple(
                f"{expected_purchase_order_id}-{expected_line_id}-unit-{index:03d}"
                for index in range(81, 101)
            )
            actual_unit_ids = tuple(item.unit_id for item in units)
            target_units = tuple(item for item in units if item.unit_id in expected_unit_ids)
            healthy = (
                purchase_order.purchase_order_id == expected_purchase_order_id
                and purchase_order.line_id == expected_line_id
                and purchase_order.ordered_quantity == expected_quantity * 5
                and message.message_id == expected_message_id
                and message.revision == 4
                and message.purchase_order_id == expected_purchase_order_id
                and message.line_id == expected_line_id
                and message.quantity == expected_quantity
                and message.error_code == "DOCUMENT_LOCKED_RETRYABLE"
                and message.status is MessageStatus.CONSUMED
                and not message.retry_eligible
                and message.lock_cleared
                and message.consumed_by_execution_id == "external:healthy-baseline"
                and erp.purchase_order_id == expected_purchase_order_id
                and erp.line_id == expected_line_id
                and erp.quantity == purchase_order.ordered_quantity
                and erp.revision == 9
                and invoice.invoice_id == "INV-10001"
                and invoice.revision == 5
                and invoice.purchase_order_id == expected_purchase_order_id
                and invoice.line_id == expected_line_id
                and invoice.quantity == purchase_order.ordered_quantity
                and invoice.state is EnterpriseInvoiceState.RELEASED
                and invoice.hold_reason is None
                and not invoice.other_blocking_holds
                and invoice.released_by_execution_id == message.consumed_by_execution_id
                and not pre_state.material_documents
                and not pre_state.business_effects
                and len(units) == purchase_order.ordered_quantity
                and actual_unit_ids == tuple(sorted(actual_unit_ids))
                and set(actual_unit_ids) == set(
                    f"{expected_purchase_order_id}-{expected_line_id}-unit-{index:03d}"
                    for index in range(1, purchase_order.ordered_quantity + 1)
                )
                and len(target_units) == expected_quantity
                and all(
                    item.purchase_order_id == expected_purchase_order_id
                    and item.line_id == expected_line_id
                    and item.current_stage is SupplyUnitStage.ERP
                    and item.status is SupplyUnitStatus.ERP_RECORDED
                    and item.source_message_id is None
                    and item.revision == 0
                    for item in units
                )
            )
            if not healthy:
                raise EnterprisePreconditionFailed(
                    "retryable lock source preconditions are not satisfied"
                )

            changed = connection.execute(
                "UPDATE failed_messages SET revision = revision + 1, status = ?, "
                "retry_eligible = 1, lock_cleared = 1, consumed_by_execution_id = NULL "
                "WHERE message_id = ? AND revision = ? AND status = ? "
                "AND retry_eligible = 0 AND lock_cleared = 1",
                (
                    MessageStatus.FAILED.value,
                    expected_message_id,
                    message.revision,
                    MessageStatus.CONSUMED.value,
                ),
            ).rowcount
            if changed != 1:
                raise EnterprisePreconditionFailed(
                    "retryable lock message changed during source transaction"
                )
            changed = connection.execute(
                "UPDATE erp_receipts SET quantity = ?, revision = revision + 1 "
                "WHERE purchase_order_id = ? AND line_id = ? AND quantity = ? AND revision = ?",
                (
                    purchase_order.ordered_quantity - expected_quantity,
                    expected_purchase_order_id,
                    expected_line_id,
                    erp.quantity,
                    erp.revision,
                ),
            ).rowcount
            if changed != 1:
                raise EnterprisePreconditionFailed(
                    "ERP receipt changed during source transaction"
                )
            changed = connection.execute(
                "UPDATE invoices SET revision = revision + 1, state = ?, "
                "hold_reason = ?, released_by_execution_id = NULL "
                "WHERE invoice_id = ? AND revision = ? AND state = ? "
                "AND hold_reason IS NULL",
                (
                    EnterpriseInvoiceState.HELD.value,
                    "RECEIPT_MISMATCH",
                    invoice.invoice_id,
                    invoice.revision,
                    EnterpriseInvoiceState.RELEASED.value,
                ),
            ).rowcount
            if changed != 1:
                raise EnterprisePreconditionFailed(
                    "invoice changed during source transaction"
                )
            for unit in target_units:
                changed = connection.execute(
                    "UPDATE supply_units SET current_stage = ?, status = ?, "
                    "source_message_id = ?, revision = revision + 1 "
                    "WHERE unit_id = ? AND purchase_order_id = ? AND line_id = ? "
                    "AND current_stage = ? AND status = ? AND source_message_id IS NULL "
                    "AND revision = 0",
                    (
                        SupplyUnitStage.MESSAGE_QUEUE.value,
                        SupplyUnitStatus.QUEUE_FAILED.value,
                        expected_message_id,
                        unit.unit_id,
                        expected_purchase_order_id,
                        expected_line_id,
                        SupplyUnitStage.ERP.value,
                        SupplyUnitStatus.ERP_RECORDED.value,
                    ),
                ).rowcount
                if changed != 1:
                    raise EnterprisePreconditionFailed(
                        "retryable lock could not update the exact unit set"
                    )

            post_state = self._snapshot(connection)
            post_units = {item.unit_id: item for item in post_state.supply_units}
            if (
                post_state.erp_receipt.quantity
                != purchase_order.ordered_quantity - expected_quantity
                or post_state.erp_receipt.revision != erp.revision + 1
                or post_state.failed_message.status is not MessageStatus.FAILED
                or post_state.failed_message.revision != message.revision + 1
                or not post_state.failed_message.retry_eligible
                or post_state.failed_message.lock_cleared is not True
                or post_state.failed_message.consumed_by_execution_id is not None
                or post_state.invoice.state is not EnterpriseInvoiceState.HELD
                or post_state.invoice.revision != invoice.revision + 1
                or post_state.invoice.hold_reason != "RECEIPT_MISMATCH"
                or post_state.invoice.released_by_execution_id is not None
                or len(post_units) != purchase_order.ordered_quantity
                or sum(
                    item.status is SupplyUnitStatus.QUEUE_FAILED
                    and item.current_stage is SupplyUnitStage.MESSAGE_QUEUE
                    and item.source_message_id == expected_message_id
                    for item in post_units.values()
                )
                != expected_quantity
                or any(
                    post_units[item_id].revision != 1
                    or post_units[item_id].status is not SupplyUnitStatus.QUEUE_FAILED
                    or post_units[item_id].current_stage is not SupplyUnitStage.MESSAGE_QUEUE
                    or post_units[item_id].source_message_id != expected_message_id
                    for item_id in expected_unit_ids
                )
                or any(
                    post_units[item.unit_id] != item
                    for item in units
                    if item.unit_id not in expected_unit_ids
                )
            ):
                raise RuntimeError("retryable lock transaction failed postcondition validation")
            transition_id = (
                f"source-transition:retryable-document-lock:"
                f"{expected_purchase_order_id}:{expected_line_id}:{expected_message_id}"
            )
            committed_at = datetime.now(UTC)
            connection.execute(
                "INSERT INTO source_condition_outbox VALUES (?, ?, ?, ?, ?, ?)",
                (
                    transition_id,
                    "retryable_document_lock",
                    json.dumps(
                        self._source_transition_snapshot(pre_state),
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    json.dumps(
                        self._source_transition_snapshot(post_state),
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    json.dumps(expected_unit_ids, separators=(",", ":")),
                    committed_at.isoformat(),
                ),
            )
            return SourceConditionMutation(
                pre_state=pre_state,
                post_state=post_state,
                affected_unit_ids=expected_unit_ids,
                transition_id=transition_id,
                committed_at=committed_at,
            )

    def apply_retryable_document_lock(self) -> SourceConditionMutation:
        """Compatibility name for callers describing the source write as an apply."""

        return self.inject_retryable_document_lock()

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
                and len(pre_state.supply_units) == pre_state.purchase_order.ordered_quantity
                and all(
                    unit.status is SupplyUnitStatus.ERP_RECORDED
                    and unit.current_stage is SupplyUnitStage.ERP
                    and unit.source_message_id is None
                    for unit in pre_state.supply_units
                )
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
                and len(pre_state.supply_units) == pre_state.purchase_order.ordered_quantity
                and sum(
                    unit.status is SupplyUnitStatus.QUEUE_FAILED
                    and unit.current_stage is SupplyUnitStage.MESSAGE_QUEUE
                    and unit.source_message_id == parameters.message_id
                    for unit in pre_state.supply_units
                )
                == parameters.quantity
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
            missing_units = tuple(
                unit
                for unit in pre_state.supply_units
                if unit.status is SupplyUnitStatus.QUEUE_FAILED
                and unit.current_stage is SupplyUnitStage.MESSAGE_QUEUE
                and unit.source_message_id == parameters.message_id
            )
            for unit in missing_units:
                changed = connection.execute(
                    "UPDATE supply_units SET current_stage = ?, status = ?, "
                    "source_message_id = NULL, revision = revision + 1 "
                    "WHERE unit_id = ? AND revision = ? AND status = ? "
                    "AND current_stage = ? AND source_message_id = ?",
                    (
                        SupplyUnitStage.ERP.value,
                        SupplyUnitStatus.ERP_RECORDED.value,
                        unit.unit_id,
                        unit.revision,
                        SupplyUnitStatus.QUEUE_FAILED.value,
                        SupplyUnitStage.MESSAGE_QUEUE.value,
                        parameters.message_id,
                    ),
                ).rowcount
                if changed != 1:
                    raise RuntimeError("receipt mutation could not update the exact unit set")
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
            post_by_id = {unit.unit_id: unit for unit in post_state.supply_units}
            recovered_ids = {item.unit_id for item in missing_units}
            if (
                len(post_by_id) != len(pre_state.supply_units)
                or any(
                    post_by_id[unit.unit_id].status is not SupplyUnitStatus.ERP_RECORDED
                    or post_by_id[unit.unit_id].current_stage is not SupplyUnitStage.ERP
                    or post_by_id[unit.unit_id].source_message_id is not None
                    or post_by_id[unit.unit_id].revision != unit.revision + 1
                    for unit in missing_units
                )
                or not all(
                    post_by_id[unit.unit_id] == unit
                    for unit in pre_state.supply_units
                    if unit.unit_id not in recovered_ids
                )
            ):
                raise RuntimeError("receipt mutation changed an unexpected unit")
            if (
                sum(
                    unit.status is SupplyUnitStatus.ERP_RECORDED for unit in post_state.supply_units
                )
                != pre_state.purchase_order.ordered_quantity
            ):
                raise RuntimeError("receipt mutation did not reconcile all units")
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
        execution_id = f"{EXTERNAL_ID_NAMESPACE}receipt:{parameters.message_id}"
        result = self.restart_receipt_message(
            case_id=case_id,
            trace_id=trace_id,
            execution_id=execution_id,
            idempotency_key=f"{EXTERNAL_ID_NAMESPACE}receipt:{parameters.message_id}",
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
        execution_id = f"{EXTERNAL_ID_NAMESPACE}invoice:{parameters.invoice_id}"
        result = self.release_invoice(
            case_id=case_id,
            trace_id=trace_id,
            execution_id=execution_id,
            idempotency_key=f"{EXTERNAL_ID_NAMESPACE}invoice:{parameters.invoice_id}",
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
