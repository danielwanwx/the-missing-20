import json
import sys

import pytest

from scripts import run_goods_workspace


@pytest.mark.parametrize("paused", [False, True])
def test_prepare_pause_is_explicit_and_does_not_disable_handoffs(tmp_path, monkeypatch, paused):
    manifest = {"case_id": "M20-GOODS-20260909-40-R2", "purchase_order": "PO-R2"}
    (tmp_path / "receiving-manifest.json").write_text(json.dumps(manifest))
    argv = ["run_goods_workspace", "--runtime-directory", str(tmp_path), "--enable-handoffs"]
    if paused:
        argv.append("--pause-auto-prepare")
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(sys, "path", list(sys.path))
    # Isolate environment writes made by the entrypoint from other tests.
    monkeypatch.setattr(run_goods_workspace.os, "environ", {})
    monkeypatch.setattr("scripts.decision_workspace_server.main", lambda: 0)
    assert run_goods_workspace.main() == 0
    env = run_goods_workspace.os.environ
    assert env["MISSING20_PHOTO_AUTO_PREPARE"] == ("0" if paused else "1")
    assert env["MISSING20_PHOTO_DRAFTS_ENABLED"] == "1"
    assert env["MISSING20_RECEIVING_HANDOFF_ENABLED"] == "1"
    assert env["MISSING20_CASE_ID"] == manifest["case_id"]
