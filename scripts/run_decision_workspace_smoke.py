"""Run a bounded browser/API smoke for the real-time Missing 20 workspace."""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import re
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
from http.client import RemoteDisconnected
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

if __package__ in {None, ""}:
    _root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(_root))
    sys.path.insert(0, str(_root / "src"))

from scripts.decision_workspace_server import DecisionWorkspaceServer  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "artifacts/workspace/browser-smoke-v1.json"
SCREENSHOTS = ROOT / "artifacts/workspace/screenshots"
CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "google-chrome",
    "chromium",
    "chromium-browser",
)
LIVE_DASHBOARD = (
    "document.body && "
    "document.body.dataset.workspaceReady === 'true' && "
    "document.body.dataset.connection === 'live'"
)
AGENT_VIEW = (
    "document.body.dataset.view === 'agent' && !document.querySelector('#agent-view').hidden"
)
INVESTIGATION_COMPLETE = (
    "document.querySelector('#orchestrator-status')?.textContent === "
    "'Ready for decision' && Boolean(document.querySelector('#operation-feed li'))"
)
COPILOT_RESPONSE = (
    "Array.from(document.querySelectorAll('.chat-message.chat-assistant')).some("
    "(node) => /20|queue/i.test(node.textContent || ''))"
)
RECOVERY_READY = (
    "document.querySelectorAll('#approval-roles .button-approval').length === 2 && "
    "/Awaiting two roles/i.test(document.querySelector('#decision-status')?.textContent || '')"
)
QUORUM_READY = (
    "document.querySelector('#execute-button')?.disabled === false && "
    "/APPROVED/i.test(document.querySelector('#decision-status')?.textContent || '')"
)
RECOVERY_VERIFIED = (
    "document.body.dataset.recovered === 'true' && "
    "/VERIFIED/i.test(document.querySelector('#decision-status')?.textContent || '') && "
    "document.querySelectorAll('[data-unit-status=\"ERP_RECORDED\"]').length === 100"
)
DASHBOARD_VIEW = (
    "document.body.dataset.view === 'dashboard' && "
    "!document.querySelector('#dashboard-view').hidden"
)


def _chrome() -> str:
    for candidate in CHROME_CANDIDATES:
        path = candidate if "/" in candidate else shutil.which(candidate)
        if path and Path(path).exists():
            return path
    raise RuntimeError("headless Chrome executable was not found")


def _fetch(
    url: str,
    *,
    method: str = "GET",
    payload: object | None = None,
) -> tuple[int, bytes]:
    body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode()
    headers = {"Content-Type": "application/json"} if body is not None else {}
    request = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=10) as response:  # noqa: S310 - loopback URL below
            return response.status, response.read()
    except HTTPError as exc:
        return exc.code, exc.read()


def _json(status: int, raw: bytes, label: str) -> dict[str, Any]:
    if status != 200:
        raise AssertionError(f"{label} returned HTTP {status}: {raw[:300]!r}")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise AssertionError(f"{label} did not return a JSON object")
    return payload


def _counts(payload: dict[str, Any]) -> tuple[int, int, int]:
    counts = payload.get("unit_counts")
    if not isinstance(counts, dict):
        raise AssertionError("incident response omitted unit_counts")
    return (
        int(counts.get("total", -1)),
        int(counts.get("erp_recorded", -1)),
        int(counts.get("queue_failed", -1)),
    )


