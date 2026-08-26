"""Generate the portable Golden v1 safety report."""

from pathlib import Path

from the_missing_20.evaluation.golden_runner import GoldenRunner

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    result = GoldenRunner(ROOT, ROOT / "artifacts/golden").run_all()
    print(
        f"Golden v1 {result['status']}: "
        f"{result['passed_case_count']}/{result['case_count']} cases passed"
    )
    print(f"Safety counters: {result['safety_counters']}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
