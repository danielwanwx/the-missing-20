"""Read-only localhost UI evidence capture; does not invoke models or business writes."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.run_decision_workspace_smoke import _CDPBrowser, _chrome, _wait_ui

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts/audits/2026-09-08-goods-upgrade"


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with (
        TemporaryDirectory(prefix="m20-goods-browser-") as profile,
        _CDPBrowser(_chrome(), Path(profile)) as browser,
    ):
        browser.navigate("http://127.0.0.1:8893/?view=dashboard")
        _wait_ui(
            browser,
            "document.body.dataset.workspaceReady === 'true'",
            "connected goods review dashboard",
        )
        _wait_ui(
            browser,
            "!document.querySelector('#history-refresh')?.disabled && "
            "document.querySelectorAll('#history-samples button').length > 0",
            "retained source history loaded",
        )
        browser.screenshot(OUTPUT / "01-dashboard.png")
        browser.evaluate("document.querySelector('#goods-gallery').scrollIntoView({block:'start'})")
        browser.screenshot(OUTPUT / "02-goods-history.png")
        browser.evaluate("document.querySelector('#tab-agent').click()")
        _wait_ui(browser, "document.body.dataset.view === 'agent'", "investigation")
        browser.evaluate("window.scrollTo(0,0)")
        browser.screenshot(OUTPUT / "03-investigation.png")
        browser.evaluate(
            "document.querySelector('[data-canvas-module=conversation] "
            "[data-module-focus]').click()"
        )
        _wait_ui(
            browser,
            "document.querySelector('dialog.platform-focus-dialog')?.open",
            "native expanded conversation",
        )
        browser.screenshot(OUTPUT / "04-conversation-expanded.png")
        (OUTPUT / "browser-capture.json").write_text(
            json.dumps(
                {
                    "url": "http://127.0.0.1:8893",
                    "console_errors": browser.console_errors(),
                    "purpose": "UI evidence only; not a provider or business-flow acceptance",
                },
                indent=2,
            )
            + "\n"
        )


if __name__ == "__main__":
    main()
