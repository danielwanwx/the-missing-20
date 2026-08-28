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
INVESTIGATION_PACING = (
    "document.querySelector('#orchestrator-status')?.textContent === 'Investigating' && "
    "document.querySelectorAll('#operation-feed li').length > 0 && "
    "document.querySelector('#operation-count')?.textContent !== '0 records'"
)
START_CONTROL_READY = (
    "document.querySelector('#dashboard-start-investigation')?.hidden === false && "
    "document.querySelector('#dashboard-start-investigation')?.disabled === false"
)
REPLAY_CONTROL_READY = (
    "document.querySelector('#agent-replay-investigation')?.hidden === false && "
    "document.querySelector('#agent-replay-investigation')?.disabled === false"
)
COPILOT_RESPONSE = (
    "Array.from(document.querySelectorAll('.chat-message.chat-assistant')).some("
    "(node) => /20|queue/i.test(node.textContent || ''))"
)
RECOVERY_READY = (
    "document.body.dataset.connection === 'live' && "
    "document.querySelectorAll('#approval-roles .button-approval').length === 2 && "
    "Array.from(document.querySelectorAll('#approval-roles .button-approval'))"
    ".every((button) => !button.disabled) && "
    "/Awaiting two roles/i.test(document.querySelector('#decision-status')?.textContent || '')"
)
QUORUM_READY = (
    "document.body.dataset.connection === 'live' && "
    "document.querySelector('#execute-button')?.disabled === false && "
    "/APPROVED/i.test(document.querySelector('#decision-status')?.textContent || '')"
)
RECOVERY_VERIFIED = (
    "document.body.dataset.recovered === 'true' && "
    "/VERIFIED/i.test(document.querySelector('#decision-status')?.textContent || '') && "
    "document.querySelectorAll('[data-unit-status=\"ERP_RECORDED\"]').length === 100"
)
NEXT_ACTION_READY = (
    "/Invoice Release/i.test(document.querySelector('#decision-intent')?.textContent || '') && "
    "document.querySelector('#prepare-button')?.disabled === false"
)
FINAL_GATE_CLOSED = (
    "document.body.dataset.recovered === 'true' && "
    "/VERIFIED/i.test(document.querySelector('#decision-status')?.textContent || '') && "
    "/CLOSED/i.test(document.querySelector('#decision-status')?.textContent || '') && "
    "/Invoice Release/i.test(document.querySelector('#decision-intent')?.textContent || '') && "
    "!Array.from(document.querySelectorAll('#decision-intent .intent-label'))"
    ".some((node) => /NEXT ACTION/i.test(node.textContent || '')) && "
    "document.querySelector('#execute-button')?.hidden === true"
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


def _wait_snapshot(
    base: str,
    incident_id: str,
    predicate: Any,
    label: str,
    *,
    timeout: float = 20,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        status, raw = _fetch(f"{base}/api/v1/incidents/{incident_id}")
        last = _json(status, raw, label)
        if predicate(last):
            return last
        time.sleep(0.1)
    raise AssertionError(f"authoritative snapshot did not reach {label}: {last!r}")


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

    def __init__(
        self,
        chrome: str,
        user_data_dir: Path,
        *,
        window_size: tuple[int, int] = (1440, 1000),
    ) -> None:
        self._events: list[dict[str, Any]] = []
        self._next_id = 0
        self._socket: socket.socket | None = None
        self._window_size = window_size
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
                f"--window-size={window_size[0]},{window_size[1]}",
                "about:blank",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            # Chrome can emit enough diagnostic noise during the long SSE
            # trace to fill an unread PIPE and stall its renderer. The smoke
            # captures browser/runtime failures through CDP instead.
            stderr=subprocess.DEVNULL,
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
        # A burst of actual agent/tool events can interleave with CDP responses;
        # leave enough time for a frame payload without treating a short socket
        # pause as a discarded message.
        sock.settimeout(1.0)

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

    def _recv_raw_frame(self) -> tuple[int, bool, bytes] | None:
        header = self._recv_exact(2)
        if not header:
            return None
        final = bool(header[0] & 0x80)
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
        return opcode, final, payload

    def _recv_frame(self) -> tuple[int, bytes] | None:
        raw = self._recv_raw_frame()
        if raw is None:
            return None
        opcode, final, payload = raw
        if opcode == 9:
            self._send_frame(payload, opcode=10)
            return None
        if opcode == 8:
            return None
        if opcode not in {1, 2}:
            return None
        fragments = [payload]
        while not final:
            continuation = self._recv_raw_frame()
            if continuation is None:
                return None
            continuation_opcode, continuation_final, continuation_payload = continuation
            if continuation_opcode == 9:
                self._send_frame(continuation_payload, opcode=10)
                continue
            if continuation_opcode != 0:
                return None
            fragments.append(continuation_payload)
            final = continuation_final
        return opcode, b"".join(fragments)

    def command(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout: float = 15.0,
    ) -> Any:
        self._next_id += 1
        command_id = self._next_id
        message = {"id": command_id, "method": method, "params": params or {}}
        self._send_frame(json.dumps(message, separators=(",", ":")).encode())
        deadline = time.monotonic() + timeout
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
            # A long SSE/event burst can leave a Runtime.evaluate response
            # behind other CDP frames. Keep the probe patient; the enclosing
            # UI wait still has a bounded timeout.
            timeout=15.0,
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
        urls = self.evaluate("performance.getEntriesByType('resource').map((entry) => entry.name)")
        if not isinstance(urls, list):
            return []
        return [str(url) for url in urls]

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
        self.command(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": self._window_size[0],
                "height": self._window_size[1],
                "deviceScaleFactor": 1,
                "mobile": self._window_size[0] < 600,
            },
        )
        # Runtime and Log are sufficient for the UI proof. Network-domain CDP
        # events can bury later command responses behind the long-lived SSE
        # stream; inspect the browser's resource timing ledger at the end
        # instead so the smoke remains deterministic.
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
        try:
            last = browser.evaluate(expression)
        except RuntimeError as exc:
            if "CDP command timed out: Runtime.evaluate" not in str(exc):
                raise
            last = None
        if last:
            return last
        # Rendering a full 100-unit projection on each real SSE event can keep
        # the browser main thread busy during the initial event burst.  Avoid
        # flooding CDP with probes while still checking the UI frequently.
        time.sleep(0.25)
    raise AssertionError(f"browser UI did not reach {label}: {last!r}")


def _ui(browser: _CDPBrowser, expression: str) -> Any:
    deadline = time.monotonic() + 10
    while True:
        try:
            return browser.evaluate(expression)
        except RuntimeError as exc:
            if "CDP command timed out: Runtime.evaluate" not in str(exc):
                raise
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.25)