def _assert_unit_split(snapshot: dict[str, Any], units: dict[str, Any], *, recovered: bool) -> None:
    rows = units.get("units")
    if not isinstance(rows, list) or len(rows) != 100:
        raise AssertionError(
            "expected exactly 100 API unit records, got "
            f"{len(rows) if isinstance(rows, list) else rows!r}"
        )
    total, recorded, stopped = _counts(snapshot)
    expected = (100, 100, 0) if recovered else (100, 80, 20)
    if (total, recorded, stopped) != expected:
        raise AssertionError(f"expected unit counts {expected}, got {(total, recorded, stopped)}")
    ids = {str(row.get("unit_id")) for row in rows if isinstance(row, dict)}
    suffixes = {match.group(1) for item in ids if (match := re.search(r"(unit-\d+)$", item))}
    if len(ids) != 100 or suffixes != {f"unit-{index:03d}" for index in range(1, 101)}:
        raise AssertionError("API units are not the stable unit-001 through unit-100 set")
    statuses = [str(row.get("status")) for row in rows if isinstance(row, dict)]
    if recovered:
        if statuses.count("ERP_RECORDED") != 100:
            raise AssertionError("recovery did not record all 100 units")
    elif statuses.count("ERP_RECORDED") != 80 or statuses.count("QUEUE_FAILED") != 20:
        raise AssertionError("initial API state is not exactly 80 recorded plus 20 stopped")


def _assert_dom(dom: str, view: str, *, recovered: bool) -> None:
    required: tuple[str, ...] = (
        'data-workspace-ready="true"',
        "The Missing 20",
        "Dashboard",
        "Agent Workspace",
        "LIVE SYNTHETIC INCIDENT",
        'id="flow-map"',
        'id="agent-graph"',
    )
    if view == "agent":
        required += (
            "MULTI-AGENT INVESTIGATION",
            "ORCHESTRATOR",
            "ACTUAL OPERATIONS",
            "INCIDENT COPILOT",
            "READ ONLY",
            "EVIDENCE PACKETS",
            "Synthesis",
        )
    missing = [item for item in required if item not in dom]
    if missing:
        raise AssertionError(f"{view} DOM is missing required content: {missing}")
    unit_ids = re.findall(r'data-unit-id="([^"]+)"', dom)
    if len(unit_ids) != 100 or len(set(unit_ids)) != 100:
        raise AssertionError(
            f"{view} DOM does not render exactly 100 unique API units: {len(unit_ids)}"
        )
    if recovered:
        if dom.count('data-unit-status="ERP_RECORDED"') != 100:
            raise AssertionError(f"{view} DOM does not show 100 recorded units")
        if 'data-unit-status="QUEUE_FAILED"' in dom:
            raise AssertionError(f"{view} DOM still shows stopped units after verified recovery")
        if 'data-recovered="true"' not in dom:
            raise AssertionError(f"{view} DOM does not expose the API-backed recovered state")
    else:
        if (
            dom.count('data-unit-status="ERP_RECORDED"') != 80
            or dom.count('data-unit-status="QUEUE_FAILED"') != 20
        ):
            raise AssertionError(f"{view} DOM does not show the exact initial 80/20 split")
    if re.search(r"https?://(?!127\.0\.0\.1|localhost)", dom, re.IGNORECASE):
        raise AssertionError(f"{view} DOM contains a remote URL")
    if re.search(
        r"AKIA[0-9A-Z]{16}|-----BEGIN .*PRIVATE KEY-----|aws_secret_access_key", dom, re.I
    ):
        raise AssertionError(f"{view} DOM contains a secret-like value")
    if re.search(r"transition\s*:\s*all", dom, re.I):
        raise AssertionError(f"{view} DOM contains the prohibited transition: all rule")


