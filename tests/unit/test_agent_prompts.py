from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from the_missing_20.agents.prompts import PromptLoadError, PromptSet

ROOT = Path(__file__).resolve().parents[2]


def _copy_prompt_tree(target: Path) -> Path:
    destination = target / "fixtures/prompts"
    shutil.copytree(ROOT / "fixtures/prompts", destination)
    return target


def test_prompt_digest_is_for_the_checked_in_content() -> None:
    prompts = PromptSet.load(ROOT)

    assert prompts.version == "agent-v5"
    assert prompts.investigator.startswith("You are one investigator")
    assert prompts.synthesis.startswith("You synthesize")
    assert prompts.evaluator.startswith("You are an independent")
    assert len(prompts.digest) == 64


def test_changed_prompt_fails_closed(tmp_path: Path) -> None:
    root = _copy_prompt_tree(tmp_path)
    path = root / "fixtures/prompts/agent-v5/investigator.md"
    path.write_text(path.read_text(encoding="utf-8") + "\nchanged", encoding="utf-8")

    with pytest.raises(PromptLoadError, match="digest changed"):
        PromptSet.load(root)


def test_missing_prompt_fails_closed(tmp_path: Path) -> None:
    root = _copy_prompt_tree(tmp_path)
    (root / "fixtures/prompts/agent-v5/evaluator.md").unlink()

    with pytest.raises(PromptLoadError, match="missing prompt"):
        PromptSet.load(root)