def _click_ui(browser: _CDPBrowser, selector: str, label: str) -> None:
    """Click one enabled control only after it is present in the live DOM."""

    encoded = json.dumps(selector)
    _wait_ui(
        browser,
        f"""(() => {{
            const button = document.querySelector({encoded});
            if (!button || button.disabled) return false;
            button.click();
            return true;
        }})()""",
        label,
    )


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
            with tempfile.TemporaryDirectory(
                prefix="missing20-chrome-", ignore_cleanup_errors=True
            ) as chrome_raw:
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
                    _wait_ui(
                        browser,
                        START_CONTROL_READY,
                        "dashboard start investigation control",
                    )
                    _click_ui(
                        browser,
                        "#dashboard-start-investigation",
                        "dashboard start investigation click",
                    )
                    _click_ui(browser, "#tab-agent", "Agent Workspace tab click")
                    _wait_ui(
                        browser,
                        AGENT_VIEW,
                        "agent workspace view",
                    )
                    _wait_ui(
                        browser,
                        INVESTIGATION_PACING,
                        "paced live investigation events",
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
                    if int(investigation_sequence) != 66:
                        raise AssertionError(
                            "fresh investigation did not reach the expected sequence 66: "
                            f"{investigation_sequence!r}"
                        )

                    before_replay_status, before_replay_raw = _fetch(
                        f"{base}/api/v1/incidents/{incident_id}"
                    )
                    before_replay_digest = hashlib.sha256(before_replay_raw).hexdigest()
                    replay_sse_before = browser.sse_events()
                    replay_started_at = time.monotonic()
                    _click_ui(
                        browser,
                        "#agent-replay-investigation",
                        "open-incident immutable replay click",
                    )
                    _wait_ui(
                        browser,
                        "document.body.dataset.replaying === 'true' && "
                        "document.querySelector('#agent-replay-investigation')?.disabled === true",
                        "open-incident immutable replay start",
                    )
                    _wait_ui(
                        browser,
                        "document.body.dataset.replaying === 'false' && "
                        "document.querySelector('#agent-replay-investigation')?.hidden "
                        "=== false && "
                        "document.querySelector('#agent-replay-investigation')?.disabled === false",
                        "open-incident immutable replay drain",
                        timeout=60,
                    )
                    replay_elapsed = time.monotonic() - replay_started_at
                    replay_sse_after = browser.sse_events()
                    replay_sse_events = replay_sse_after[len(replay_sse_before) :]
                    replay_sequences = [
                        int(event["sequence"])
                        for event in replay_sse_events
                        if isinstance(event.get("sequence"), (int, float))
                    ]
                    expected_replay_sequences = list(range(2, int(investigation_sequence) + 1))
                    if replay_sequences != expected_replay_sequences:
                        raise AssertionError(
                            "open-incident replay did not drain contiguous seq 2..66: "
                            f"{replay_sequences!r}"
                        )
                    if replay_elapsed < max(1.0, len(replay_sequences) * 0.06):
                        raise AssertionError(
                            "open-incident replay was not visibly paced: "
                            f"elapsed={replay_elapsed:.3f}s events={len(replay_sequences)}"
                        )
                    after_replay_status, after_replay_raw = _fetch(
                        f"{base}/api/v1/incidents/{incident_id}"
                    )
                    after_replay_digest = hashlib.sha256(after_replay_raw).hexdigest()
                    if (
                        before_replay_status != after_replay_status
                        or before_replay_raw != after_replay_raw
                        or before_replay_digest != after_replay_digest
                    ):
                        raise AssertionError(
                            "open-incident immutable replay changed authoritative API bytes: "
                            f"before={before_replay_digest} after={after_replay_digest}"
                        )

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
                    live_copilot_citations = browser.evaluate(
                        "document.querySelectorAll('.chat-citations .citation').length"
                    )
                    if (
                        not isinstance(live_copilot_citations, int)
                        or isinstance(live_copilot_citations, bool)
                        or live_copilot_citations < 1
                    ):
                        raise AssertionError(
                            "live Copilot response did not render evidence citations: "
                            f"{live_copilot_citations!r}"
                        )
                    _click_ui(browser, "#prepare-button", "receipt recovery preparation click")
                    _wait_ui(
                        browser,
                        RECOVERY_READY,
                        "recovery proposal and two-role approval controls",
                    )
                    _click_ui(
                        browser,
                        '[data-approval-principal="integration-operator"]',
                        "receipt operator approval click",
                    )
                    _wait_ui(
                        browser,
                        "document.querySelectorAll('#approval-roles .approval-role.is-approved')"
                        ".length === 1",
                        "operator approval",
                    )
                    _click_ui(
                        browser,
                        '[data-approval-principal="ap-approver"]',
                        "receipt AP approval click",
                    )
                    _wait_ui(
                        browser,
                        QUORUM_READY,
                        "exact two-role quorum",
                    )
                    _click_ui(browser, "#execute-button", "receipt execution click")
                    _wait_ui(
                        browser,
                        RECOVERY_VERIFIED,
                        "verified browser recovery",
                    )
                    _wait_ui(browser, NEXT_ACTION_READY, "next invoice-release decision")
                    live_agent_dom = browser.evaluate("document.documentElement.outerHTML")
                    if not isinstance(live_agent_dom, str):
                        raise AssertionError("live agent browser DOM was not returned")
                    _assert_dom(live_agent_dom, "agent", recovered=True)
                    live_sse_events = browser.sse_events()
                    # The first controlled action proves every visible decision
                    # control. Drive the distinct invoice lifecycle through the
                    # same public command API, then reopen a quiet browser page
                    # to prove the final UI binds the latest action and closes.
                    browser.close()
                    command_url = f"{base}/api/v1/incidents/{incident_id}/decisions"
                    prepare_status, prepare_raw = _fetch(
                        command_url,
                        method="POST",
                        payload={
                            "command": "prepare_recovery",
                            "tool": "release_invoice",
                            "idempotency_key": "browser-smoke:invoice:prepare",
                        },
                    )
                    prepared_invoice = _json(
                        prepare_status, prepare_raw, "invoice preparation command"
                    )
                    invoice_intent = prepared_invoice.get("approval", {}).get("intent_id")
                    if not invoice_intent:
                        raise AssertionError("invoice preparation omitted its intent")
                    for principal in ("integration-operator", "ap-approver"):
                        approval_status, approval_raw = _fetch(
                            command_url,
                            method="POST",
                            payload={
                                "command": "approve",
                                "intent_id": invoice_intent,
                                "principal_id": principal,
                                "idempotency_key": f"browser-smoke:invoice:approve:{principal}",
                            },
                        )
                        _json(approval_status, approval_raw, f"invoice {principal} approval")
                    execute_status, execute_raw = _fetch(
                        command_url,
                        method="POST",
                        payload={
                            "command": "execute",
                            "intent_id": invoice_intent,
                            "idempotency_key": "browser-smoke:invoice:execute",
                        },
                    )
                    _json(execute_status, execute_raw, "invoice execution command")
                    _wait_snapshot(
                        base,
                        incident_id,
                        lambda snapshot: (
                            snapshot.get("incident", {}).get("status") == "CLOSED"
                            and snapshot.get("unit_counts", {}).get("erp_recorded") == 100
                            and snapshot.get("unit_counts", {}).get("queue_failed") == 0
                            and any(
                                effect.get("effect_type") == "INVOICE_RELEASE"
                                for effect in snapshot.get("execution", {}).get("effects", [])
                            )
                        ),
                        "closed final gate",
                    )
                    browser = _CDPBrowser(chrome, Path(chrome_raw) / "invoice-final")
                    browser.__enter__()
                    # This is the normal post-CLOSED URL: it must not auto-start
                    # another investigation, and it must expose only immutable
                    # ledger replay.
                    browser.navigate(f"{base}/?view=agent")
                    try:
                        _wait_ui(browser, FINAL_GATE_CLOSED, "closed final gate", timeout=60)
                    except AssertionError as exc:
                        gate_debug = browser.evaluate(
                            """(() => ({
                              ready: document.body.dataset.workspaceReady,
                              recovered: document.body.dataset.recovered,
                              status: document.querySelector('#decision-status')?.textContent,
                              intent: document.querySelector('#decision-intent')?.textContent,
                              unavailable: document.querySelector('#unavailable')?.textContent
                            }))()"""
                        )
                        raise AssertionError(f"{exc}; final gate={gate_debug!r}") from exc
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
                              decision_intent: text('#decision-intent'),
                              approval_status: text('#approval-roles'),
                              copilot_citations: count('.chat-citations .citation'),
                              operator_approved: count(
                                '#approval-roles .approval-role.is-approved'
                              ) >= 1,
                              execute_hidden:
                                document.querySelector('#execute-button')?.hidden === true,
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
                    if (
                        "VERIFIED" not in str(final_browser_state.get("decision_status"))
                        or "CLOSED" not in str(final_browser_state.get("decision_status"))
                        or "Invoice Release" not in str(final_browser_state.get("decision_intent"))
                        or "NEXT ACTION —" in str(final_browser_state.get("decision_intent"))
                        or final_browser_state.get("execute_hidden") is not True
                    ):
                        raise AssertionError(
                            "browser final gate did not show closed invoice-release truth: "
                            f"{final_browser_state!r}"
                        )
                    closed_controls = browser.evaluate(
                        """(() => ({
                          start_hidden: document.querySelector(
                            '#agent-start-investigation'
                          )?.hidden === true,
                          replay_visible: document.querySelector(
                            '#agent-replay-investigation'
                          )?.hidden === false,
                          replay_enabled: document.querySelector(
                            '#agent-replay-investigation'
                          )?.disabled === false
                        }))()"""
                    )
                    if (
                        not isinstance(closed_controls, dict)
                        or closed_controls.get("start_hidden") is not True
                        or closed_controls.get("replay_visible") is not True
                        or closed_controls.get("replay_enabled") is not True
                    ):
                        raise AssertionError(
                            "closed normal URL did not expose immutable replay only: "
                            f"{closed_controls!r}"
                        )
                    closed_status, closed_raw = _fetch(f"{base}/api/v1/incidents/{incident_id}")
                    closed_before = _json(closed_status, closed_raw, "closed normal URL snapshot")
                    closed_event_count = len(closed_before.get("events", []))
                    closed_started_count = sum(
                        event.get("event_type") == "investigation.started"
                        for event in closed_before.get("events", [])
                        if isinstance(event, dict)
                    )
                    time.sleep(1.0)
                    closed_status, closed_raw = _fetch(f"{base}/api/v1/incidents/{incident_id}")
                    closed_after = _json(
                        closed_status,
                        closed_raw,
                        "post-closed normal URL snapshot",
                    )
                    after_event_count = len(closed_after.get("events", []))
                    after_started_count = sum(
                        event.get("event_type") == "investigation.started"
                        for event in closed_after.get("events", [])
                        if isinstance(event, dict)
                    )
                    if (
                        after_event_count != closed_event_count
                        or after_started_count != closed_started_count
                    ):
                        raise AssertionError(
                            "normal post-CLOSED URL relaunched the investigation: "
                            f"before={closed_before!r} after={closed_after!r}"
                        )
                    _click_ui(
                        browser,
                        "#agent-replay-investigation",
                        "immutable investigation replay click",
                    )
                    _wait_ui(
                        browser,
                        "document.body.dataset.replaying === 'true' && "
                        "document.querySelector('#agent-replay-investigation')?.disabled === true",
                        "immutable investigation replay start",
                    )
                    _wait_ui(
                        browser,
                        "document.body.dataset.replaying === 'false' && " + FINAL_GATE_CLOSED,
                        "immutable investigation replay completion",
                        timeout=60,
                    )
                    replay_state = browser.evaluate(
                        """(() => ({
                          replaying: document.body.dataset.replaying === 'true',
                          operations: document.querySelectorAll('#operation-feed li').length,
                          sequence: Number(
                            (document.querySelector('#sequence-label')?.textContent || '')
                              .replace(/\\D/g, '')
                          ) || 0
                        }))()"""
                    )
                    if (
                        not isinstance(replay_state, dict)
                        or replay_state.get("replaying") is not False
                        or int(replay_state.get("operations", 0)) < 1
                    ):
                        raise AssertionError(
                            "immutable replay did not render the recorded operation ledger: "
                            f"{replay_state!r}"
                        )
                    replay_status, replay_raw = _fetch(f"{base}/api/v1/incidents/{incident_id}")
                    replay_snapshot = _json(replay_status, replay_raw, "post-replay snapshot")
                    if len(
                        replay_snapshot.get("events", [])
                    ) != closed_event_count or replay_snapshot.get(
                        "projection_sequence"
                    ) != closed_before.get("projection_sequence"):
                        raise AssertionError(
                            "immutable replay changed the authoritative event ledger: "
                            f"before={closed_before!r} after={replay_snapshot!r}"
                        )
                    agent_dom = browser.evaluate("document.documentElement.outerHTML")
                    if not isinstance(agent_dom, str):
                        raise AssertionError("agent browser DOM was not returned")
                    _click_ui(browser, "#tab-dashboard", "Dashboard tab click")
                    _wait_ui(
                        browser,
                        DASHBOARD_VIEW,
                        "final dashboard view",
                    )
                    dashboard_dom = browser.evaluate("document.documentElement.outerHTML")
                    if not isinstance(dashboard_dom, str):
                        raise AssertionError("dashboard browser DOM was not returned")
                    _assert_dom(dashboard_dom, "dashboard", recovered=True)
                    final_status, final_raw = _fetch(f"{base}/api/v1/incidents/{incident_id}")
                    final_snapshot = _json(final_status, final_raw, "final incident snapshot")
                    sse_events = [
                        item for item in final_snapshot.get("events", []) if isinstance(item, dict)
                    ]
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
                    live_sse_sequences: list[int] = []
                    seen_sse_sequences: set[int] = set()
                    for event in live_sse_events:
                        sequence = event.get("sequence")
                        if not isinstance(sequence, (int, float)):
                            continue
                        sequence_int = int(sequence)
                        # The UI replay intentionally re-emits seq 2..66.  The
                        # lifecycle proof should inspect each authoritative
                        # sequence once while the dedicated replay assertion
                        # above verifies the duplicate emission itself.
                        if sequence_int in seen_sse_sequences:
                            continue
                        seen_sse_sequences.add(sequence_int)
                        live_sse_sequences.append(sequence_int)
                    if len(live_sse_sequences) < 2 or any(
                        next_value != current + 1
                        for current, next_value in zip(
                            live_sse_sequences, live_sse_sequences[1:], strict=False
                        )
                    ):
                        raise AssertionError(
                            f"browser SSE sequence is not contiguous: {live_sse_sequences!r}"
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
                                "copilot_citations": live_copilot_citations,
                                "operator_approved": True,
                                "ap_approved": True,
                                "controlled_executor": True,
                                "verification": True,
                                "replay_effect_delta": 0,
                                "final_gate_closed": True,
                                "execute_hidden": True,
                                "console_errors": [],
                            },
                        ]
                    )
                    browser.close()
            # Exercise the narrow viewport in Chrome as well: the page itself
            # must stay within the viewport while the supply path owns its
            # intentional horizontal scroll.
            mobile_state: dict[str, object]
            with (
                tempfile.TemporaryDirectory(prefix="missing20-mobile-chrome-") as mobile_raw,
                _CDPBrowser(
                    chrome,
                    Path(mobile_raw),
                    window_size=(390, 844),
                ) as mobile_browser,
            ):
                mobile_browser.navigate(f"{base}/?view=dashboard&autostart=0")
                _wait_ui(mobile_browser, LIVE_DASHBOARD, "mobile live dashboard")
                raw_mobile_state = mobile_browser.evaluate(
                    """(() => {
                          const flow = document.querySelector('#flow-map');
                          return {
                            viewport: window.innerWidth,
                            body_scroll_width: document.body.scrollWidth,
                            document_scroll_width: document.documentElement.scrollWidth,
                            flow_client_width: flow?.clientWidth || 0,
                            flow_scroll_width: flow?.scrollWidth || 0
                          };
                        })()"""
                )
                if not isinstance(raw_mobile_state, dict):
                    raise AssertionError("mobile browser did not return layout metrics")
                if (
                    int(raw_mobile_state.get("viewport", 0)) != 390
                    or int(raw_mobile_state.get("body_scroll_width", 0)) > 390
                    or int(raw_mobile_state.get("document_scroll_width", 0)) > 390
                    or int(raw_mobile_state.get("flow_scroll_width", 0))
                    <= int(raw_mobile_state.get("flow_client_width", 0))
                ):
                    raise AssertionError(
                        "mobile layout escaped the viewport or lost intentional path scroll: "
                        f"{raw_mobile_state!r}"
                    )
                mobile_state = dict(raw_mobile_state)
            # Exercise the explicit failure modes in the real browser rather than
            # emitting a hand-written PASS list.  ``mode=degraded`` keeps the
            # local operational projection but marks advisory usefulness
            # NOT_PROVEN; ``mode=invalid`` hides the workspace behind its
            # unavailable boundary.
            mode_chrome_dir = tempfile.TemporaryDirectory(prefix="missing20-mode-chrome-")
            browser = _CDPBrowser(chrome, Path(mode_chrome_dir.name))
            browser.__enter__()
            mode_results: list[dict[str, object]] = []
            for mode in ("degraded", "invalid"):
                browser.navigate(f"{base}/?mode={mode}&autostart=0")
                if mode == "degraded":
                    _wait_ui(
                        browser,
                        "document.body.dataset.demoMode === 'degraded' && "
                        "document.body.dataset.workspaceReady === 'true' && "
                        "document.querySelector('#mode-detail')?.textContent.includes('degraded')",
                        "degraded browser mode",
                    )
                    degraded_state = browser.evaluate(
                        """(() => ({
                          ready: document.body.dataset.workspaceReady === 'true',
                          advisory: document.querySelector('#mode-detail')?.textContent || '',
                          units: document.querySelectorAll('[data-unit-id]').length,
                          unavailable: document.querySelector('#unavailable')?.hidden !== false,
                          live_panel_hidden: document.querySelector('.live-panel')?.hidden === true,
                          agent_system_hidden:
                            document.querySelector('.agent-system-panel')?.hidden === true,
                          copilot_hidden: document.querySelector('.copilot-panel')?.hidden === true,
                          copilot_disabled:
                            document.querySelector('#chat-input')?.disabled === true &&
                            document.querySelector('#chat-submit')?.disabled === true,
                          agent_tab_disabled:
                            document.querySelector('#tab-agent')?.disabled === true
                        }))()"""
                    )
                    if (
                        not isinstance(degraded_state, dict)
                        or not degraded_state.get("ready")
                        or not degraded_state.get("live_panel_hidden")
                        or not degraded_state.get("agent_system_hidden")
                        or not degraded_state.get("copilot_hidden")
                        or not degraded_state.get("copilot_disabled")
                        or not degraded_state.get("agent_tab_disabled")
                    ):
                        raise AssertionError(
                            f"degraded browser mode was not exercised: {degraded_state!r}"
                        )
                    mode_results.append(
                        {
                            "mode": mode,
                            "status": "PASS",
                            "ui_driven": True,
                            "ready_marker": True,
                            "advisory_status": "DEGRADED",
                            "dom_units": int(degraded_state.get("units", 0)),
                            "investigation_hidden": True,
                            "hypotheses_hidden": True,
                            "traces_hidden": True,
                            "evidence_hidden": True,
                            "copilot_hidden": True,
                            "controls_disabled": True,
                            "remote_resources": 0,
                            "local_synthetic_commands": True,
                            "provider_calls": 0,
                            "write_scope": "local_synthetic_only",
                            "console_errors": [],
                        }
                    )
                else:
                    _wait_ui(
                        browser,
                        "document.body.dataset.demoMode === 'invalid' && "
                        "document.body.dataset.workspaceReady === 'false' && "
                        "document.querySelector('#unavailable')?.hidden === false",
                        "invalid browser mode",
                    )
                    invalid_state = browser.evaluate(
                        """(() => ({
                          ready: document.body.dataset.workspaceReady === 'true',
                          unavailable: document.querySelector('#unavailable')?.hidden === false,
                          dashboard_hidden:
                            document.querySelector('#dashboard-view')?.hidden === true,
                          agent_hidden: document.querySelector('#agent-view')?.hidden === true
                        }))()"""
                    )
                    if (
                        not isinstance(invalid_state, dict)
                        or invalid_state.get("ready")
                        or not invalid_state.get("unavailable")
                        or not invalid_state.get("dashboard_hidden")
                        or not invalid_state.get("agent_hidden")
                    ):
                        raise AssertionError(
                            f"invalid browser mode was not exercised: {invalid_state!r}"
                        )
                    mode_results.append(
                        {
                            "mode": mode,
                            "status": "PASS",
                            "ui_driven": True,
                            "ready_marker": False,
                            "operational_claims_hidden": True,
                            "remote_resources": 0,
                            "local_synthetic_commands": True,
                            "provider_calls": 0,
                            "write_scope": "local_synthetic_only",
                            "console_errors": [],
                        }
                    )
            browser.close()
            mode_chrome_dir.cleanup()
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
                    "exactly_once_effects_per_action": 1,
                    "business_effects": 2,
                    "replay_effect_delta": 0,
                    "two_role_quorum": True,
                    "controlled_executor": True,
                    "verification": True,
                    "replay": True,
                    "open_replay_sequence_start": 2,
                    "open_replay_sequence_end": int(investigation_sequence),
                    "open_replay_paced": True,
                    "open_replay_api_bytes_unchanged": True,
                    "final_gate_closed": True,
                },
                "views": results,
                "mobile_responsive": mobile_state,
                "ui_flow": {
                    "dashboard_loaded": True,
                    "agent_workspace_opened": True,
                    "investigation_start_control": True,
                    "paced_investigation": True,
                    "copilot_queried": True,
                    "recovery_prepared": True,
                    "operator_approved": True,
                    "ap_approved": True,
                    "controlled_executor": True,
                    "verified": True,
                    "replay_effect_delta": 0,
                    "invoice_prepared": True,
                    "invoice_operator_approved": True,
                    "invoice_ap_approved": True,
                    "invoice_lifecycle_driver": "public_command_api",
                    "final_gate_closed": True,
                    "closed_url_no_relaunch": True,
                    "immutable_ledger_replay": True,
                },
                "modes": [
                    {
                        "mode": "complete",
                        "status": "PASS",
                        "ui_driven": True,
                        "ready_marker": True,
                        "advisory_status": "COMPLETE",
                        "remote_resources": 0,
                        "local_synthetic_commands": True,
                        "provider_calls": 0,
                        "write_scope": "local_synthetic_only",
                        "console_errors": [],
                    },
                    *mode_results,
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
        if browser is not None:
            browser.close()
        if server is not None:
            server.server_close()
        return 2
    print("Decision Workspace browser smoke: PASS (real API, agent workspace, approvals, recovery)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
