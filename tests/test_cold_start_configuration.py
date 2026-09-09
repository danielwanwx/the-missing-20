"""Public starter configuration must not require developer credentials."""

import os
from unittest.mock import patch

import pytest

from the_missing_20.adapters.agent_platform import AgentPlatform
from the_missing_20.adapters.erpnext_source import DEFAULT_CASE_ID, ERPNextEvidenceSource
from the_missing_20.adapters.saas_evidence import SaaSEvidenceSource


@pytest.mark.parametrize("setting", [None, "", "   ", "M20-ISOLATED"])
def test_optional_case_setting_retains_scoped_unavailable_history(tmp_path, setting):
    if setting is not None:
        (tmp_path / ".env").write_text(f"MISSING20_CASE_ID={setting}\n")
    with patch.dict(os.environ, {}, clear=True):
        erp = ERPNextEvidenceSource.from_environment(repository_root=tmp_path)
        saas = SaaSEvidenceSource.from_environment(repository_root=tmp_path)
    expected = setting if setting and setting.strip() else DEFAULT_CASE_ID
    source = erp.current()
    assert source["case_id"] == expected
    assert source["status"] == "NOT_CONFIGURED"
    assert source["documents"] == []
    state = tmp_path / "state.json"
    for _ in range(2):
        platform = AgentPlatform(erp, saas, state_path=state)
        projection = platform.current()
        assert projection["execution"]["status"] == "WRITE_DISABLED"
        history = platform.operational_history()
        assert history["case_id"] == expected
        assert len(history["points"]) == 1
        point = history["points"][0]
        assert point["source_status"] == "NOT_CONFIGURED"
        assert point["documents"] == []
        assert all(value is None for value in point["metrics"].values())
