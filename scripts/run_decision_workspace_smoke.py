"""Run a bounded, local headless-Chrome smoke for both M5 workspace modes."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from http.client import RemoteDisconnected
from pathlib import Path
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


def _chrome() -> str:
    for candidate in CHROME_CANDIDATES:
        path = candidate if "/" in candidate else shutil.which(candidate)
        if path and Path(path).exists():
            return path
    raise RuntimeError("headless Chrome executable was not found")


def _fetch(url: str, *, method: str = "GET") -> tuple[int, bytes]:
    request = Request(url, method=method)
    try:
        with urlopen(request, timeout=5) as response:  # noqa: S310 - loopback URL created below
            return response.status, response.read()
    except HTTPError as exc:
        return exc.code, exc.read()


def _assert_common_dom(dom: str, mode: str) -> None:
    required = (
        'data-workspace-ready="true"',
        "PROVEN",
        "SCRIPTED SYNTHETIC PROOF",
        "NOT PROVEN",
        "M6 INTEGRATION BOUNDARY",
        "CONNECTIVITY_AND_DEGRADATION_OBSERVABILITY",
        "AgentCore capabilities remain NOT PROVEN",
        "NO WRITE AUTHORITY",
        "ADVISORY — NOT AN OPERATIONAL DECISION",
        "restart_receipt_message",
        "INTEGRATION_OPERATOR",
        "AP_APPROVER",
        "Fresh read",
        "Replay",
    )
    missing = [value for value in required if value not in dom]
    if missing:
        raise AssertionError(f"{mode} DOM is missing required content: {missing}")
    if re.search(r"<button\b|<form\b|type=[\"']submit", dom, re.IGNORECASE):
        raise AssertionError(f"{mode} page exposes an active write control")
    if re.search(r"https?://(?!127\.0\.0\.1|localhost)", dom, re.IGNORECASE):
        raise AssertionError(f"{mode} page contains a remote URL")
    if re.search(
        r"AKIA[0-9A-Z]{16}|-----BEGIN .*PRIVATE KEY-----|aws_secret_access_key", dom, re.I
    ):
        raise AssertionError(f"{mode} page contains a secret-like value")
    if mode == "degraded":
        if "DEGRADED" not in dom or dom.count("NOT PROVEN") < 2:
            raise AssertionError("degraded DOM does not disclose provider degradation")
        if "No hypothesis was fabricated" not in dom:
            raise AssertionError("degraded DOM fabricated or omitted the empty advisory state")
    else:
        if "Competing hypotheses" not in dom or dom.count("hypothesis-card") < 3:
            raise AssertionError("complete DOM does not contain the scripted hypothesis projection")


def _assert_unavailable_dom(dom: str) -> None:
    required = (
        'data-workspace-ready="true"',
        "Workspace unavailable.",
        "UNAVAILABLE",
        "LIFECYCLE_BUNDLE_INCOMPLETE",
    )
    missing = [value for value in required if value not in dom]
    if missing:
        raise AssertionError(f"invalid DOM is missing fail-closed content: {missing}")
    if "GRANTED" in dom or "CLOSED" in dom or "PASS" in dom:
        raise AssertionError("invalid DOM exposes fabricated operational state")


def _chrome_dom(chrome: str, url: str, user_data_dir: Path, screenshot: Path) -> tuple[str, str]:
    command = [
        chrome,
        "--headless=new",
        "--disable-gpu",
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-sync",
        "--no-proxy-server",
        "--no-first-run",
        "--no-default-browser-check",
        f"--user-data-dir={user_data_dir}",
        "--virtual-time-budget=3000",
        "--run-all-compositor-stages-before-draw",
        "--window-size=1440,900",
        f"--screenshot={screenshot}",
        "--dump-dom",
        url,
    ]
    with (
        tempfile.TemporaryFile(mode="w+", encoding="utf-8") as stdout,
        tempfile.TemporaryFile(mode="w+", encoding="utf-8") as stderr,
    ):
        process = subprocess.Popen(command, stdout=stdout, stderr=stderr, text=True)
        deadline = time.monotonic() + 30
        dom = ""
        try:
            while time.monotonic() < deadline:
                stdout.seek(0)
                dom = stdout.read()
                if (
                    'data-workspace-ready="true"' in dom
                    and screenshot.exists()
                    and screenshot.stat().st_size > 0
                ):
                    break
                if process.poll() is not None:
                    break
                time.sleep(0.1)
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
        stderr.seek(0)
        chrome_log = stderr.read()
    if 'data-workspace-ready="true"' not in dom:
        raise RuntimeError(f"Chrome DOM capture did not become ready: {chrome_log[-500:]}")
    if not screenshot.exists() or screenshot.stat().st_size == 0:
        raise RuntimeError(f"Chrome screenshot was not written: {chrome_log[-500:]}")
    return dom, chrome_log


def main() -> int:
    try:
        chrome = _chrome()
        server = DecisionWorkspaceServer(("127.0.0.1", 0), ROOT)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        SCREENSHOTS.mkdir(parents=True, exist_ok=True)
        results: list[dict[str, object]] = []
        with tempfile.TemporaryDirectory(prefix="missing20-chrome-") as raw_profile:
            profile = Path(raw_profile)
            health_status, health = _fetch(f"{base}/healthz")
            if health_status != 200 or b'"read_only":true' not in health:
                raise AssertionError("healthz did not prove read-only mode")
            post_status, _ = _fetch(f"{base}/api/workspace?mode=complete", method="POST")
            if post_status != 405:
                raise AssertionError(f"non-GET route returned {post_status}, expected 405")
            for mode in ("complete", "degraded", "invalid"):
                url = f"{base}/?mode={mode}"
                screenshot = SCREENSHOTS / f"{mode}.png"
                dom, chrome_log = _chrome_dom(chrome, url, profile / f"{mode}-dom", screenshot)
                if mode == "invalid":
                    _assert_unavailable_dom(dom)
                else:
                    _assert_common_dom(dom, mode)
                if re.search(
                    r"(?:^|\n).*\b(?:SEVERE|Uncaught TypeError|Uncaught ReferenceError)\b",
                    chrome_log,
                ):
                    raise AssertionError(f"{mode} Chrome output contains a console error")
                results.append(
                    {
                        "mode": mode,
                        "status": "PASS",
                        "url": f"127.0.0.1:{server.server_port}/?mode={mode}",
                        "ready_marker": True,
                        "remote_resources": 0,
                        "console_errors": [],
                        "active_write_controls": 0,
                        "screenshot": str(screenshot.relative_to(ROOT)),
                    }
                )
        manifest = {
            "schema_version": "decision-workspace-browser-smoke/v1",
            "status": "PASS",
            "browser": "Google Chrome (headless)",
            "server": {"host": "127.0.0.1", "read_only": True},
            "routes": {"healthz": 200, "post_workspace": 405},
            "modes": results,
            "synthetic_only": True,
            "network": {"remote_resources": 0, "provider_calls": 0},
        }
        MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        MANIFEST.write_text(
            json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8"
        )
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    except (AssertionError, OSError, RuntimeError, RemoteDisconnected, ValueError) as exc:
        print(f"Decision Workspace browser smoke: BLOCKED ({exc})", file=sys.stderr)
        return 2
    print("Decision Workspace browser smoke: PASS (complete + degraded + invalid)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
