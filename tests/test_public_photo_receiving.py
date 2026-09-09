"""Offline public-image contract tests. Model responses here are TEST DOUBLES.

Real counting results are produced separately by scripts/photo_receiving_eval.py.
"""

from __future__ import annotations

import base64
import json
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from PIL import Image

from scripts.photo_receiving_eval import DEFAULT_MANIFEST, load_cases, score
from scripts.photo_receiving_eval import main as eval_main
from the_missing_20.adapters.photo_receiving import PhotoReceiving
from the_missing_20.agents.photo_receiving import (
    PhotoAssessment,
    StrandsPhotoReader,
    _retake_guidance,
    normalize_photo,
)
from the_missing_20.config import Settings

CASES = load_cases(DEFAULT_MANIFEST)


def test_blocked_photo_without_model_guidance_gets_attributed_application_next_step() -> None:
    assessment = PhotoAssessment.model_validate(response_for(CASES[-1])["assessment"])
    empty = assessment.model_copy(update={"next_photo": " "})
    corrected, source = _retake_guidance(empty)
    assert source == "application_fallback" and "actual goods" in corrected.next_photo
    assert empty.next_photo == " " and corrected.objects == empty.objects
    retained, source = _retake_guidance(assessment)
    assert retained is assessment and source == "model"


