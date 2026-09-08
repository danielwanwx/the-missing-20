"""Browser proof for the case-first Agent Platform console."""

from __future__ import annotations

import threading
from copy import deepcopy
from pathlib import Path

import pytest

from scripts.decision_workspace_server import DecisionWorkspaceServer
from scripts.run_decision_workspace_smoke import _CDPBrowser, _chrome, _wait_ui
from the_missing_20.adapters.agent_platform import AgentPlatform
from the_missing_20.adapters.ambiguous_case_platform import AmbiguousCasePlatform

ROOT = Path(__file__).resolve().parents[1]


class _Reader:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def current(self) -> dict[str, object]:
        return deepcopy(self.payload)


def _erp() -> dict[str, object]:
    return {
        "status": "CONNECTED",
        "activity": [
            {
                "source_id": "erpnext-missing20",
                "provider": "ERPNext",
                "status": "HELD",
                "record_id": "PR-20",
                "label": "Receipt PR-20",
                "detail": "8 held",
            }
        ],
        "documents": [
            {"kind": "purchase_order", "name": "PO-20"},
            {
                "kind": "purchase_receipt",
                "name": "PR-20",
                "status": "PARTIAL_QUALITY_HOLD",
                "rejected": 8,
            },
            {"kind": "purchase_invoice", "name": "PI-20", "status": "PAYMENT_HOLD"},
        ],
    }


def _saas() -> dict[str, object]:
    tuple_fields = {
        "case_id": "M20-CASE-20",
        "purchase_order": "PO-20",
        "purchase_receipt": "PR-20",
        "purchase_invoice": "PI-20",
        "supplier_lot": "LOT-20",
        "certificate_id": "CERT-20",
        "quantity": 8,
        "evidence_revision": "rev-3",
    }
    sources = [
        {
            "source_id": "airtable-quality-registry",
            "provider": "Airtable",
            "status": "VERIFIED",
            "record_id": "rec-20",
            "label": "Registry approved",
            "detail": "quality release registry",
            "correlation": tuple_fields,
        },
        {
            "source_id": "celigo-quality-release",
            "provider": "Celigo",
            "status": "VERIFIED",
            "record_id": "run-20",
            "label": "Run receipt",
            "detail": "ERP acknowledged",
            "evidence_kind": "RUN_RECEIPT",
            "correlation": tuple_fields,
            "erp_acknowledged": True,
        },
        {
            "source_id": "jira-capa",
            "provider": "Jira",
            "status": "VERIFIED",
            "record_id": "CAPA-20",
            "label": "CAPA journal",
            "detail": "context only",
        },
        {
            "source_id": "slack-quality-alerts",
            "provider": "Slack",
            "status": "VERIFIED",
            "record_id": "171.20",
            "label": "Alert journal",
            "detail": "context only",
        },
    ]
    return {
        "status": "CONNECTED",
        "correlation_id": "M20-CASE-20",
        "sources": sources,
        "activity": sources,
    }