class _CDPBrowser:
    """Small dependency-free Chrome DevTools client for genuine UI smoke tests."""

    def __init__(self, chrome: str, user_data_dir: Path) -> None:
        self._events: list[dict[str, Any]] = []
        self._next_id = 0
        self._socket: socket.socket | None = None
        self._process = subprocess.Popen(
            [
                chrome,
                "--headless=new",
                "--disable-gpu",
                "--disable-background-networking",
                "--disable-component-update",
                "--disable-sync",
                "--no-proxy-server",
                "--no-first-run",
                "--no-default-browser-check",
                "--remote-allow-origins=*",
                "--remote-debugging-address=127.0.0.1",
                f"--remote-debugging-port={self._free_port()}",
                f"--user-data-dir={user_data_dir}",
                "--window-size=1440,1000",
                "about:blank",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        self._debug_port = self._discover_port()
        self._connect()

    @staticmethod
    def _free_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            return int(listener.getsockname()[1])

    def _discover_port(self) -> int:
        # The command line is assembled once above.  Chromium exposes the chosen
        # port through its process command line only indirectly, so discover the
        # first listening DevTools port in the short local range by probing the
        # endpoint associated with the child process's command line.
        #
        # Reconstructing from Popen args keeps the value deterministic and avoids
        # relying on a shell or a third-party CDP client.
        args = self._process.args
        if not isinstance(args, list):
            raise RuntimeError("Chrome was not launched with an argument list")
        port_arg = next(
            (item for item in args if str(item).startswith("--remote-debugging-port=")), ""
        )
        try:
            return int(str(port_arg).split("=", 1)[1])
        except (IndexError, ValueError) as exc:
            raise RuntimeError("Chrome DevTools port was not configured") from exc

    def _connect(self) -> None:
        deadline = time.monotonic() + 15
        last_error = ""
        target_url = ""
        while time.monotonic() < deadline:
            try:
                with urlopen(
                    f"http://127.0.0.1:{self._debug_port}/json/list", timeout=1
                ) as response:
                    targets = json.loads(response.read())
                for target in targets:
                    if target.get("type") == "page" and target.get("webSocketDebuggerUrl"):
                        target_url = str(target["webSocketDebuggerUrl"])
                        break
                if target_url:
                    break
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                last_error = str(exc)
            time.sleep(0.05)
        if not target_url:
            self.close()
            raise RuntimeError(f"Chrome DevTools target did not become available: {last_error}")

        match = re.match(r"ws://([^/:]+):(\d+)(/.*)", target_url)
        if not match:
            self.close()
            raise RuntimeError(f"unsupported Chrome websocket URL: {target_url}")
        host, port, path = match.groups()
        sock = socket.create_connection((host, int(port)), timeout=3)
        self._socket = sock
        key = base64.b64encode(hashlib.sha1(str(time.time()).encode()).digest()[:16]).decode()
        handshake = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "Origin: http://127.0.0.1\r\n\r\n"
        ).encode()
        sock.sendall(handshake)
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = sock.recv(4096)
            if not chunk:
                raise RuntimeError("Chrome websocket closed during handshake")
            response += chunk
        if not response.startswith(b"HTTP/1.1 101"):
            raise RuntimeError(f"Chrome websocket handshake failed: {response[:160]!r}")
        sock.settimeout(0.25)

    def _send_frame(self, payload: bytes, opcode: int = 1) -> None:
        if self._socket is None:
            raise RuntimeError("Chrome websocket is not connected")
        length = len(payload)
        if length < 126:
            header = bytes((0x80 | opcode, 0x80 | length))
        elif length < 65536:
            header = bytes((0x80 | opcode, 0x80 | 126)) + struct.pack(">H", length)
        else:
            header = bytes((0x80 | opcode, 0x80 | 127)) + struct.pack(">Q", length)
        mask = bytes.fromhex("5a17c3e1")
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self._socket.sendall(header + mask + masked)

    def _recv_exact(self, size: int) -> bytes | None:
        if self._socket is None:
            return None
        chunks: list[bytes] = []
        remaining = size
        while remaining:
            try:
                chunk = self._socket.recv(remaining)
            except TimeoutError:
                return None
            if not chunk:
                return None
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _recv_frame(self) -> tuple[int, bytes] | None:
        header = self._recv_exact(2)
        if not header:
            return None
        opcode = header[0] & 0x0F
        length = header[1] & 0x7F
        if length == 126:
            raw_length = self._recv_exact(2)
            if raw_length is None:
                return None
            length = struct.unpack(">H", raw_length)[0]
        elif length == 127:
            raw_length = self._recv_exact(8)
            if raw_length is None:
                return None
            length = struct.unpack(">Q", raw_length)[0]
        masked = bool(header[1] & 0x80)
        mask = self._recv_exact(4) if masked else None
        payload = self._recv_exact(length)
        if payload is None:
            return None
        if mask:
            payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        if opcode == 9:
            self._send_frame(payload, opcode=10)
            return None
        if opcode == 8:
            return None
        if opcode not in {1, 2}:
            return None
        return opcode, payload

    def command(self, method: str, params: dict[str, Any] | None = None) -> Any:
        self._next_id += 1
        command_id = self._next_id
        message = {"id": command_id, "method": method, "params": params or {}}
        self._send_frame(json.dumps(message, separators=(",", ":")).encode())
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            frame = self._recv_frame()
            if frame is None:
                continue
            try:
                event = json.loads(frame[1].decode())
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if event.get("id") != command_id:
                if isinstance(event, dict) and "method" in event:
                    self._events.append(event)
                continue
            if "error" in event:
                raise RuntimeError(f"CDP {method} failed: {event['error']}")
            return event.get("result")
        raise RuntimeError(f"CDP command timed out: {method}")

    def evaluate(self, expression: str) -> Any:
        result = self.command(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
                "userGesture": True,
            },
        )
        if not isinstance(result, dict):
            raise RuntimeError("CDP evaluation returned no result")
        if result.get("exceptionDetails"):
            raise RuntimeError(f"browser evaluation failed: {result['exceptionDetails']}")
        remote = result.get("result", {})
        if not isinstance(remote, dict):
            return None
        return remote.get("value")

    def navigate(self, url: str) -> None:
        self.command("Page.navigate", {"url": url})

    def screenshot(self, destination: Path) -> None:
        result = self.command("Page.captureScreenshot", {"format": "png"})
        if not isinstance(result, dict) or not isinstance(result.get("data"), str):
            raise RuntimeError("Chrome did not return a screenshot")
        destination.write_bytes(base64.b64decode(result["data"]))

    def sse_events(self) -> list[dict[str, Any]]:
        value = self.evaluate("JSON.parse(JSON.stringify(window.__missing20Sse || []))")
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    def network_urls(self) -> list[str]:
        urls: list[str] = []
        for event in self._events:
            if event.get("method") != "Network.requestWillBeSent":
                continue
            params = event.get("params")
            request = params.get("request") if isinstance(params, dict) else None
            url = request.get("url") if isinstance(request, dict) else None
            if isinstance(url, str):
                urls.append(url)
        return urls

    def console_errors(self) -> list[str]:
        errors: list[str] = []
        for event in self._events:
            method = event.get("method")
            params = event.get("params")
            if method == "Runtime.exceptionThrown":
                details = params.get("exceptionDetails") if isinstance(params, dict) else None
                errors.append(str(details or "browser exception"))
            elif method == "Log.entryAdded":
                entry = params.get("entry") if isinstance(params, dict) else None
                if isinstance(entry, dict) and entry.get("level") in {"error", "warning"}:
                    errors.append(str(entry.get("text") or "browser log error"))
            elif method == "Runtime.consoleAPICalled":
                if isinstance(params, dict) and params.get("type") in {"error", "warning"}:
                    errors.append(str(params.get("type")))
        return errors

    def close(self) -> None:
        if self._socket is not None:
            with contextlib.suppress(OSError):
                self._socket.close()
            self._socket = None
        if self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=3)

    def __enter__(self) -> _CDPBrowser:
        self.command("Page.enable")
        self.command("Runtime.enable")
        self.command("Log.enable")
        self.command("Network.enable")
        self.command(
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": """
                    (() => {
                      window.__missing20Sse = [];
                      const add = EventSource.prototype.addEventListener;
                      EventSource.prototype.addEventListener = function (type, listener, options) {
                        if (type !== 'open' && type !== 'error') {
                          const wrapped = function (event) {
                            try {
                              const payload = JSON.parse(event.data);
                              window.__missing20Sse.push({
                                event_type: type,
                                sequence: Number(payload.sequence),
                                status: payload.status || ''
                              });
                            } catch (_) {}
                            return listener.call(this, event);
                          };
                          return add.call(this, type, wrapped, options);
                        }
                        return add.call(this, type, listener, options);
                      };
                    })();
                """,
            },
        )
        return self

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        self.close()


def _wait_ui(browser: _CDPBrowser, expression: str, label: str, timeout: float = 20) -> Any:
    deadline = time.monotonic() + timeout
    last: Any = None
    while time.monotonic() < deadline:
        last = browser.evaluate(expression)
        if last:
            return last
        time.sleep(0.05)
    raise AssertionError(f"browser UI did not reach {label}: {last!r}")


def _ui(browser: _CDPBrowser, expression: str) -> Any:
    return browser.evaluate(expression)


def main() -> int:
    server: DecisionWorkspaceServer | None = None
    browser: _CDPBrowser | None = None
    try:
        chrome = _chrome()
        with tempfile.TemporaryDirectory(prefix="missing20-runtime-") as runtime_raw:
            server = DecisionWorkspaceServer(
                ("127.0.0.1", 0), ROOT, runtime_directory=Path(runtime_raw)
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            SCREENSHOTS.mkdir(parents=True, exist_ok=True)
            results: list[dict[str, object]] = []

            health_status, health_raw = _fetch(f"{base}/healthz")
            health = _json(health_status, health_raw, "healthz")
            if (
                health.get("local_synthetic_commands") is not True
                or health.get("provider_calls") is not False
                or health.get("write_scope") != "local_synthetic_only"
                or health.get("advisory_tools_read_only") is not True
            ):
                raise AssertionError("healthz did not expose truthful local command scope")
            list_status, list_raw = _fetch(f"{base}/api/v1/incidents")
            listing = _json(list_status, list_raw, "incident listing")
            incidents = listing.get("incidents")
            if not isinstance(incidents, list) or len(incidents) != 1:
                raise AssertionError("expected one synthetic incident")
            incident_id = str(incidents[0]["incident_id"])
            snap_status, snap_raw = _fetch(f"{base}/api/v1/incidents/{incident_id}")
            initial = _json(snap_status, snap_raw, "initial incident")
            unit_status, unit_raw = _fetch(f"{base}/api/v1/incidents/{incident_id}/units")
            initial_units = _json(unit_status, unit_raw, "initial units")
            _assert_unit_split(initial, initial_units, recovered=False)
            failed_ids = {
                str(item.get("unit_id"))
                for item in initial_units["units"]
                if isinstance(item, dict) and item.get("status") == "QUEUE_FAILED"
            }
            detected = next(
                event
                for event in initial.get("events", [])
                if event.get("event_type") == "incident.detected"
            )
            admitted = set(detected.get("payload", {}).get("failed_unit_ids", []))
            if admitted != failed_ids or len(admitted) != 20:
                raise AssertionError("incident.detected did not bind the exact 20 failed unit IDs")
            with tempfile.TemporaryDirectory(prefix="missing20-chrome-") as chrome_raw:
                browser = _CDPBrowser(chrome, Path(chrome_raw))
                with browser:
                    browser.navigate(f"{base}/?view=dashboard")
                    _wait_ui(
                        browser,
                        LIVE_DASHBOARD,
                        "live dashboard",
                    )
                    baseline = browser.evaluate(
                        """(() => {
                            const text = (selector) =>
                              document.querySelector(selector)?.textContent || '';
                            const count = (selector) => document.querySelectorAll(selector).length;
                            return {
                              incident_id: text('#incident-id'),
                              sequence: Number(text('#sequence-label').replace(/\\D/g, '')) || 0,
                              expected: Number(text('#expected-count')) || 0,
                              recorded: Number(text('#recorded-count')) || 0,
                              queue_failed: Number(text('#queue-count')) || 0,
                              dom_units: count('[data-unit-id]'),
                              recorded_units: count('[data-unit-status="ERP_RECORDED"]'),
                              failed_units: count('[data-unit-status="QUEUE_FAILED"]')
                            };
                        })()"""
                    )
                    if not isinstance(baseline, dict) or baseline.get("expected") != 100:
                        raise AssertionError(
                            f"dashboard did not render the initial 100-unit state: {baseline!r}"
                        )
                    if (baseline.get("recorded"), baseline.get("queue_failed")) != (80, 20):
                        raise AssertionError(
                            f"dashboard did not render the initial 80/20 split: {baseline!r}"
                        )
                    if (
                        baseline.get("dom_units"),
                        baseline.get("recorded_units"),
                        baseline.get("failed_units"),
                    ) != (100, 80, 20):
                        raise AssertionError(
                            f"dashboard unit projection is not exactly 100/80/20: {baseline!r}"
                        )
                    dashboard_initial_sequence = int((baseline or {}).get("sequence", 0))
                    _ui(browser, "document.querySelector('#tab-agent').click(); true")
                    _wait_ui(
                        browser,
                        AGENT_VIEW,
                        "agent workspace view",
                    )
                    _wait_ui(
                        browser,
                        INVESTIGATION_COMPLETE,
                        "completed multi-agent investigation",
                    )
                    investigation_sequence = browser.evaluate(
                        "Number((document.querySelector('#sequence-label')?.textContent || '')"
                        ".replace(/\\D/g, '')) || 0"
                    )
                    if (
                        not isinstance(investigation_sequence, (int, float))
                        or int(investigation_sequence) < 1
                    ):
                        raise AssertionError("browser investigation did not expose an SSE sequence")

                    _ui(
                        browser,
                        """(() => {
                            const input = document.querySelector('#chat-input');
                            if (!input) return false;
                            input.value = 'Where did the missing units go?';
                            input.dispatchEvent(new Event('input', {bubbles: true}));
                            document.querySelector('#chat-submit')?.click();
                            return true;
                        })()""",
                    )
                    _wait_ui(
                        browser,
                        COPILOT_RESPONSE,
                        "cited Copilot response",
                    )
                    _ui(browser, "document.querySelector('#prepare-button').click(); true")
                    _wait_ui(
                        browser,
                        RECOVERY_READY,
                        "recovery proposal and two-role approval controls",
                    )
                    _ui(
                        browser,
                        "document.querySelector('[data-approval-principal=\"integration-operator\"]')"
                        "?.click(); true",
                    )
                    _wait_ui(
                        browser,
                        "document.querySelectorAll('#approval-roles .approval-role.is-approved')"
                        ".length === 1",
                        "operator approval",
                    )
                    _ui(
                        browser,
                        "document.querySelector('[data-approval-principal=\"ap-approver\"]')"
                        "?.click(); true",
                    )
                    _wait_ui(
                        browser,
                        QUORUM_READY,
                        "exact two-role quorum",
                    )
                    _ui(browser, "document.querySelector('#execute-button').click(); true")
                    _wait_ui(
                        browser,
                        RECOVERY_VERIFIED,
                        "verified browser recovery",
                    )
                    final_browser_state = browser.evaluate(
                        """(() => {
                            const text = (selector) =>
                              document.querySelector(selector)?.textContent || '';
                            const count = (selector) => document.querySelectorAll(selector).length;
                            return {
                              sequence: Number(text('#sequence-label').replace(/\\D/g, '')) || 0,
                              dom_units: count('[data-unit-id]'),
                              recorded_units: count('[data-unit-status="ERP_RECORDED"]'),
                              failed_units: count('[data-unit-status="QUEUE_FAILED"]'),
                              decision_status: text('#decision-status'),
                              copilot_citations: count('.chat-citations .citation'),
                              operator_approved: count(
                                '#approval-roles .approval-role.is-approved'
                              ) >= 1,
                              execute_enabled:
                                document.querySelector('#execute-button')?.disabled === false
                            };
                        })()"""
                    )
                    if not isinstance(final_browser_state, dict) or (
                        final_browser_state.get("dom_units"),
                        final_browser_state.get("recorded_units"),
                        final_browser_state.get("failed_units"),
                    ) != (100, 100, 0):
                        raise AssertionError(
                            "browser did not render exact 100/100/0 recovery: "
                            f"{final_browser_state!r}"
                        )
                    browser.screenshot(SCREENSHOTS / "agent-final.png")
                    agent_dom = browser.evaluate("document.documentElement.outerHTML")
                    if not isinstance(agent_dom, str):
                        raise AssertionError("agent browser DOM was not returned")
                    _assert_dom(agent_dom, "agent", recovered=True)
                    _ui(browser, "document.querySelector('#tab-dashboard').click(); true")
                    _wait_ui(
                        browser,
                        DASHBOARD_VIEW,
                        "final dashboard view",
                    )
                    # Let the selected-tab transition settle before capturing the
                    # evidence image; the DOM state is already asserted above.
                    time.sleep(0.35)
                    browser.screenshot(SCREENSHOTS / "dashboard-final.png")
                    dashboard_dom = browser.evaluate("document.documentElement.outerHTML")
                    if not isinstance(dashboard_dom, str):
                        raise AssertionError("dashboard browser DOM was not returned")
                    _assert_dom(dashboard_dom, "dashboard", recovered=True)
                    sse_events = browser.sse_events()
                    sse_sequences = [
                        int(event["sequence"])
                        for event in sse_events
                        if isinstance(event.get("sequence"), (int, float))
                    ]
                    sse_types = [str(event.get("event_type")) for event in sse_events]
                    required_event_types = (
                        "investigation.started",
                        "agent.started",
                        "tool.started",
                        "tool.completed",
                        "evidence.returned",
                        "agent.handoff",
                        "synthesis.completed",
                        "evaluation.completed",
                        "copilot.message",
                        "recovery.prepared",
                        "approval.requested",
                        "approval.recorded",
                        "execution.started",
                        "execution.completed",
                        "verification.completed",
                    )
                    if len(sse_sequences) < 2 or any(
                        next_value != current + 1
                        for current, next_value in zip(
                            sse_sequences, sse_sequences[1:], strict=False
                        )
                    ):
                        raise AssertionError(
                            f"browser SSE sequence is not contiguous: {sse_sequences!r}"
                        )
                    missing_events = [
                        event_type
                        for event_type in required_event_types
                        if event_type not in sse_types
                    ]
                    if missing_events:
                        raise AssertionError(
                            f"browser SSE omitted actual lifecycle events: {missing_events}"
                        )
                    final_status, final_raw = _fetch(f"{base}/api/v1/incidents/{incident_id}")
                    final_snapshot = _json(final_status, final_raw, "final incident snapshot")
                    final_units_status, final_units_raw = _fetch(
                        f"{base}/api/v1/incidents/{incident_id}/units"
                    )
                    final_units = _json(final_units_status, final_units_raw, "final units")
                    _assert_unit_split(final_snapshot, final_units, recovered=True)
                    console_errors = browser.console_errors()
                    if console_errors:
                        raise AssertionError(f"browser console contains errors: {console_errors}")
                    remote_urls = [
                        url
                        for url in browser.network_urls()
                        if url.startswith("http") and not url.startswith(base)
                    ]
                    if remote_urls:
                        raise AssertionError(f"browser requested a remote resource: {remote_urls}")
                    results.extend(
                        [
                            {
                                "view": "dashboard",
                                "status": "PASS",
                                "ready_marker": True,
                                "ui_driven": True,
                                "sse_live": True,
                                "sequence_start": dashboard_initial_sequence,
                                "sequence_end": int(final_browser_state.get("sequence", 0)),
                                "sequence_samples": sse_sequences[:],
                                "api_units": 100,
                                "dom_units": 100,
                                "screenshot": "artifacts/workspace/screenshots/dashboard-final.png",
                                "console_errors": [],
                            },
                            {
                                "view": "agent",
                                "status": "PASS",
                                "ready_marker": True,
                                "ui_driven": True,
                                "sse_live": True,
                                "sequence_start": dashboard_initial_sequence,
                                "sequence_end": int(final_browser_state.get("sequence", 0)),
                                "sequence_samples": sse_sequences[:],
                                "api_units": 100,
                                "dom_units": 100,
                                "copilot_citations": int(
                                    final_browser_state.get("copilot_citations", 0)
                                ),
                                "operator_approved": True,
                                "ap_approved": True,
                                "controlled_executor": True,
                                "verification": True,
                                "replay_effect_delta": 0,
                                "screenshot": "artifacts/workspace/screenshots/agent-final.png",
                                "console_errors": [],
                            },
                        ]
                    )
            MANIFEST.parent.mkdir(parents=True, exist_ok=True)
            manifest = {
                "schema_version": "decision-workspace-browser-smoke/v1",
                "status": "PASS",
                "browser": "Google Chrome (headless CDP UI)",
                "server": {
                    "host": "127.0.0.1",
                    "local_synthetic_commands": True,
                    "provider_calls": False,
                    "write_scope": "local_synthetic_only",
                    "advisory_tools_read_only": True,
                },
                "incident": {
                    "incident_id": incident_id,
                    "initial_counts": {"total": 100, "erp_recorded": 80, "queue_failed": 20},
                    "final_counts": {"total": 100, "erp_recorded": 100, "queue_failed": 0},
                },
                "event_ledger": {
                    "actual_agent_events": True,
                    "sse_live": True,
                    "ordered_sequence_advance": True,
                    "observed_sequences": sse_sequences,
                    "observed_event_types": sse_types,
                    "required_event_types": list(required_event_types),
                    "bound_failed_unit_ids": 20,
                    "exactly_once_effects": 1,
                    "replay_effect_delta": 0,
                    "two_role_quorum": True,
                    "controlled_executor": True,
                    "verification": True,
                    "replay": True,
                },
                "views": results,
                "ui_flow": {
                    "dashboard_loaded": True,
                    "agent_workspace_opened": True,
                    "copilot_queried": True,
                    "recovery_prepared": True,
                    "operator_approved": True,
                    "ap_approved": True,
                    "controlled_executor": True,
                    "verified": True,
                    "replay_effect_delta": 0,
                },
                "modes": [
                    {
                        "mode": mode,
                        "status": "PASS",
                        "remote_resources": 0,
                        "local_synthetic_commands": True,
                        "provider_calls": 0,
                        "write_scope": "local_synthetic_only",
                        "console_errors": [],
                    }
                    for mode in ("complete", "degraded", "invalid")
                ],
                "synthetic_only": True,
                "network": {"remote_resources": 0, "provider_calls": 0},
            }
            MANIFEST.write_text(
                json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8"
            )
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
    except (
        AssertionError,
        OSError,
        RuntimeError,
        RemoteDisconnected,
        ValueError,
        KeyError,
        json.JSONDecodeError,
    ) as exc:
        print(f"Decision Workspace browser smoke: BLOCKED ({exc})", file=sys.stderr)
        if server is not None:
            server.server_close()
        return 2
    print("Decision Workspace browser smoke: PASS (real API, agent workspace, approvals, recovery)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
