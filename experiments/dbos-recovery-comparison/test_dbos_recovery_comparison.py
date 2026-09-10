"""End-to-end checks for the isolated DBOS crash-recovery comparison."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType

EXPERIMENT_DIRECTORY = Path(__file__).resolve().parent
PROBE_ROOT = Path("/private/tmp/m20-dbos-2311-probe")


def _load_probe() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "dbos_recovery_comparison_under_test",
        EXPERIMENT_DIRECTORY / "dbos_recovery_comparison.py",
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load the DBOS comparison script")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PROBE = _load_probe()


class DBOSRecoveryComparisonTests(unittest.TestCase):
    def _runtime_directory(self) -> Path:
        test_root = PROBE_ROOT / "test-runs"
        test_root.mkdir(parents=True, exist_ok=True)
        return Path(tempfile.mkdtemp(prefix="dbos-recovery-", dir=test_root))

    def test_structure_probe_uses_a_sqlite_system_database(self) -> None:
        result = PROBE.run_structure_probe(self._runtime_directory())

        self.assertEqual(result["workflow_status"], "SUCCESS")
        self.assertEqual(result["effect_count"], 1)
        self.assertEqual(result["workflow_id"], PROBE.STRUCTURE_WORKFLOW_ID)

    def test_crash_recovery_comparison_records_both_fake_erp_contracts(self) -> None:
        for variant in PROBE.VARIANTS:
            with self.subTest(variant=variant):
                runtime_directory = self._runtime_directory()
                result = PROBE.run_comparison(
                    runtime_directory,
                    variant,
                    timeout_seconds=20,
                )

                self.assertEqual(result["external_intent_id"], PROBE.EXTERNAL_INTENT_ID)
                self.assertEqual(result["workflow_id"], PROBE.WORKFLOW_ID)
                self.assertTrue((runtime_directory / "comparison-result.json").is_file())
                with (runtime_directory / "phase-attempts.jsonl").open(encoding="utf-8") as log:
                    attempt_records = [json.loads(line) for line in log]
                self.assertEqual(len(attempt_records), 6)
                self.assertEqual(
                    [record["event"] for record in attempt_records],
                    ["started", "finished"] * 3,
                )
                children = result["children"]
                self.assertEqual(
                    [child["phase"] for child in children], ["crash", "recover", "replay"]
                )
                self.assertEqual([child["returncode"] for child in children], [97, 0, 0])
                self.assertEqual(len({child["pid"] for child in children}), 3)
                self.assertTrue(
                    all(isinstance(child["pid"], int) and child["pid"] > 0 for child in children)
                )

                after_crash = result["after_crash"]
                after_recovery = result["after_recovery"]
                after_replay = result["after_replay"]
                self.assertEqual(after_crash["attempt_count"], 1)
                self.assertEqual(after_crash["fake_erp_effect_row_count"], 1)
                self.assertEqual(after_recovery["attempt_count"], 2)
                self.assertEqual(after_recovery["workflow_status"], "SUCCESS")
                self.assertEqual(after_replay["workflow_status"], "SUCCESS")
                self.assertEqual(after_replay["attempt_count"], after_recovery["attempt_count"])
                self.assertEqual(
                    after_replay["fake_erp_effect_row_count"],
                    after_recovery["fake_erp_effect_row_count"],
                )
                self.assertEqual(
                    after_replay["returned_identity"], after_recovery["returned_identity"]
                )

                if variant == PROBE.NO_UNIQUE_INTENT_KEY:
                    self.assertEqual(after_recovery["fake_erp_effect_row_count"], 2)
                    self.assertNotEqual(
                        after_recovery["returned_identity"],
                        after_crash["effects"][0]["effect_id"],
                    )
                    self.assertTrue(after_recovery["returned_record"]["created"])
                else:
                    self.assertEqual(after_recovery["fake_erp_effect_row_count"], 1)
                    self.assertEqual(
                        after_recovery["returned_identity"],
                        after_crash["effects"][0]["effect_id"],
                    )
                    self.assertFalse(after_recovery["returned_record"]["created"])

    def test_child_timeout_is_limited_to_thirty_seconds(self) -> None:
        with self.assertRaises(ValueError):
            PROBE.run_comparison(
                self._runtime_directory(),
                PROBE.NO_UNIQUE_INTENT_KEY,
                timeout_seconds=30.1,
            )


if __name__ == "__main__":
    unittest.main()