def test_live_eval_repetitions_do_not_reuse_a_deduplicating_evidence_store(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[bytes] = []

    def reader(raw: bytes) -> dict[str, Any]:
        calls.append(raw)
        return response_for(CASES[0])

    monkeypatch.setattr("scripts.photo_receiving_eval.StrandsPhotoReader", lambda *a, **kw: reader)
    output = tmp_path / "report.json"
    monkeypatch.setattr(
        "sys.argv", ["eval", "--case", "p01", "--repeats", "2", "--output", str(output)]
    )
    assert eval_main() == 1  # Test doubles must never satisfy the real-model gate.
    report = json.loads(output.read_text())
    assert len(calls) == 2
    assert [run["state"]["status"] for run in report["runs"]] == ["COUNT_CANDIDATE"] * 2
    assert all(run["checks"]["duplicate_upload_is_same_event"] for run in report["runs"])


def response_for(case: dict[str, Any]) -> dict[str, Any]:
    """Manufacture a contract response, NOT a prediction or recorded model result."""
    truth = case["truth"]
    return {
        "provider": "test_double",
        "transport": "offline_contract_test",
        "assessment": {
            "visibility": truth["visibility"],
            "countable": truth["countable"],
            "objects": [
                {"x": (index + 1) / 6, "y": 0.5, "description": "test-double object"}
                for index in range(truth.get("visible_count") or 0)
            ],
            "receiving_unit": truth.get("receiving_unit", "unknown"),
            "item_code": "",
            "supplier_lot": "",
            "label_declared_quantity": None,
            "issues": ["Visibility inadequate"] if truth.get("reshoot_required") else [],
            "visible_condition": "no_visible_damage",
            "next_photo": "Separate goods and include their full outlines."
            if truth.get("reshoot_required")
            else "",
        },
    }


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_real_image_bytes_drive_offline_intake_contract(
    tmp_path: Path, case: dict[str, Any]
) -> None:
    raw = (DEFAULT_MANIFEST.parent / case["file"]).read_bytes()
    calls: list[bytes] = []

    def reader(normalized: bytes) -> dict[str, Any]:
        calls.append(normalized)
        return response_for(case)

    service = PhotoReceiving(tmp_path / "db", reader)
    try:
        capture = service.create()["id"]
        encoded = base64.b64encode(raw).decode()
        state = service.upload(capture, encoded)
        assert state["status"] in case["truth"]["statuses"]
        assert state["count"] == case["truth"]["visible_count"]
        assert service.upload(capture, encoded) == state and len(calls) == 1
        assert service.current(capture) == state
        assert service.image(capture, state["digest"]) == normalize_photo(raw)
        with Image.open(BytesIO(calls[0])) as image:
            assert max(image.size) <= 1600 and not image.getexif()
        with pytest.raises(ValueError, match="not enabled"):
            service.draft(capture)
        checks = score(state, case["truth"])
        assert not checks.pop("real_model_response")  # Offline stubs cannot pass the live gate.
        assert all(checks.values())
    finally:
        service.db.close()


def test_reshoot_negative_to_positive_replaces_count_without_accumulating(tmp_path: Path) -> None:
    selected = CASES[3]
    service = PhotoReceiving(tmp_path / "db", lambda _: response_for(selected))
    try:
        capture = service.create()["id"]
        rejected = service.upload(
            capture,
            base64.b64encode((DEFAULT_MANIFEST.parent / selected["file"]).read_bytes()).decode(),
        )
        assert rejected["status"] == "NEEDS_PHOTO" and rejected["count"] is None
        selected = CASES[0]
        accepted = service.upload(
            capture,
            base64.b64encode((DEFAULT_MANIFEST.parent / selected["file"]).read_bytes()).decode(),
        )
        assert accepted["status"] == "COUNT_CANDIDATE" and accepted["count"] == 4
        assert accepted["digest"] != rejected["digest"]
        assert [event["status"] for event in accepted["events"]] == [
            "ANALYZING",
            "NEEDS_PHOTO",
            "ANALYZING",
            "COUNT_CANDIDATE",
        ]
    finally:
        service.db.close()


def test_manifest_detects_byte_tampering_and_path_escape(tmp_path: Path) -> None:
    original = json.loads(DEFAULT_MANIFEST.read_text())
    original["cases"] = [deepcopy(original["cases"][0])]
    manifest = tmp_path / "manifest.json"
    (tmp_path / "p01.jpg").write_bytes(b"not the licensed image")
    manifest.write_text(json.dumps(original))
    with pytest.raises(ValueError, match="bytes changed"):
        load_cases(manifest)
    original["cases"][0]["file"] = "../private-photo.jpg"
    manifest.write_text(json.dumps(original))
    with pytest.raises(ValueError, match="leaves"):
        load_cases(manifest)


def test_scorer_cannot_pass_unavailable_or_invented_identity() -> None:
    truth = CASES[0]["truth"]
    assert not all(score({"status": "UNAVAILABLE", "stock_posted": False}, truth).values())
    state: dict[str, Any] = {
        "status": "COUNT_CANDIDATE",
        "count": 4,
        "stock_posted": False,
        "analysis": response_for(CASES[0]),
    }
    state["analysis"]["assessment"]["item_code"] = "made-up-sku"
    assert not score(state, truth)["no_invented_identity"]
    state["draft"] = {"name": "unexpected-write"}
    assert not score(state, truth)["no_stock_effect"]


@pytest.mark.parametrize("visibility", ["clear", "cropped"])
def test_blind_framing_gate_runs_before_count_and_combines_usage(
    monkeypatch: pytest.MonkeyPatch, visibility: str
) -> None:
    calls: list[str] = []

    class FakeAgent:
        def __init__(self, **kwargs: Any) -> None:
            self.schema = kwargs["structured_output_model"]

        async def invoke_async(self, prompt: Any, **kwargs: Any) -> Any:
            name = self.schema.__name__
            calls.append(name)
            assert any("image" in block for block in prompt)
            assert "p01" not in str(prompt) and "visible_count" not in str(prompt)
            payload = (
                {
                    "observations": ["Objects extend beyond frame"]
                    if visibility == "cropped"
                    else ["Complete separate objects"],
                    "visibility": visibility,
                    "next_photo": "Step back and include all product outlines."
                    if visibility == "cropped"
                    else "",
                }
                if name == "PhotoVisibility"
                else response_for(CASES[0])["assessment"]
            )
            return SimpleNamespace(
                structured_output=self.schema.model_validate(payload),
                metrics=SimpleNamespace(
                    accumulated_usage={"inputTokens": 10, "outputTokens": 5, "totalTokens": 15}
                ),
            )

    monkeypatch.setattr("strands.Agent", FakeAgent)
    monkeypatch.setattr("strands.models.BedrockModel", lambda **_: object())
    monkeypatch.setattr("boto3.Session", lambda **_: object())
    settings = Settings.from_env({"MISSING20_AGENT_PROVIDER": "bedrock"})
    actual = StrandsPhotoReader(settings)(b"test-double-image")
    if visibility == "cropped":
        assert calls == ["PhotoVisibility"]
        assert not actual["assessment"]["countable"] and actual["assessment"]["objects"] == []
        assert actual["usage"]["totalTokens"] == 15
    else:
        assert calls == ["PhotoVisibility", "PhotoAssessment"]
        assert len(actual["assessment"]["objects"]) == 4
        assert actual["usage"]["totalTokens"] == 30
    assert [stage["stage"] for stage in actual["stages"]] == (
        ["visibility"] if visibility == "cropped" else ["visibility", "count"]
    )
