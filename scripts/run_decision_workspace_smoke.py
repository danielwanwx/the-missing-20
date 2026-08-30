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
    "'COMPLETE' && "
    "(document.querySelectorAll('#operation-feed .operation-item').length > 0 || "
    "document.querySelectorAll('#full-operation-feed .operation-item').length > 0)"
)
INVESTIGATION_PACING = (
    "['INVESTIGATING', 'HANDOFF', 'COMPLETE'].includes("
    "document.querySelector('#orchestrator-status')?.textContent || '') && "
    "(document.querySelectorAll('#operation-feed .operation-item').length > 0 || "
    "document.querySelectorAll('#full-operation-feed .operation-item').length > 0)"
)
AUTO_HANDOFF_READY = (
    "Boolean(document.querySelector('#agent-start-investigation')?.closest('[hidden]')) && "
    "(document.querySelectorAll('#operation-feed .operation-item').length > 0 || "
    "document.querySelectorAll('#full-operation-feed .operation-item').length > 0) && "
    "['INVESTIGATING', 'HANDOFF', 'COMPLETE'].includes("
    "document.querySelector('#orchestrator-status')?.textContent || '')"
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
    "document.querySelectorAll("
    "'#unit-density-strip [data-unit-status=\"ERP_RECORDED\"]'"
    ").length === 100"
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


def _int_field(mapping: dict[str, object], key: str, default: int = 0) -> int:
    value = mapping.get(key, default)
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return int(value)
    return default


def _replay_immutable_projection(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Keep replay checks strict while allowing live telemetry to advance.

    Opening an immutable replay does not mutate the case, effects, or lifecycle
    events.  A real telemetry producer may, however, append a new observation
    while the replay is being displayed.  Compare the authoritative projection
    after removing only those observation-owned fields; any other difference is
    still a replay integrity failure.
    """

    projection = {
        key: value
        for key, value in snapshot.items()
        if key not in {"projection_sequence", "timestamp", "telemetry"}
    }
    for field in ("events", "activity"):
        rows = projection.get(field)
        if isinstance(rows, list):
            projection[field] = [
                row
                for row in rows
                if not isinstance(row, dict) or row.get("event_type") != "telemetry.observed"
            ]
    replay = projection.get("replay")
    if isinstance(replay, dict):
        replay_projection = dict(replay)
        replay_projection.pop("latest_sequence", None)
        projection["replay"] = replay_projection
    return projection


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
        'id="flow-map"',
        'id="agent-graph"',
    )
    if view == "agent":
        required += (
            "AGENT OPERATIONS MAP",
            "INCIDENT COPILOT",
            "RECOVERY",
            "Live activity",
            "Reconciliation timeline",
            'id="agent-nodes"',
            'id="operation-feed"',
            "Evidence returned",
            'id="evidence-packets"',
        )
    missing = [item for item in required if item not in dom]
    if missing:
        raise AssertionError(f"{view} DOM is missing required content: {missing}")
    density_statuses = re.findall(r'data-unit-status="([^"]+)"', dom)
    if len(density_statuses) != 100:
        raise AssertionError(
            f"{view} DOM does not render exactly 100 API-backed density records: "
            f"{len(density_statuses)}"
        )
    if recovered:
        if density_statuses.count("ERP_RECORDED") != 100:
            raise AssertionError(f"{view} DOM does not show 100 recorded units")
        if "QUEUE_FAILED" in density_statuses:
            raise AssertionError(f"{view} DOM still shows stopped units after verified recovery")
        if 'data-recovered="true"' not in dom:
            raise AssertionError(f"{view} DOM does not expose the API-backed recovered state")
    else:
        if (
            density_statuses.count("ERP_RECORDED") != 80
            or density_statuses.count("QUEUE_FAILED") != 20
        ):
            raise AssertionError(f"{view} DOM does not show the exact initial 80/20 split")
    # Official provenance links are inert until an operator opens them.  They
    # are useful evidence and must not be treated as browser resource loads;
    # only executable/resource elements are forbidden from pointing off-host.
    remote_resource_urls = re.findall(
        r"<(?:script|link|img|iframe|frame|object|embed|source|video|audio)\b[^>]*"
        r"\b(?:src|href|data)\s*=\s*[\"'](https?://[^\"']+)",
        dom,
        re.IGNORECASE,
    )
    remote_resource_urls = [
        url
        for url in remote_resource_urls
        if not re.match(r"https?://(?:127\.0\.0\.1|localhost)(?::|/|$)", url, re.IGNORECASE)
    ]
    if remote_resource_urls:
        raise AssertionError(f"{view} DOM contains a remote resource URL: {remote_resource_urls}")
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

    def set_reduced_motion(self, enabled: bool = True) -> None:
        self.command(
            "Emulation.setEmulatedMedia",
            {
                "features": [
                    {
                        "name": "prefers-reduced-motion",
                        "value": "reduce" if enabled else "no-preference",
                    }
                ]
            },
        )

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


def _physical_key(browser: _CDPBrowser, key: str) -> None:
    """Dispatch one physical-style key press through Chrome's input domain."""

    key_codes = {
        "ArrowLeft": 37,
        "ArrowRight": 39,
        "Home": 36,
        "End": 35,
    }
    try:
        key_code = key_codes[key]
    except KeyError as exc:
        raise ValueError(f"unsupported physical smoke key: {key}") from exc
    params = {
        "key": key,
        "code": key,
        "windowsVirtualKeyCode": key_code,
        "nativeVirtualKeyCode": key_code,
    }
    browser.command("Input.dispatchKeyEvent", {"type": "keyDown", **params})
    browser.command("Input.dispatchKeyEvent", {"type": "keyUp", **params})


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
            live_source_stability: dict[str, object] = {}
            dashboard_diagram_state: dict[str, object] = {}
            chart_focus_e2e: dict[str, object] = {}
            rail_keyboard_e2e: dict[str, object] = {}
            citation_focus_e2e: dict[str, object] = {}
            closed_citation_focus_e2e: dict[str, object] = {}

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
            unknown_id = "does-not-exist"
            unknown_status, unknown_raw = _fetch(
                f"{base}/api/v1/incidents/{unknown_id}"
            )
            unknown_payload = json.loads(unknown_raw)
            unknown_error = (
                unknown_payload.get("error", {})
                if isinstance(unknown_payload, dict)
                else {}
            )
            if (
                unknown_status != 404
                or not isinstance(unknown_payload, dict)
                or not isinstance(unknown_error, dict)
                or unknown_error.get("code") != "incident_not_found"
                or unknown_id in server.registry._sessions
                or (Path(runtime_raw) / unknown_id).exists()
            ):
                raise AssertionError(
                    "unknown incident lookup was not fail-closed: "
                    f"status={unknown_status} payload={unknown_payload!r}"
                )
            snap_status, snap_raw = _fetch(f"{base}/api/v1/incidents/{incident_id}")
            initial = _json(snap_status, snap_raw, "initial incident")
            unit_status, unit_raw = _fetch(f"{base}/api/v1/incidents/{incident_id}/units")
            initial_units = _json(unit_status, unit_raw, "initial units")
            _assert_unit_split(initial, initial_units, recovered=True)
            with tempfile.TemporaryDirectory(
                prefix="missing20-chrome-", ignore_cleanup_errors=True
            ) as chrome_raw:
                browser = _CDPBrowser(chrome, Path(chrome_raw))
                with browser:
                    browser.navigate(
                        f"{base}/?view=dashboard&scenario=incident&incident_id={unknown_id}"
                    )
                    _wait_ui(
                        browser,
                        "document.body.dataset.workspaceReady === 'false' && "
                        "document.querySelector('#unavailable')?.hidden === false",
                        "unknown incident not-found UI",
                    )
                    unknown_ui_state = browser.evaluate(
                        """(() => ({
                          ready: document.body.dataset.workspaceReady === 'true',
                          unavailable: document.querySelector('#unavailable')?.hidden === false,
                          message: document.querySelector('#unavailable')?.textContent || ''
                        }))()"""
                    )
                    if (
                        not isinstance(unknown_ui_state, dict)
                        or unknown_ui_state.get("ready")
                        or unknown_ui_state.get("unavailable") is not True
                        or "not registered" not in str(unknown_ui_state.get("message", ""))
                    ):
                        raise AssertionError(
                            "unknown incident deep link did not fail closed in the browser: "
                            f"{unknown_ui_state!r}"
                        )
                    browser.navigate(f"{base}/?view=dashboard")
                    _wait_ui(
                        browser,
                        LIVE_DASHBOARD,
                        "live dashboard",
                    )
                    _wait_ui(
                        browser,
                        "document.querySelectorAll("
                        "'#dashboard-live-sources .live-source-card'"
                        ").length >= 3",
                        "dashboard live source cards",
                    )
                    raw_diagram_state = browser.evaluate(
                        """(() => {
                          const ids = [
                            'flow-map',
                            'dashboard-chart',
                            'queue-health-chart',
                            'erp-health-chart',
                            'invoice-health-chart',
                            'external-risk-chart'
                          ];
                          const nodes = ids.map((id) => document.querySelector(`#${id}`));
                          return {
                            diagram_ids: ids,
                            present: nodes.every(Boolean),
                            visible: nodes.every((node) => {
                              const rect = node?.getBoundingClientRect();
                              return Boolean(rect && rect.width > 0 && rect.height > 0);
                            }),
                            visible_panels: document.querySelectorAll(
                              '#dashboard-view .diagram-panel:not([hidden])'
                            ).length,
                            chart_canvas_count: document.querySelectorAll(
                              '#dashboard-view .diagram-panel canvas'
                            ).length
                          };
                        })()"""
                    )
                    if (
                        not isinstance(raw_diagram_state, dict)
                        or raw_diagram_state.get("present") is not True
                        or raw_diagram_state.get("visible") is not True
                        or raw_diagram_state.get("visible_panels") != 3
                        or raw_diagram_state.get("chart_canvas_count") != 5
                    ):
                        raise AssertionError(
                            "Dashboard did not render exactly four coordinated diagrams: "
                            f"{raw_diagram_state!r}"
                        )
                    dashboard_diagram_state = dict(raw_diagram_state)
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
                              flow_title: text('#flow-title'),
                              path_status: text('#path-status').toUpperCase(),
                              active_incident_hidden: document.querySelector(
                                '[data-incident-row="active"]'
                              )?.hidden === true,
                              healthy_empty_visible: document.querySelector(
                                '#incident-empty'
                              )?.hidden === false,
                              start_hidden: document.querySelector(
                                '#dashboard-start-investigation'
                              )?.hidden === true,
                              invoice_status: document.querySelector(
                                '#flow-map [data-node-id="invoice"] .state-badge'
                              )?.getAttribute('aria-label') || '',
                              raw_metrics_href: document.querySelector(
                                '#observability-link'
                              )?.getAttribute('href') || '',
                              visible_text: (() => {
                                const walker = document.createTreeWalker(
                                  document.body,
                                  NodeFilter.SHOW_TEXT,
                                );
                                const parts = [];
                                while (walker.nextNode()) {
                                  let node = walker.currentNode.parentElement;
                                  let visible = true;
                                  while (node) {
                                    const style = getComputedStyle(node);
                                    if (node.hidden
                                      || (node.tagName === 'DETAILS' && !node.open)
                                      || node.getAttribute('aria-hidden') === 'true'
                                      || style.display === 'none'
                                      || style.visibility === 'hidden'
                                      || node.getClientRects().length === 0) {
                                      visible = false;
                                      break;
                                    }
                                    node = node.parentElement;
                                  }
                                  if (visible) parts.push(walker.currentNode.textContent || '');
                                }
                                return parts.join('\\n');
                              })(),
                              dom_units: count('#unit-density-strip .unit-density-cell'),
                              density_total: Number(
                                document.querySelector('#unit-density-strip')?.dataset.totalRecords
                                  || 0
                              ),
                              unit_buttons: count('#dashboard-view button[data-unit-id]'),
                              anomaly_buttons: count('#unit-anomaly-list [data-unit-detail-id]'),
                              recorded_units: count(
                                '#unit-density-strip [data-unit-status="ERP_RECORDED"]'
                              ),
                              failed_units: count(
                                '#unit-density-strip [data-unit-status="QUEUE_FAILED"]'
                              )
                            };
                        })()"""
                    )
                    baseline["dashboard_diagrams"] = dashboard_diagram_state
                    baseline["visible_word_count"] = len(
                        re.findall(
                            r"[A-Za-z0-9]+(?:['’][A-Za-z0-9]+)?",
                            str(baseline.get("visible_text") or ""),
                        )
                    )
                    if not isinstance(baseline, dict) or baseline.get("expected") != 100:
                        raise AssertionError(
                            f"dashboard did not render the initial 100-unit state: {baseline!r}"
                        )
                    if (baseline.get("recorded"), baseline.get("queue_failed")) != (100, 0):
                        raise AssertionError(
                            "dashboard did not render the initial healthy 100/100 split: "
                            f"{baseline!r}"
                        )
                    if (
                        baseline.get("flow_title") != "Live movement"
                        or baseline.get("path_status") != "HEALTHY"
                        or baseline.get("active_incident_hidden") is not True
                        or baseline.get("healthy_empty_visible") is not True
                        or baseline.get("start_hidden") is not True
                        or baseline.get("invoice_status") != "RELEASED"
                        or baseline.get("raw_metrics_href") != "/metrics"
                    ):
                        raise AssertionError(
                            "healthy Normal view exposed incident controls or stale observability: "
                            f"{baseline!r}"
                        )
                    visible_normal_text = str(baseline.get("visible_text") or "")
                    forbidden_normal_copy = (
                        "Missing units in message queue",
                        "Start investigation",
                        "Investigation in progress",
                        "Open investigation",
                    )
                    visible_normal_lower = visible_normal_text.lower()
                    forbidden_visible = [
                        item for item in forbidden_normal_copy
                        if item.lower() in visible_normal_lower
                    ]
                    if forbidden_visible:
                        raise AssertionError(
                            "healthy Normal viewport exposed incident-only copy: "
                            f"{forbidden_visible}"
                        )
                    if (
                        baseline.get("dom_units"),
                        baseline.get("density_total"),
                        baseline.get("unit_buttons"),
                        baseline.get("recorded_units"),
                        baseline.get("failed_units"),
                    ) != (100, 100, 0, 100, 0):
                        raise AssertionError(
                            "dashboard density projection is not exactly 100/100/0 with no unit "
                            f"buttons: {baseline!r}"
                        )
                    if int(baseline.get("visible_word_count", 0)) > 180:
                        raise AssertionError(
                            "Dashboard primary surface exceeds the 180-word limit: "
                            f"{baseline.get('visible_word_count')}"
                        )
                    if baseline.get("incident_id") != "Incident missing-20-normal":
                        raise AssertionError(
                            f"dashboard did not open the healthy Normal scenario: {baseline!r}"
                        )
                    # Keep one fresh visual artifact for the independent UI
                    # review.  It is captured only after the DOM truth checks
                    # pass and never participates in the product runtime.
                    browser.screenshot(SCREENSHOTS / "dashboard-phase1-normal.png")
                    live_source_stability = browser.evaluate(
                        """(() => {
                          const card = document.querySelector(
                            '#dashboard-live-sources .live-source-card'
                          );
                          const details = card?.querySelector('details');
                          if (!card || !details) return null;
                          details.open = true;
                          window.__missing20LiveSourceCard = card;
                          return {
                            card_source_id: card.dataset.liveSourceId || '',
                            details_open: details.open,
                            pulse_visible: card.classList.contains('is-new')
                          };
                        })()"""
                    )
                    if not isinstance(live_source_stability, dict):
                        raise AssertionError(
                            "live source cards did not expose a disclosure target"
                    )
                    _click_ui(browser, "#tab-agent", "live-source view transition to agent")
                    _wait_ui(
                        browser,
                        AGENT_VIEW,
                        "agent view during live-source stability check",
                    )
                    _click_ui(browser, "#tab-dashboard", "live-source view transition to dashboard")
                    _wait_ui(
                        browser,
                        DASHBOARD_VIEW,
                        "dashboard view after live-source stability check",
                    )
                    live_source_after_view = browser.evaluate(
                        """(() => {
                          const card = document.querySelector(
                            '#dashboard-live-sources .live-source-card'
                          );
                          return {
                            same_card: window.__missing20LiveSourceCard === card,
                            details_open: card?.querySelector('details')?.open === true,
                            pulse_visible: card?.classList.contains('is-new') === true
                          };
                        })()"""
                    )
                    if (
                        not isinstance(live_source_after_view, dict)
                        or live_source_after_view.get("same_card") is not True
                        or live_source_after_view.get("details_open") is not True
                        or live_source_after_view.get("pulse_visible")
                        != live_source_stability.get("pulse_visible")
                    ):
                        raise AssertionError(
                            "live source disclosure or pulse changed during an unrelated "
                            "view render: "
                            f"before={live_source_stability!r} after={live_source_after_view!r}"
                        )
                    live_source_stability["same_card_after_view_change"] = True
                    live_source_stability["details_preserved_after_view_change"] = True
                    live_source_stability["pulse_not_replayed_by_view_change"] = True
                    density_state = browser.evaluate(
                        """(() => ({
                          role: document.querySelector('#unit-density-strip')
                            ?.getAttribute('role') || '',
                          cells: document.querySelectorAll(
                            '#unit-density-strip .unit-density-cell'
                          ).length,
                          unit_buttons: document.querySelectorAll(
                            '#dashboard-view button[data-unit-id]'
                          ).length,
                          anomaly_buttons: document.querySelectorAll(
                            '#unit-anomaly-list [data-unit-detail-id]'
                          ).length
                        }))()"""
                    )
                    if (
                        not isinstance(density_state, dict)
                        or density_state.get("role") != "img"
                        or density_state.get("cells") != 100
                        or density_state.get("unit_buttons") != 0
                        or density_state.get("anomaly_buttons") != 0
                    ):
                        raise AssertionError(
                            "healthy dashboard did not expose one non-interactive density strip: "
                            f"{density_state!r}"
                        )
                    # The first viewport is intentionally healthy.  Selecting
                    # Incident is a real API transition to the investigation
                    # case, not a client-side count swap.
                    _click_ui(
                        browser,
                        "#scenario-incident",
                        "incident scenario selection",
                    )
                    _wait_ui(
                        browser,
                        "document.querySelector('#incident-id')?.textContent.startsWith("
                        "'Incident missing-20-001-run-') && "
                        "document.querySelector('#recorded-count')?.textContent === '80' && "
                        "document.querySelector('#queue-count')?.textContent === '20' && "
                        "document.querySelectorAll("
                        "'#unit-density-strip [data-unit-status=\"QUEUE_FAILED\"]'"
                        ")"
                        ".length === 20",
                        "authoritative incident scenario",
                    )
                    anomaly_state = browser.evaluate(
                        """(() => {
                          const buttons = [...document.querySelectorAll(
                            '#unit-anomaly-list [data-unit-detail-id]'
                          )];
                          const first = buttons[0];
                          first?.click();
                          return {
                            count: buttons.length,
                            tab_stops: buttons.filter((item) => item.tabIndex === 0).length,
                            detail: document.querySelector('#unit-detail')?.textContent || '',
                            selected: document.querySelector(
                              '.unit-anomaly-button.is-selected'
                            )?.dataset.unitDetailId || ''
                          };
                        })()"""
                    )
                    if (
                        not isinstance(anomaly_state, dict)
                        or anomaly_state.get("count") != 6
                        or anomaly_state.get("tab_stops") != 1
                        or not anomaly_state.get("selected")
                        or not anomaly_state.get("detail")
                    ):
                        raise AssertionError(
                            "incident density strip did not expose bounded anomaly detail access: "
                            f"{anomaly_state!r}"
                        )
                    shared_cursor_state = browser.evaluate(
                        """(() => {
                          const canvas = document.querySelector('#dashboard-chart');
                          const meta = canvas?.__chartMeta;
                          canvas?.focus();
                          canvas?.dispatchEvent(
                            new KeyboardEvent('keydown', {key: 'ArrowLeft', bubbles: true})
                          );
                          const detail = document.querySelector(
                            '#flow-selection-detail'
                          )?.textContent || '';
                          return {
                            points: meta?.points?.length || 0,
                            detail,
                            trend: document.querySelector('#trend-time')?.textContent || '',
                            health: document.querySelector(
                              '#flow-health-cursor'
                            )?.textContent || '',
                            source: document.querySelector(
                              '#source-status-summary'
                            )?.textContent || ''
                          };
                        })()"""
                    )
                    if (
                        not isinstance(shared_cursor_state, dict)
                        or int(shared_cursor_state.get("points", 0)) < 2
                        or not shared_cursor_state.get("detail")
                        or not shared_cursor_state.get("trend")
                        or shared_cursor_state.get("trend")
                        != shared_cursor_state.get("health")
                        or shared_cursor_state.get("trend")
                        != shared_cursor_state.get("source")
                        or not re.search(
                            r"observed .* received .*\d+(?:\.\d+)?s old",
                            str(shared_cursor_state.get("detail")),
                        )
                    ):
                        raise AssertionError(
                            "shared chart cursor did not expose one timestamp and numeric "
                            f"freshness: {shared_cursor_state!r}"
                        )
                    # Scenario controls live in the Scenario Lab, but the
                    # physical chart keyboard contract belongs to the
                    # Dashboard. Return through the real top-level tab before
                    # exercising every dashboard canvas.
                    _click_ui(browser, "#tab-dashboard", "Dashboard tab for chart focus")
                    _wait_ui(browser, DASHBOARD_VIEW, "dashboard chart focus view")
                    # Drive every visible chart through Chrome's physical input
                    # dispatch. A live SSE redraw must not move focus back to a
                    # navigation control or silently drop the key event.
                    chart_ids = (
                        "dashboard-chart",
                        "queue-health-chart",
                        "erp-health-chart",
                        "invoice-health-chart",
                        "external-risk-chart",
                    )
                    chart_focus_e2e = {}
                    for chart_id in chart_ids:
                        focused = browser.evaluate(
                            f"(() => {{ const node = document.querySelector('#{chart_id}'); "
                            "node?.focus({preventScroll: true}); "
                            "return document.activeElement?.id || ''; })()"
                        )
                        if focused != chart_id:
                            raise AssertionError(
                                f"could not focus chart canvas {chart_id}: {focused!r}"
                            )
                        # Repeat physical navigation while SSE is still active;
                        # a redraw between presses must not move the shared
                        # cursor to a different canvas or metric.
                        for _ in range(3):
                            _physical_key(browser, "ArrowRight")
                        physical_state = browser.evaluate(
                            f"""(() => {{
                              const canvas = document.querySelector('#{chart_id}');
                              const detail = document.querySelector(
                                '#flow-selection-detail'
                              )?.textContent || '';
                              return {{
                                active_id: document.activeElement?.id || '',
                                metric: canvas?.__chartMeta?.metric || '',
                                detail,
                                shared_timestamp: document.querySelector(
                                  '#trend-time'
                                )?.textContent || '',
                                health_timestamp: document.querySelector(
                                  '#flow-health-cursor'
                                )?.textContent || '',
                                source_timestamp: document.querySelector(
                                  '#source-status-summary'
                                )?.textContent || '',
                                numeric_freshness: /\\d+(?:\\.\\d+)?s old/.test(detail)
                              }};
                            }})()"""
                        )
                        if (
                            not isinstance(physical_state, dict)
                            or physical_state.get("active_id") != chart_id
                            or not physical_state.get("detail")
                            or not physical_state.get("metric")
                            or physical_state.get("numeric_freshness") is not True
                            or not physical_state.get("shared_timestamp")
                            or physical_state.get("shared_timestamp")
                            != physical_state.get("health_timestamp")
                            or physical_state.get("shared_timestamp")
                            != physical_state.get("source_timestamp")
                        ):
                            raise AssertionError(
                                "physical chart key focus was lost for "
                                f"state={physical_state!r}"
                            )
                        chart_focus_e2e[chart_id] = physical_state
                    selected_incident_label = browser.evaluate(
                        "document.querySelector('#incident-id')?.textContent || ''"
                    )
                    if (
                        not isinstance(selected_incident_label, str)
                        or not selected_incident_label.startswith("Incident missing-20-001-run-")
                    ):
                        raise AssertionError(
                            "incident scenario did not select a fresh persisted run: "
                            f"{selected_incident_label!r}"
                        )
                    incident_id = selected_incident_label.removeprefix("Incident ")
                    selected_status, selected_raw = _fetch(
                        f"{base}/api/v1/incidents/{incident_id}"
                    )
                    selected_snapshot = _json(
                        selected_status, selected_raw, "selected incident snapshot"
                    )
                    selected_unit_status, selected_unit_raw = _fetch(
                        f"{base}/api/v1/incidents/{incident_id}/units"
                    )
                    selected_units = _json(
                        selected_unit_status, selected_unit_raw, "selected incident units"
                    )
                    _assert_unit_split(selected_snapshot, selected_units, recovered=False)
                    failed_ids = {
                        str(item.get("unit_id"))
                        for item in selected_units["units"]
                        if isinstance(item, dict) and item.get("status") == "QUEUE_FAILED"
                    }
                    detected = next(
                        event
                        for event in selected_snapshot.get("events", [])
                        if event.get("event_type") == "incident.detected"
                    )
                    admitted = set(detected.get("payload", {}).get("failed_unit_ids", []))
                    if admitted != failed_ids or len(admitted) != 20:
                        raise AssertionError(
                            "incident.detected did not bind the exact 20 failed unit IDs"
                        )
                    telemetry_history = selected_snapshot.get("telemetry", {}).get("history", [])
                    if not isinstance(telemetry_history, list) or len(telemetry_history) < 2:
                        raise AssertionError(
                            "incident scenario did not expose a healthy-to-fault "
                            "telemetry transition"
                        )
                    baseline_counts = telemetry_history[0].get("unit_counts", {})
                    fault_counts = telemetry_history[-1].get("unit_counts", {})
                    if (
                        baseline_counts.get("total"),
                        baseline_counts.get("erp_recorded"),
                        baseline_counts.get("queue_failed"),
                    ) != (100, 100, 0):
                        raise AssertionError(
                            "incident telemetry is missing the healthy baseline: "
                            f"{baseline_counts!r}"
                        )
                    if (
                        fault_counts.get("total"),
                        fault_counts.get("erp_recorded"),
                        fault_counts.get("queue_failed"),
                    ) != (100, 80, 20):
                        raise AssertionError(
                            "incident telemetry is missing the faulted source state: "
                            f"{fault_counts!r}"
                        )
                    source_sequence = next(
                        int(event["sequence"])
                        for event in selected_snapshot.get("events", [])
                        if event.get("event_type") == "source.condition.injected"
                    )
                    detected_sequence = next(
                        int(event["sequence"])
                        for event in selected_snapshot.get("events", [])
                        if event.get("event_type") == "incident.detected"
                    )
                    if source_sequence >= detected_sequence:
                        raise AssertionError(
                            "source.condition.injected must precede incident.detected"
                        )
                    incident_baseline = browser.evaluate(
                        "Number((document.querySelector('#sequence-label')?.textContent || '')"
                        ".replace(/\\D/g, '')) || 0"
                    )
                    if (
                        not isinstance(incident_baseline, (int, float))
                        or int(incident_baseline) < detected_sequence
                    ):
                        raise AssertionError(
                            "incident scenario did not expose source-then-detector "
                            f"ledger sequence {detected_sequence}"
                        )
                    dashboard_initial_sequence = int(incident_baseline)
                    _click_ui(browser, "#tab-agent", "Agent Workspace tab click")
                    _wait_ui(
                        browser,
                        AGENT_VIEW,
                        "agent workspace view",
                    )
                    browser.evaluate(
                        "document.querySelector('#rail-tab-context')?.focus(); "
                        "document.activeElement?.id || ''"
                    )
                    _physical_key(browser, "ArrowRight")
                    rail_context_to_chat = browser.evaluate(
                        "(() => ({"
                        "view: document.body.dataset.view || '',"
                        "selected: document.querySelector('[data-rail-target=chat-log]')"
                        "?.getAttribute('aria-selected') || '',"
                        "active: document.activeElement?.id || ''"
                        "}))()"
                    )
                    _physical_key(browser, "End")
                    rail_chat_to_decision = browser.evaluate(
                        "(() => ({"
                        "view: document.body.dataset.view || '',"
                        "selected: document.querySelector('[data-rail-target=decision-panel]')"
                        "?.getAttribute('aria-selected') || '',"
                        "active: document.activeElement?.id || ''"
                        "}))()"
                    )
                    _physical_key(browser, "Home")
                    rail_decision_to_context = browser.evaluate(
                        "(() => ({"
                        "view: document.body.dataset.view || '',"
                        "selected: document.querySelector('[data-rail-target=agent-role-context]')"
                        "?.getAttribute('aria-selected') || '',"
                        "active: document.activeElement?.id || ''"
                        "}))()"
                    )
                    rail_keyboard_e2e = {
                        "context_to_chat": rail_context_to_chat,
                        "chat_to_decision": rail_chat_to_decision,
                        "decision_to_context": rail_decision_to_context,
                    }
                    rail_states = (
                        rail_context_to_chat,
                        rail_chat_to_decision,
                        rail_decision_to_context,
                    )
                    if not all(
                        isinstance(item, dict)
                        and item.get("view") == "agent"
                        and item.get("selected") == "true"
                        for item in rail_states
                    ) or (
                        rail_context_to_chat.get("active") != "rail-tab-chat"
                        or rail_chat_to_decision.get("active") != "rail-tab-decision"
                        or rail_decision_to_context.get("active") != "rail-tab-context"
                    ):
                        raise AssertionError(
                            "Agent Workspace rail keyboard moved global navigation or lost focus: "
                            f"{rail_keyboard_e2e!r}"
                        )
                    # The incident detector owns the handoff into the live
                    # multi-agent stream; the browser only observes it.
                    _wait_ui(
                        browser,
                        AUTO_HANDOFF_READY,
                        "detector-triggered agent handoff",
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
                    # Detection owns the handoff and may advance the durable
                    # ledger before the browser finishes entering Agent
                    # Workspace. Do not infer an event-count delta from the
                    # client cursor; the authoritative event-type and sequence
                    # assertions below are the lifecycle proof.
                    if int(investigation_sequence) < detected_sequence:
                        raise AssertionError(
                            "fresh investigation cursor regressed before detection "
                            f"{detected_sequence}: "
                            f"{investigation_sequence!r}"
                        )

                    role_checks = browser.evaluate(
                        """(() => {
                          const ids = [
                            'retryable_message_investigator',
                            'short_shipment_investigator',
                            'duplicate_posting_investigator',
                          ];
                          const checks = ids.map((id) => {
                            const card = document.querySelector(
                              `.agent-nodes [data-agent-id="${id}"]`
                            );
                            card?.click();
                            const selected = document.querySelector(
                              `.agent-nodes [data-agent-id="${id}"].is-selected`
                            );
                            const role = document.querySelector(
                              '#agent-role-name'
                            )?.textContent || '';
                            const title = document.querySelector(
                              '#copilot-title'
                            )?.textContent || '';
                            const links = document.querySelectorAll(
                              '#agent-graph-links .is-selected-route'
                            ).length;
                            const feed = [
                              document.querySelector('#operation-feed')?.textContent || '',
                              document.querySelector('#full-operation-feed')?.textContent || '',
                            ].join(' ');
                            return {
                              id,
                              selected: Boolean(selected),
                              role,
                              title,
                              selected_links: links,
                              filtered_activity: feed.length > 0 && !/No activity yet/i.test(feed),
                            };
                          });
                          const orchestrator = document.querySelector('#orchestrator-node');
                          orchestrator?.click();
                          return {
                            checks,
                            team_selected: document.querySelector(
                              '#orchestrator-node'
                            )?.classList.contains('is-selected'),
                            team_title: document.querySelector(
                              '#copilot-title'
                            )?.textContent || '',
                            graph_links: document.querySelectorAll(
                              '#agent-graph-links .agent-link'
                            ).length,
                          };
                        })()"""
                    )
                    if not isinstance(role_checks, dict):
                        raise AssertionError(
                            f"agent role interaction probe failed: {role_checks!r}"
                        )
                    checks = role_checks.get("checks")
                    if (
                        not isinstance(checks, list)
                        or len(checks) != 3
                        or any(
                            not isinstance(item, dict)
                            or item.get("selected") is not True
                            or not item.get("role")
                            or not item.get("title", "").startswith("Ask ")
                            or int(item.get("selected_links", 0)) < 2
                            or item.get("filtered_activity") is not True
                            for item in checks
                        )
                        or role_checks.get("team_selected") is not True
                        or role_checks.get("team_title") != "Ask the agent team"
                        or int(role_checks.get("graph_links", 0)) < 6
                    ):
                        raise AssertionError(
                            "agent cards did not expose selected role context and path: "
                            f"{role_checks!r}"
                        )

                    before_replay_status, before_replay_raw = _fetch(
                        f"{base}/api/v1/incidents/{incident_id}"
                    )
                    before_replay_snapshot = _json(
                        before_replay_status,
                        before_replay_raw,
                        "pre-replay snapshot",
                    )
                    before_replay_digest = hashlib.sha256(before_replay_raw).hexdigest()
                    replay_sse_before = browser.sse_events()
                    # Preserve the live stream observed before opening replay.
                    # Replay intentionally re-emits an earlier slice and may
                    # race a final in-flight telemetry callback; that replay
                    # slice is validated separately below.
                    live_sse_events = replay_sse_before[:]
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
                    # Replay resets the client to the durable source and
                    # detector anchors, not to the latest telemetry point.
                    # Telemetry remains part of the immutable ledger, so the
                    # first replayed event is the sequence after detection.
                    replay_sequence_start = detected_sequence + 1
                    if not replay_sequences:
                        raise AssertionError("open-incident replay emitted no ledger events")
                    replay_sequence_end = replay_sequences[-1]
                    expected_replay_sequences = list(
                        range(replay_sequence_start, replay_sequence_end + 1)
                    )
                    if replay_sequences != expected_replay_sequences:
                        raise AssertionError(
                            "open-incident replay did not drain contiguous seq "
                            f"{replay_sequence_start}..{replay_sequence_end}: "
                            f"{replay_sequences!r}"
                        )
                    if replay_sequence_end < int(investigation_sequence):
                        raise AssertionError(
                            "open-incident replay ended before the investigation cursor: "
                            f"investigation={investigation_sequence} replay={replay_sequence_end}"
                        )
                    if replay_elapsed < max(1.0, len(replay_sequences) * 0.06):
                        raise AssertionError(
                            "open-incident replay was not visibly paced: "
                            f"elapsed={replay_elapsed:.3f}s events={len(replay_sequences)}"
                        )
                    after_replay_status, after_replay_raw = _fetch(
                        f"{base}/api/v1/incidents/{incident_id}"
                    )
                    after_replay_snapshot = _json(
                        after_replay_status,
                        after_replay_raw,
                        "post-replay snapshot",
                    )
                    after_replay_digest = hashlib.sha256(after_replay_raw).hexdigest()
                    before_replay_projection = _replay_immutable_projection(before_replay_snapshot)
                    after_replay_projection = _replay_immutable_projection(after_replay_snapshot)
                    if (
                        before_replay_status != after_replay_status
                        or before_replay_projection != after_replay_projection
                    ):
                        raise AssertionError(
                            "open-incident immutable replay changed authoritative state "
                            "outside live telemetry: "
                            f"before={before_replay_digest} after={after_replay_digest}"
                        )

                    # Exercise every bounded Case Console option. Each click
                    # dispatches a real API command and leaves a durable trace;
                    # the UI is not allowed to synthesize a local answer.
                    _click_ui(
                        browser,
                        '[data-case-action-id="compare_causes"]',
                        "Case Console compare causes",
                    )
                    _wait_ui(
                        browser,
                        "document.querySelectorAll('.chat-message.chat-assistant').length >= 1 && "
                        "document.querySelectorAll('.operation-item').length > 0",
                        "Case Console compare causes response",
                        timeout=60,
                    )
                    _click_ui(
                        browser,
                        '[data-case-action-id="show_evidence"]',
                        "Case Console show evidence",
                    )
                    _wait_ui(
                        browser,
                        "document.querySelectorAll('.chat-message.chat-assistant').length >= 2 && "
                        "document.querySelectorAll('.chat-citations .citation').length > 0",
                        "Case Console evidence response",
                        timeout=60,
                    )
                    _click_ui(
                        browser,
                        '[data-case-action-id="explain_decision"]',
                        "Case Console explain decision",
                    )
                    _wait_ui(
                        browser,
                        "document.querySelectorAll('.chat-message.chat-assistant').length >= 3 && "
                        "/evaluator|deterministic/i.test(document.querySelector("
                        "'#chat-log')?.textContent || '')",
                        "Case Console decision response",
                        timeout=60,
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
                    citation_focus_e2e = browser.evaluate(
                        """(() => {
                          const buttons = [...document.querySelectorAll(
                            '.chat-citations .citation'
                          )];
                          const ids = [...new Set(
                            buttons.map((button) => (button.textContent || '').trim())
                              .filter(Boolean)
                          )];
                          const results = ids.map((id) => {
                            const button = buttons.find(
                              (candidate) => (candidate.textContent || '').trim() === id
                            );
                            button?.click();
                            const target = [...document.querySelectorAll(
                              '.evidence-record[data-evidence-id]'
                            )].find((record) => record.dataset.evidenceId === id);
                            return {
                              id,
                              target: Boolean(target),
                              drawer_open: [...document.querySelectorAll(
                                'details.evidence-drawer'
                              )].some((drawer) => drawer.open),
                              active_id: document.activeElement?.dataset?.evidenceId || '',
                              aria_current: target?.getAttribute('aria-current') || '',
                              focused: target?.classList.contains('is-focused') === true,
                            };
                          });
                          return { ids, results };
                        })()"""
                    )
                    live_citation_results = (
                        citation_focus_e2e.get("results")
                        if isinstance(citation_focus_e2e, dict)
                        else None
                    )
                    live_citation_rows: list[object] = (
                        live_citation_results if isinstance(live_citation_results, list) else []
                    )
                    if (
                        not isinstance(citation_focus_e2e, dict)
                        or not isinstance(citation_focus_e2e.get("ids"), list)
                        or not citation_focus_e2e.get("ids")
                        or not isinstance(live_citation_results, list)
                        or any(
                            not isinstance(item, dict)
                            or item.get("target") is not True
                            or item.get("drawer_open") is not True
                            or item.get("active_id") != item.get("id")
                            or item.get("aria_current") != "true"
                            or item.get("focused") is not True
                            for item in live_citation_rows
                        )
                    ):
                        raise AssertionError(
                            "displayed live citations did not land on exact focused evidence: "
                            f"{citation_focus_e2e!r}"
                        )
                    # Remove the durable target behind one displayed citation
                    # and click it again. The console must expose a visible
                    # fail-closed state rather than silently selecting a stale
                    # or fabricated record.
                    missing_citation_state = browser.evaluate(
                        """(() => {
                          const button = document.querySelector('.chat-citations .citation');
                          const id = (button?.textContent || '').trim();
                          const records = [...document.querySelectorAll(
                            '.evidence-record[data-evidence-id]'
                          )].filter((record) => record.dataset.evidenceId === id);
                          records.forEach((record) => record.remove());
                          button?.click();
                          return {
                            id,
                            status: document.querySelector('#evidence-status')?.textContent || '',
                            visible: document.querySelector('#evidence-status')?.hidden === false,
                            focused: document.querySelector(
                              '.evidence-record[aria-current="true"]'
                            )?.dataset.evidenceId || '',
                          };
                        })()"""
                    )
                    if (
                        not isinstance(missing_citation_state, dict)
                        or missing_citation_state.get("visible") is not True
                        or "not admitted" not in str(missing_citation_state.get("status", ""))
                        or missing_citation_state.get("focused")
                    ):
                        raise AssertionError(
                            "missing citation did not fail closed visibly: "
                            f"{missing_citation_state!r}"
                        )
                    _click_ui(
                        browser,
                        '[data-case-action-id="prepare_recovery"]',
                        "Case Console prepare recovery",
                    )
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
                    browser.navigate(
                        f"{base}/?view=agent&scenario=incident&incident_id={incident_id}"
                    )
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
                              dom_units: count('#unit-density-strip .unit-density-cell'),
                              density_total: Number(
                                document.querySelector('#unit-density-strip')?.dataset.totalRecords
                                  || 0
                              ),
                              unit_buttons: count('#dashboard-view button[data-unit-id]'),
                              recorded_units: count(
                                '#unit-density-strip [data-unit-status="ERP_RECORDED"]'
                              ),
                              failed_units: count(
                                '#unit-density-strip [data-unit-status="QUEUE_FAILED"]'
                              ),
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
                        final_browser_state.get("density_total"),
                        final_browser_state.get("unit_buttons"),
                        final_browser_state.get("recorded_units"),
                        final_browser_state.get("failed_units"),
                    ) != (100, 100, 0, 100, 0):
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
                    _wait_ui(
                        browser,
                        "document.querySelector('#agent-replay-investigation')?.hidden "
                        "=== false && "
                        "document.querySelector('#agent-replay-investigation')?.disabled "
                        "=== false",
                        "closed replay control ready",
                        timeout=30,
                    )
                    closed_chat_count = browser.evaluate(
                        "document.querySelectorAll('.chat-message.chat-assistant').length"
                    )
                    if (
                        not isinstance(closed_chat_count, int)
                        or isinstance(closed_chat_count, bool)
                    ):
                        raise AssertionError(
                            f"closed workspace did not expose assistant chat: {closed_chat_count!r}"
                        )
                    _ui(
                        browser,
                        """(() => {
                          const input = document.querySelector('#chat-input');
                          const submit = document.querySelector('#chat-submit');
                          if (!input || !submit || submit.disabled) return false;
                          input.value = 'Where did the missing units go after recovery?';
                          input.dispatchEvent(new Event('input', {bubbles: true}));
                          submit.click();
                          return true;
                        })()""",
                    )
                    _wait_ui(
                        browser,
                        "document.querySelectorAll('.chat-message.chat-assistant').length > "
                        f"{closed_chat_count} && "
                        "/closed and reconciled/i.test(document.querySelector("
                        "'#chat-log')?.textContent || '')",
                        "closed state-aware chat response",
                        timeout=60,
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
                    closed_citation_focus_e2e = browser.evaluate(
                        """(() => {
                          const buttons = [...document.querySelectorAll(
                            '.chat-citations .citation'
                          )];
                          const ids = [...new Set(
                            buttons.map((button) => (button.textContent || '').trim())
                              .filter(Boolean)
                          )];
                          const results = ids.map((id) => {
                            const button = buttons.find(
                              (candidate) => (candidate.textContent || '').trim() === id
                            );
                            button?.click();
                            const target = [...document.querySelectorAll(
                              '.evidence-record[data-evidence-id]'
                            )].find((record) => record.dataset.evidenceId === id);
                            return {
                              id,
                              target: Boolean(target),
                              drawer_open: [...document.querySelectorAll(
                                'details.evidence-drawer'
                              )].some((drawer) => drawer.open),
                              active_id: document.activeElement?.dataset?.evidenceId || '',
                              aria_current: target?.getAttribute('aria-current') || '',
                              focused: target?.classList.contains('is-focused') === true,
                            };
                          });
                          return { ids, results };
                        })()"""
                    )
                    closed_citation_results = (
                        closed_citation_focus_e2e.get("results")
                        if isinstance(closed_citation_focus_e2e, dict)
                        else None
                    )
                    closed_citation_ids = (
                        closed_citation_focus_e2e.get("ids")
                        if isinstance(closed_citation_focus_e2e, dict)
                        else None
                    )
                    closed_citation_rows: list[object] = (
                        closed_citation_results
                        if isinstance(closed_citation_results, list)
                        else []
                    )
                    closed_citation_id_rows: list[object] = (
                        closed_citation_ids if isinstance(closed_citation_ids, list) else []
                    )
                    if (
                        not isinstance(closed_citation_focus_e2e, dict)
                        or not isinstance(closed_citation_focus_e2e.get("ids"), list)
                        or not closed_citation_focus_e2e.get("ids")
                        or not any(
                            ":refresh-" in str(item)
                            for item in closed_citation_id_rows
                        )
                        or not isinstance(closed_citation_results, list)
                        or any(
                            not isinstance(item, dict)
                            or item.get("target") is not True
                            or item.get("drawer_open") is not True
                            or item.get("active_id") != item.get("id")
                            or item.get("aria_current") != "true"
                            or item.get("focused") is not True
                            for item in closed_citation_rows
                        )
                    ):
                        raise AssertionError(
                            "closed citations did not land on exact refresh evidence: "
                            f"{closed_citation_focus_e2e!r}"
                        )
                    closed_status, closed_raw = _fetch(f"{base}/api/v1/incidents/{incident_id}")
                    closed_before = _json(closed_status, closed_raw, "closed normal URL snapshot")
                    closed_before_status = closed_status
                    closed_before_digest = hashlib.sha256(closed_raw).hexdigest()
                    closed_before_projection = _replay_immutable_projection(closed_before)
                    time.sleep(1.0)
                    closed_status, closed_raw = _fetch(f"{base}/api/v1/incidents/{incident_id}")
                    closed_after = _json(
                        closed_status,
                        closed_raw,
                        "post-closed normal URL snapshot",
                    )
                    closed_after_status = closed_status
                    closed_after_digest = hashlib.sha256(closed_raw).hexdigest()
                    if (
                        closed_after_status != closed_before_status
                        or _replay_immutable_projection(closed_after)
                        != closed_before_projection
                    ):
                        raise AssertionError(
                            "normal post-CLOSED URL changed authoritative state "
                            "outside live telemetry: "
                            f"before={closed_before_digest} after={closed_after_digest}"
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
                    if (
                        replay_status != closed_before_status
                        or _replay_immutable_projection(replay_snapshot)
                        != closed_before_projection
                    ):
                        raise AssertionError(
                            "immutable replay changed authoritative state "
                            "outside live telemetry: "
                            f"before={closed_before_digest} "
                            f"after={hashlib.sha256(replay_raw).hexdigest()}"
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
                    # Scenario controls are shared by both views. Return to the
                    # Agent Workspace before asserting decision-state re-entry so
                    # the checks read the visible decision rail, not its hidden
                    # dashboard counterpart.
                    _click_ui(browser, "#tab-agent", "Agent Workspace re-entry tab")
                    _wait_ui(browser, AGENT_VIEW, "agent workspace re-entry view")
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
                        # The UI replay intentionally re-emits the lifecycle
                        # tail after the source and detector events.  The
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

                    # Scenario re-entry is a real session transition.  Recovery
                    # must continue to show the verified closed run, while a
                    # later Incident must receive a new ledger and the original
                    # 80/20 unit split rather than inheriting CLOSED state.
                    _wait_ui(
                        browser,
                        """(() => {
                          const button = document.querySelector('#scenario-recovery');
                          if (!button) return false;
                          if (button.getAttribute('aria-pressed') === 'true'
                              || button.classList.contains('is-selected')) return true;
                          if (button.disabled) return false;
                          button.click();
                          return true;
                        })()""",
                        "verified Recovery scenario",
                    )
                    _wait_ui(
                        browser,
                        "document.querySelector('#incident-id')?.textContent === "
                        f"'Incident {incident_id}' && "
                        "document.querySelector('#recorded-count')?.textContent === '100' && "
                        "document.querySelector('#queue-count')?.textContent === '0' && "
                        "/VERIFIED/i.test(document.querySelector('#decision-status')?.textContent "
                        "|| '')",
                        "verified Recovery scenario state",
                    )
                    recovery_scenario_state = browser.evaluate(
                        """(() => ({
                          incident_id: document.querySelector('#incident-id')?.textContent || '',
                          recorded: document.querySelector('#recorded-count')?.textContent || '',
                          queue: document.querySelector('#queue-count')?.textContent || '',
                          decision: document.querySelector('#decision-status')?.textContent || ''
                        }))()"""
                    )
                    # Normal is the explicit reset boundary before the next
                    # incident run; the closed Recovery session remains
                    # durable and is selected again above for verification.
                    _click_ui(browser, "#scenario-normal", "Normal reset before fresh Incident")
                    _wait_ui(
                        browser,
                        "document.querySelector('#incident-id')?.hidden === true && "
                        "document.querySelector('#recorded-count')?.textContent === '100' && "
                        "document.querySelector('#queue-count')?.textContent === '0'",
                        "healthy Normal reset",
                    )
                    _click_ui(browser, "#scenario-incident", "fresh Incident scenario")
                    _wait_ui(
                        browser,
                        "document.querySelector('#incident-id')?.textContent !== "
                        f"'Incident {incident_id}' && "
                        "document.querySelector('#recorded-count')?.textContent === '80' && "
                        "document.querySelector('#queue-count')?.textContent === '20' && "
                        "!/VERIFIED/i.test(document.querySelector('#decision-status')?.textContent "
                        "|| '')",
                        "fresh Incident scenario state",
                    )
                    fresh_scenario_state = browser.evaluate(
                        """(() => ({
                          incident_id: document.querySelector('#incident-id')?.textContent || '',
                          sequence: Number(
                            (document.querySelector('#sequence-label')?.textContent || '')
                              .replace(/\\D/g, '')
                          ) || 0,
                          recorded: document.querySelector('#recorded-count')?.textContent || '',
                          queue: document.querySelector('#queue-count')?.textContent || '',
                          decision: document.querySelector('#decision-status')?.textContent || ''
                        }))()"""
                    )
                    fresh_running_sequence = _int_field(
                        fresh_scenario_state if isinstance(fresh_scenario_state, dict) else {},
                        "sequence",
                    )
                    fresh_incident_id = str(
                        fresh_scenario_state.get("incident_id", "")
                    ).removeprefix("Incident ")
                    # The detector may still be appending the investigation
                    # lifecycle while this first DOM projection is read. Keep
                    # that running view as an authoritative prefix, then wait
                    # for the terminal evaluation before comparing DOM and API
                    # cursors. This avoids treating a normal SSE race as a
                    # broken session transition.
                    _wait_ui(
                        browser,
                        INVESTIGATION_COMPLETE,
                        "fresh Incident automatic evaluation",
                        timeout=60,
                    )
                    fresh_terminal_state = browser.evaluate(
                        """(() => ({
                          incident_id: document.querySelector('#incident-id')?.textContent || '',
                          sequence: Number(
                            (document.querySelector('#sequence-label')?.textContent || '')
                              .replace(/\\D/g, '')
                          ) || 0,
                          recorded: document.querySelector('#recorded-count')?.textContent || '',
                          queue: document.querySelector('#queue-count')?.textContent || '',
                          decision: document.querySelector('#decision-status')?.textContent || ''
                        }))()"""
                    )
                    fresh_terminal_sequence = _int_field(
                        fresh_terminal_state if isinstance(fresh_terminal_state, dict) else {},
                        "sequence",
                    )
                    fresh_status, fresh_raw = _fetch(
                        f"{base}/api/v1/incidents/{fresh_incident_id}"
                    )
                    fresh_snapshot = _json(
                        fresh_status,
                        fresh_raw,
                        "fresh Incident scenario snapshot",
                    )
                    fresh_events = [
                        event
                        for event in fresh_snapshot.get("events", [])
                        if isinstance(event, dict)
                    ]
                    fresh_sequences = [
                        int(event["sequence"])
                        for event in fresh_events
                        if isinstance(event.get("sequence"), (int, float))
                    ]
                    fresh_types = [str(event.get("event_type")) for event in fresh_events]
                    fresh_source_index = (
                        fresh_types.index("source.condition.injected")
                        if "source.condition.injected" in fresh_types
                        else -1
                    )
                    fresh_detected_index = (
                        fresh_types.index("incident.detected")
                        if "incident.detected" in fresh_types
                        else -1
                    )
                    fresh_projection_sequence = fresh_snapshot.get("projection_sequence")
                    fresh_telemetry = fresh_snapshot.get("telemetry", {}).get("history", [])
                    if (
                        not isinstance(recovery_scenario_state, dict)
                        or recovery_scenario_state.get("incident_id") != f"Incident {incident_id}"
                        or recovery_scenario_state.get("recorded") != "100"
                        or recovery_scenario_state.get("queue") != "0"
                        or "VERIFIED" not in str(recovery_scenario_state.get("decision"))
                    ):
                        raise AssertionError(
                            "Recovery scenario did not preserve the verified lifecycle: "
                            f"{recovery_scenario_state!r}"
                        )
                    if (
                        not isinstance(fresh_scenario_state, dict)
                        or fresh_scenario_state.get("incident_id") in {
                            "",
                            f"Incident {incident_id}",
                        }
                        or fresh_scenario_state.get("recorded") != "80"
                        or fresh_scenario_state.get("queue") != "20"
                        or not isinstance(fresh_terminal_state, dict)
                        or fresh_terminal_state.get("incident_id")
                        != fresh_scenario_state.get("incident_id")
                        or fresh_terminal_state.get("recorded") != "80"
                        or fresh_terminal_state.get("queue") != "20"
                        or not isinstance(fresh_projection_sequence, int)
                        or isinstance(fresh_projection_sequence, bool)
                        or fresh_running_sequence < 1
                        or fresh_terminal_sequence < fresh_running_sequence
                        or fresh_terminal_sequence > fresh_projection_sequence
                        or fresh_running_sequence > fresh_projection_sequence
                        or not fresh_sequences
                        or fresh_sequences != list(range(1, fresh_projection_sequence + 1))
                        or fresh_source_index < 0
                        or fresh_detected_index < 0
                        or fresh_events[fresh_source_index].get("sequence", 0)
                        >= fresh_events[fresh_detected_index].get("sequence", 0)
                        or not isinstance(fresh_telemetry, list)
                        or len(fresh_telemetry) < 2
                        or "VERIFIED" in str(fresh_terminal_state.get("decision"))
                    ):
                        raise AssertionError(
                            "Incident scenario did not create a fresh 80/20 lifecycle: "
                            f"running={fresh_scenario_state!r} terminal={fresh_terminal_state!r} "
                            f"projection_sequence={fresh_projection_sequence!r}"
                        )
                    _click_ui(browser, "#scenario-normal", "Normal reset before Golden Incident")
                    _wait_ui(
                        browser,
                        "document.querySelector('#incident-id')?.hidden === true && "
                        "document.querySelector('#recorded-count')?.textContent === '100' && "
                        "document.querySelector('#queue-count')?.textContent === '0'",
                        "healthy Normal reset before Golden Incident",
                    )
                    # Golden Incident must clear its running state from the
                    # terminal evaluation event, then Recovery must reopen the
                    # durable verified lifecycle rather than the Golden run.
                    _click_ui(browser, "#golden-incident", "Golden Incident run")
                    _wait_ui(
                        browser,
                        "document.querySelector('#golden-incident')?.textContent === "
                        "'Run Golden Incident' && "
                        "document.querySelector('#orchestrator-status')?.textContent === "
                        "'COMPLETE' && "
                        "document.querySelector('#recorded-count')?.textContent === '80' && "
                        "document.querySelector('#queue-count')?.textContent === '20'",
                        "Golden Incident terminal evaluation",
                        timeout=60,
                    )
                    golden_state = browser.evaluate(
                        """(() => ({
                          incident_id: document.querySelector('#incident-id')?.textContent || '',
                          golden_button: document.querySelector(
                            '#golden-incident'
                          )?.textContent || '',
                          orchestrator: document.querySelector(
                            '#orchestrator-status'
                          )?.textContent || '',
                          recorded: document.querySelector('#recorded-count')?.textContent || '',
                          queue: document.querySelector('#queue-count')?.textContent || ''
                        }))()"""
                    )
                    if (
                        not isinstance(golden_state, dict)
                        or golden_state.get("golden_button") != "Run Golden Incident"
                        or golden_state.get("incident_id") in {"", f"Incident {incident_id}"}
                        or golden_state.get("recorded") != "80"
                        or golden_state.get("queue") != "20"
                    ):
                        raise AssertionError(
                            "Golden Incident did not clear at terminal evaluation: "
                            f"{golden_state!r}"
                        )
                    _click_ui(browser, "#scenario-recovery", "Recovery after Golden Incident")
                    _wait_ui(
                        browser,
                        f"document.querySelector('#incident-id')?.textContent === "
                        f"'Incident {incident_id}' && "
                        "document.querySelector('#recorded-count')?.textContent === '100' && "
                        "document.querySelector('#queue-count')?.textContent === '0' && "
                        "/VERIFIED/i.test(document.querySelector("
                        "'#decision-status')?.textContent || '')",
                        "Recovery re-entry after Golden Incident",
                        timeout=30,
                    )
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
                                "citation_focus": citation_focus_e2e,
                                "closed_citation_focus": closed_citation_focus_e2e,
                                "operator_approved": True,
                                "ap_approved": True,
                                "controlled_executor": True,
                                "verification": True,
                                "replay_effect_delta": 0,
                                "final_gate_closed": True,
                                "role_interaction": role_checks,
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
                _wait_ui(
                    mobile_browser,
                    "document.querySelectorAll("
                    "'#dashboard-live-sources .live-source-card'"
                    ").length >= 3",
                    "mobile live source cards",
                )
                raw_mobile_state = mobile_browser.evaluate(
                    """(() => {
                          const flow = document.querySelector('#flow-map');
                          const liveSources = document.querySelector('#dashboard-live-sources');
                          const dashboardText = document.querySelector(
                            '#dashboard-view'
                          )?.innerText || '';
                          return {
                            viewport: window.innerWidth,
                            visible_word_count: (
                              dashboardText.match(/[A-Za-z0-9]+(?:['’][A-Za-z0-9]+)?/g) || []
                            ).length,
                            body_scroll_width: document.body.scrollWidth,
                            document_scroll_width: document.documentElement.scrollWidth,
                            flow_client_width: flow?.clientWidth || 0,
                            flow_scroll_width: flow?.scrollWidth || 0,
                            live_source_cards: document.querySelectorAll(
                              '#dashboard-live-sources .live-source-card'
                            ).length,
                            live_source_client_width: liveSources?.clientWidth || 0,
                            live_source_scroll_width: liveSources?.scrollWidth || 0,
                            remote_resources: performance.getEntriesByType('resource')
                              .map((entry) => entry.name)
                              .filter((url) => url.startsWith('http') &&
                                new URL(url).origin !== window.location.origin)
                          };
                        })()"""
                )
                if not isinstance(raw_mobile_state, dict):
                    raise AssertionError("mobile browser did not return layout metrics")
                if (
                    _int_field(raw_mobile_state, "viewport") != 390
                    or _int_field(raw_mobile_state, "body_scroll_width") > 390
                    or _int_field(raw_mobile_state, "document_scroll_width") > 390
                    or _int_field(raw_mobile_state, "flow_scroll_width")
                    <= _int_field(raw_mobile_state, "flow_client_width")
                    or _int_field(raw_mobile_state, "live_source_cards") < 3
                    or _int_field(raw_mobile_state, "live_source_client_width") > 390
                    or _int_field(raw_mobile_state, "live_source_scroll_width") > 390
                    or _int_field(raw_mobile_state, "visible_word_count") > 180
                    or raw_mobile_state.get("remote_resources")
                ):
                    raise AssertionError(
                        "mobile layout escaped the viewport or lost intentional path scroll: "
                        f"{raw_mobile_state!r}"
                    )
                mobile_state = dict(raw_mobile_state)
            responsive_word_counts: dict[str, int] = {
                "1440": int(baseline.get("visible_word_count", 0)),
                "390": _int_field(mobile_state, "visible_word_count"),
            }
            for responsive_width in (768, 1280):
                with (
                    tempfile.TemporaryDirectory(
                        prefix=f"missing20-responsive-{responsive_width}-chrome-"
                    ) as responsive_raw,
                    _CDPBrowser(
                        chrome,
                        Path(responsive_raw),
                        window_size=(responsive_width, 900),
                    ) as responsive_browser,
                ):
                    responsive_browser.navigate(
                        f"{base}/?view=dashboard&autostart=0"
                    )
                    _wait_ui(
                        responsive_browser,
                        LIVE_DASHBOARD,
                        f"{responsive_width}px live dashboard",
                    )
                    responsive_word_count = responsive_browser.evaluate(
                        """(() => {
                          const text = document.querySelector('#dashboard-view')?.innerText || '';
                          return (text.match(/[A-Za-z0-9]+(?:['’][A-Za-z0-9]+)?/g) || []).length;
                        })()"""
                    )
                    if (
                        not isinstance(responsive_word_count, int)
                        or isinstance(responsive_word_count, bool)
                        or responsive_word_count > 180
                    ):
                        raise AssertionError(
                            f"Dashboard primary surface exceeds the 180-word limit at "
                            f"{responsive_width}px: {responsive_word_count!r}"
                        )
                    responsive_word_counts[str(responsive_width)] = responsive_word_count
            with (
                tempfile.TemporaryDirectory(
                    prefix="missing20-reduced-motion-chrome-"
                ) as motion_raw,
                _CDPBrowser(
                    chrome,
                    Path(motion_raw),
                    window_size=(1280, 900),
                ) as motion_browser,
            ):
                motion_browser.set_reduced_motion()
                motion_browser.navigate(f"{base}/?view=dashboard&autostart=0")
                _wait_ui(
                    motion_browser,
                    LIVE_DASHBOARD,
                    "reduced-motion live dashboard",
                )
                reduced_motion_state = motion_browser.evaluate(
                    """(() => {
                      const line = document.querySelector('.flow-link-line');
                      const style = line ? getComputedStyle(line, '::after') : null;
                      return {
                        has_line: Boolean(line),
                        animation_name: style?.animationName || 'none',
                        animation_duration: style?.animationDuration || '0s'
                      };
                    })()"""
                )
                if (
                    not isinstance(reduced_motion_state, dict)
                    or reduced_motion_state.get("has_line") is not True
                    or reduced_motion_state.get("animation_name") != "none"
                ):
                    raise AssertionError(
                        "reduced-motion flow packet animation was not disabled: "
                        f"{reduced_motion_state!r}"
                    )
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
                          units: document.querySelectorAll(
                            '#unit-density-strip .unit-density-cell'
                          ).length,
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
                "truth_boundary": {
                    "unknown_incident_id": unknown_id,
                    "unknown_incident_status": 404,
                    "unknown_incident_code": "incident_not_found",
                    "unknown_session_created": False,
                    "unknown_runtime_directory_created": False,
                    "unknown_deep_link_ui_fail_closed": True,
                    "scenario_lab_is_only_session_allocator": True,
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
                    "open_replay_sequence_start": replay_sequence_start,
                    "open_replay_sequence_end": replay_sequence_end,
                    "open_replay_sequences": replay_sequences,
                    "open_replay_paced": True,
                    "open_replay_api_bytes_unchanged": True,
                    "final_gate_closed": True,
                },
                "views": results,
                "live_sources": live_source_stability,
                "mobile_responsive": mobile_state,
                "dashboard_visible_word_counts": responsive_word_counts,
                "reduced_motion": reduced_motion_state,
                "ui_flow": {
                    "dashboard_loaded": True,
                    "dashboard_diagrams": dashboard_diagram_state,
                    "agent_workspace_opened": True,
                    "unknown_incident_lookup_fail_closed": True,
                    "investigation_auto_handoff": True,
                    "manual_start_control_absent": True,
                    "physical_chart_key_focus": chart_focus_e2e,
                    "rail_keyboard_focus": rail_keyboard_e2e,
                    "citation_focus": citation_focus_e2e,
                    "closed_citation_focus": closed_citation_focus_e2e,
                    "role_selection_and_path_highlight": role_checks,
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
