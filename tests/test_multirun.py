"""Tests de l'agrégation des runs répétés (stockage JSONL et rapport)."""

from __future__ import annotations

from harness_tools.eval.multirun import (
    RunRecord,
    aggregate,
    format_report,
    load_records,
    save_record,
)


def _rec(runner: str, run: int, case: str, passed: bool, dur: float = 1.0, dataset: str = "hard") -> RunRecord:
    return RunRecord(
        model="m",
        temperature=0.0,
        runner=runner,
        dataset=dataset,
        run_index=run,
        case_id=case,
        passed=passed,
        duration_s=dur,
        steps_count=2,
        tools_called=("calculate",),
        tool_selection_ok=passed,
        abstention_ok=True,
        keywords_ok=True,
        state_ok=True,
        error=None,
        final_answer="ok",
    )


def test_record_round_trip_through_jsonl(tmp_path):
    path = tmp_path / "out.jsonl"
    first = _rec("harness_v4", 1, "a", True)
    second = _rec("smolagents", 2, "b", False, dur=3.5)
    save_record(path, first)
    save_record(path, second)
    assert load_records(path) == [first, second]


def test_aggregate_counts_passes_per_case_and_runner():
    records = [
        _rec("harness_v4", 1, "a", True),
        _rec("harness_v4", 2, "a", True),
        _rec("harness_v4", 3, "a", False),
        _rec("harness_v4", 1, "b", False),
        _rec("harness_v4", 2, "b", False),
        _rec("harness_v4", 3, "b", False),
    ]
    summary = aggregate(records)
    case_a = summary.cases[("hard", "a", "harness_v4")]
    assert (case_a.passes, case_a.runs) == (2, 3)
    assert case_a.unstable
    case_b = summary.cases[("hard", "b", "harness_v4")]
    assert (case_b.passes, case_b.runs) == (0, 3)
    assert not case_b.unstable


def test_aggregate_per_run_score_range():
    records = [
        _rec("smolagents", 1, "a", True),
        _rec("smolagents", 1, "b", True),
        _rec("smolagents", 2, "a", True),
        _rec("smolagents", 2, "b", False),
        _rec("smolagents", 3, "a", False),
        _rec("smolagents", 3, "b", False),
    ]
    runner = aggregate(records).runners[("hard", "smolagents")]
    assert runner.per_run_passes == (2, 1, 0)
    assert runner.n_cases == 2
    assert runner.mean_passes == 1.0
    assert (runner.min_passes, runner.max_passes) == (0, 2)


def test_aggregate_latency_uses_median():
    records = [
        _rec("pydantic_ai", 1, "a", True, dur=1.0),
        _rec("pydantic_ai", 1, "b", True, dur=2.0),
        _rec("pydantic_ai", 1, "c", True, dur=100.0),
    ]
    runner = aggregate(records).runners[("hard", "pydantic_ai")]
    assert runner.median_case_duration_s == 2.0
    assert runner.median_run_duration_s == 103.0


def test_aggregate_separates_datasets():
    records = [
        _rec("harness_v4", 1, "a", True, dataset="hard"),
        _rec("harness_v4", 1, "h1", False, dataset="holdout"),
    ]
    summary = aggregate(records)
    assert ("hard", "harness_v4") in summary.runners
    assert ("holdout", "harness_v4") in summary.runners
    assert summary.runners[("hard", "harness_v4")].n_cases == 1


def test_format_report_mentions_runs_and_unstable_cases():
    records = [
        _rec("harness_v4", 1, "a", True),
        _rec("harness_v4", 2, "a", False),
    ]
    report = format_report(records)
    assert "1/2" in report
    assert "instable" in report.lower()
    assert "harness_v4" in report