def test_browser_renders_live_agent_platform_and_keeps_writes_disabled(tmp_path: Path) -> None:
    platform = AgentPlatform(_Reader(_erp()), _Reader(_saas()))
    try:
        server = DecisionWorkspaceServer(
            ("127.0.0.1", 0),
            ROOT,
            runtime_directory=tmp_path / "runtime",
            agent_platform=platform,
        )
    except PermissionError:
        pytest.skip("the managed test sandbox disallows loopback sockets")
    server.registry.select_incident()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    browser: _CDPBrowser | None = None
    try:
        try:
            chrome = _chrome()
            browser = _CDPBrowser(chrome, tmp_path / "chrome")
        except (OSError, RuntimeError) as exc:
            pytest.skip(f"headless Chrome is unavailable: {exc}")
        with browser:
            base = f"http://127.0.0.1:{server.server_port}"
            browser.navigate(f"{base}/?view=dashboard&scenario=incident")
            _wait_ui(
                browser,
                (
                    "document.body.dataset.agentPlatform === 'ready' && "
                    "getComputedStyle(document.querySelector('#dashboard-chart')).display "
                    "!== 'none' && "
                    "document.querySelectorAll('#dashboard-event-feed "
                    ".dashboard-event-row').length > 0 && "
                    "document.querySelectorAll('#dashboard-evidence-links path').length === 4 && "
                    "document.querySelectorAll('#flow-map "
                    ".flow-node[data-stage-count]').length === 4"
                ),
                "flow-first dashboard projection",
            )
            assert browser.evaluate(
                "getComputedStyle(document.querySelector("
                "'#dashboard-view .dashboard-grid')).display !== 'none'"
            )
            assert browser.evaluate(
                "[...document.querySelectorAll('#dashboard-evidence-links path')]"
                ".every(path => path.getAttribute('d').includes(' L '))"
            )
            assert browser.evaluate(
                "document.querySelectorAll('#flow-map .flow-link, "
                "#flow-map .flow-node-port, #flow-map .flow-particle').length === 0"
            )
            browser.evaluate("document.querySelector('#tab-agent')?.click()")
            _wait_ui(
                browser,
                (
                    "document.body.dataset.view === 'agent' && "
                    "document.querySelector('#agent-platform-console')?.hidden === false && "
                    "document.querySelector('#agent-platform-console')?.parentElement?.id "
                    "=== 'agent-view' && "
                    "document.querySelector('#agent-view .workspace-layout')?.hidden === true && "
                    "document.querySelectorAll('.platform-investigation-link').length === 6 && "
                    "document.querySelectorAll("
                    "'#platform-source-receipts .platform-source-receipt').length === 5"
                ),
                "investigation workspace projection",
            )
            assert browser.evaluate(
                "document.querySelector('#platform-mode')?.textContent.includes('WRITES DISABLED')"
            )
            assert browser.evaluate(
                "['WAITING', 'MANAGER REVIEW'].includes("
                "document.querySelector('#platform-outcome-status')?.textContent) && "
                "document.querySelector('#platform-diagnose')?.disabled"
            )
            geometry = browser.evaluate(
                "(() => {"
                "const map=document.querySelector('#platform-investigation-map');"
                "const paths=[...document.querySelectorAll('.platform-investigation-link')];"
                "if(!map)return {ok:false,reason:'missing-map'};"
                "const mb=map.getBoundingClientRect();"
                "const edgeError=(id,p)=>{"
                'const node=map.querySelector(`[data-investigation-node="${id}"]`);'
                "if(!node)return 99;"
                "const r=node.getBoundingClientRect(),cx=r.left-mb.left+r.width/2,"
                "cy=r.top-mb.top+r.height/2;"
                "const nx=Math.abs(p.x-cx)/(r.width/2),ny=Math.abs(p.y-cy)/(r.height/2);"
                "return Math.abs((node.classList.contains('platform-agent-node')?"
                "Math.sqrt(nx*nx+ny*ny):Math.max(nx,ny))-1);"
                "};"
                "const edgeErrors=paths.map(path=>{"
                "const [from,to]=path.dataset.platformLink.split('-');"
                "return {id:path.dataset.platformLink,straight:"
                "path.getAttribute('d').includes(' L '),from:edgeError(from,"
                "path.getPointAtLength(0)),"
                "to:edgeError(to,path.getPointAtLength(path.getTotalLength()))};"
                "});"
                "const colors=new Set(paths.map(path=>getComputedStyle(path).stroke)).size;"
                "return {ok:paths.length===6&&edgeErrors.every(item=>"
                "item.straight&&item.from<.04&&item.to<.04)&&colors===6,"
                "count:paths.length,colors,edgeErrors};"
                "})()"
            )
            assert geometry["ok"], geometry

            _wait_ui(
                browser,
                (
                    "document.querySelector('#platform-run-state')?.textContent.includes("
                    "'PLAN READY') && document.querySelector('#platform-diagnosis-status')?"
                    ".textContent.includes('PLAN READY')"
                ),
                "agent-platform diagnosis",
            )
            assert browser.evaluate(
                "document.querySelectorAll("
                "'#platform-hypotheses .platform-hypothesis').length === 4"
            )
            browser.evaluate(
                "document.querySelector('#platform-question').value = "
                "'Can the agent release this receipt?'; "
                "document.querySelector('#platform-question-form').requestSubmit()"
            )
            _wait_ui(
                browser,
                "document.querySelector('#platform-answer')?.textContent.includes("
                "'Real Strands Agent is not configured')",
                "explicit unavailable advisory state",
            )
            assert not browser.console_errors()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_browser_completes_human_gated_case_and_exposes_resolution_packet(
    tmp_path: Path,
) -> None:
    platform = AmbiguousCasePlatform(store_path=tmp_path / "case-console.sqlite3")
    try:
        server = DecisionWorkspaceServer(
            ("127.0.0.1", 0),
            ROOT,
            runtime_directory=tmp_path / "runtime",
            agent_platform=platform,
        )
    except PermissionError:
        pytest.skip("the managed test sandbox disallows loopback sockets")
    server.registry.select_incident()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    browser: _CDPBrowser | None = None
    try:
        try:
            browser = _CDPBrowser(_chrome(), tmp_path / "chrome-recovery")
        except (OSError, RuntimeError) as exc:
            pytest.skip(f"headless Chrome is unavailable: {exc}")
        with browser:
            base = f"http://127.0.0.1:{server.server_port}"
            browser.navigate(f"{base}/?view=dashboard&scenario=incident")
            _wait_ui(
                browser,
                (
                    "document.body.dataset.agentPlatform === 'ready' && "
                    "document.querySelectorAll("
                    "'#platform-source-receipts .platform-source-receipt').length === 5"
                ),
                "synthetic case console",
            )
            browser.evaluate("document.querySelector('#tab-agent')?.click()")
            _wait_ui(
                browser,
                "document.body.dataset.view === 'agent' && "
                "document.querySelector('#agent-platform-console')?.hidden === false",
                "investigation workspace",
            )
            _wait_ui(
                browser,
                (
                    "document.querySelector('#platform-outcome-status')?.textContent === "
                    "'MANAGER REVIEW' && "
                    "!document.querySelector('#platform-approve-execute')?.disabled"
                ),
                "manager review gate",
            )
            browser.evaluate("document.querySelector('#platform-approve-execute').click()")
            _wait_ui(
                browser,
                (
                    "document.querySelector('#platform-outcome-status')?.textContent === "
                    "'VERIFIED' && document.querySelector('#platform-resolution-packet')?"
                    ".hidden === false"
                ),
                "verified resolution packet",
            )
            assert browser.evaluate(
                "document.querySelector('#platform-packet-id')?.textContent === "
                "'resolution-m20-4817'"
            )
            assert browser.evaluate(
                "document.querySelector('#platform-state-transition')?.hidden === false"
            )
            assert browser.evaluate("document.querySelector('#platform-approve-execute')?.disabled")
            browser.evaluate("document.querySelector('#tab-dashboard')?.click()")
            _wait_ui(
                browser,
                (
                    "document.body.dataset.view === 'dashboard' && "
                    "document.querySelector('#queue-count')?.textContent === '0' && "
                    "document.querySelector('#recorded-count')?.textContent === '100' && "
                    "document.querySelector('#dashboard-agent-stage')?.textContent === "
                    "'Recovery verified'"
                ),
                "dashboard shares verified case truth",
            )
            assert browser.evaluate(
                "Number(document.querySelector('#dashboard-agent-event-count')?.textContent) > 4"
            )
            assert not browser.console_errors()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_browser_ready_incident_link_recovers_to_registered_normal_case(tmp_path: Path) -> None:
    """A catalog placeholder must not leave a fresh-runtime dashboard empty."""

    try:
        server = DecisionWorkspaceServer(
            ("127.0.0.1", 0),
            ROOT,
            runtime_directory=tmp_path / "fresh-runtime",
        )
    except PermissionError:
        pytest.skip("the managed test sandbox disallows loopback sockets")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    browser: _CDPBrowser | None = None
    try:
        try:
            browser = _CDPBrowser(_chrome(), tmp_path / "chrome-fresh-runtime")
        except (OSError, RuntimeError) as exc:
            pytest.skip(f"headless Chrome is unavailable: {exc}")
        with browser:
            base = f"http://127.0.0.1:{server.server_port}"
            browser.navigate(f"{base}/?view=dashboard&scenario=incident")
            _wait_ui(
                browser,
                (
                    "document.body.dataset.workspaceReady === 'true' || "
                    "document.querySelector('#unavailable')?.hidden === false"
                ),
                "fresh-runtime bootstrap verdict",
            )
            verdict = browser.evaluate(
                "(() => ({"
                "ready: document.body.dataset.workspaceReady === 'true',"
                "unavailable: document.querySelector('#unavailable')?.hidden === false,"
                "units: document.querySelectorAll("
                "'#unit-density-strip .unit-density-cell').length"
                "}))()"
            )
            assert verdict == {"ready": True, "unavailable": False, "units": 100}
            assert not browser.console_errors()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_browser_renders_inflight_sdk_flight_recorder(tmp_path: Path) -> None:
    platform = AmbiguousCasePlatform()
    diagnosed = platform.diagnose()
    run_id = str(diagnosed["agent_run"]["run_id"])
    platform.record_agent_runtime_progress(
        {"sequence": 1, "type": "model.started", "projected_input_tokens": 2432},
        run_id,
    )
    platform.record_agent_runtime_progress(
        {
            "sequence": 2,
            "type": "tool.started",
            "tool": "read_erp_evidence",
            "tool_use_id": "tool-live-1",
        },
        run_id,
    )
    try:
        server = DecisionWorkspaceServer(
            ("127.0.0.1", 0),
            ROOT,
            runtime_directory=tmp_path / "runtime-flight-recorder",
            agent_platform=platform,
        )
    except PermissionError:
        pytest.skip("the managed test sandbox disallows loopback sockets")
    incident = server.registry.select_incident()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    browser: _CDPBrowser | None = None
    try:
        try:
            browser = _CDPBrowser(_chrome(), tmp_path / "chrome-flight-recorder")
        except (OSError, RuntimeError) as exc:
            pytest.skip(f"headless Chrome is unavailable: {exc}")
        with browser:
            browser.navigate(
                f"http://127.0.0.1:{server.server_port}/?view=agent&scenario=incident"
                f"&incident_id={incident.incident_id}"
            )
            _wait_ui(
                browser,
                (
                    "document.querySelector('#platform-runtime-count')?.textContent === "
                    "'2 hooks' && document.querySelectorAll("
                    "'#platform-runtime-trace .platform-runtime-span').length === 2"
                ),
                "in-flight SDK flight recorder",
            )
            assert browser.evaluate(
                "document.querySelector('#platform-runtime-trace')?.textContent.includes("
                "'Reasoning 1') && document.querySelector('#platform-runtime-trace')?"
                ".textContent.includes('erp evidence')"
            )
            assert not browser.console_errors()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
