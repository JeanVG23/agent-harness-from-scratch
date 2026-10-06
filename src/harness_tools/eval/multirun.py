"""Stockage JSONL et agrégation de runs répétés pour comparer plusieurs runtimes."""

from __future__ import annotations

import json
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class RunRecord:
    """Résultat brut d'un cas, pour un runtime, lors d'un run donné."""
    model: str
    temperature: float
    runner: str
    dataset: str
    run_index: int
    case_id: str
    passed: bool
    duration_s: float
    steps_count: int
    tools_called: tuple[str, ...]
    tool_selection_ok: bool
    abstention_ok: bool
    keywords_ok: bool
    state_ok: bool
    error: str | None
    final_answer: str


@dataclass(frozen=True, slots=True)
class CaseSummary:
    """Nombre de réussites d'un cas sur l'ensemble des runs d'un runtime."""
    passes: int
    runs: int

    @property
    def unstable(self) -> bool:
        return 0 < self.passes < self.runs


@dataclass(frozen=True, slots=True)
class RunnerSummary:
    """Score d'un runtime sur un jeu de cas, run par run."""
    per_run_passes: tuple[int, ...]
    n_cases: int
    median_case_duration_s: float
    median_run_duration_s: float

    @property
    def mean_passes(self) -> float:
        return statistics.mean(self.per_run_passes)

    @property
    def min_passes(self) -> int:
        return min(self.per_run_passes)

    @property
    def max_passes(self) -> int:
        return max(self.per_run_passes)


@dataclass(frozen=True, slots=True)
class Aggregate:
    """Résultats agrégés, indexés par (jeu, cas, runtime) et (jeu, runtime)."""
    cases: dict[tuple[str, str, str], CaseSummary]
    runners: dict[tuple[str, str], RunnerSummary]


def save_record(path: Path, record: RunRecord) -> None:
    """Ajoute un enregistrement en fin de fichier JSONL (une ligne par cas et par run)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")


def load_records(path: Path) -> list[RunRecord]:
    """Relit les enregistrements d'un fichier JSONL."""
    records: list[RunRecord] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            data = json.loads(line)
            data["tools_called"] = tuple(data["tools_called"])
            records.append(RunRecord(**data))
    return records


def aggregate(records: list[RunRecord]) -> Aggregate:
    """Compte les réussites par cas et par run, et résume les latences par runtime."""
    by_case: dict[tuple[str, str, str], list[RunRecord]] = {}
    by_runner: dict[tuple[str, str], list[RunRecord]] = {}
    for rec in records:
        by_case.setdefault((rec.dataset, rec.case_id, rec.runner), []).append(rec)
        by_runner.setdefault((rec.dataset, rec.runner), []).append(rec)

    cases = {
        key: CaseSummary(passes=sum(r.passed for r in recs), runs=len(recs))
        for key, recs in by_case.items()
    }

    runners: dict[tuple[str, str], RunnerSummary] = {}
    for key, recs in by_runner.items():
        run_indexes = sorted({r.run_index for r in recs})
        per_run_passes = tuple(sum(r.passed for r in recs if r.run_index == i) for i in run_indexes)
        run_durations = [sum(r.duration_s for r in recs if r.run_index == i) for i in run_indexes]
        runners[key] = RunnerSummary(
            per_run_passes=per_run_passes,
            n_cases=len({r.case_id for r in recs}),
            median_case_duration_s=statistics.median(r.duration_s for r in recs),
            median_run_duration_s=statistics.median(run_durations),
        )
    return Aggregate(cases=cases, runners=runners)


def format_report(records: list[RunRecord]) -> str:
    """Produit un rapport texte : score par run, puis réussites par cas (k/N)."""
    if not records:
        return "Aucun enregistrement."

    summary = aggregate(records)
    models = sorted({r.model for r in records})
    temps = sorted({r.temperature for r in records})
    lines = [
        f"Modèle(s) : {', '.join(models)} | température : {', '.join(str(t) for t in temps)}",
        "",
    ]

    datasets = sorted({d for d, _ in summary.runners})
    for dataset in datasets:
        runner_names = sorted(r for d, r in summary.runners if d == dataset)
        lines.append(f"## Jeu « {dataset} »")
        lines.append("")
        lines.append("Réussites par run (moyenne, min à max) et latence médiane :")
        for runner in runner_names:
            s = summary.runners[(dataset, runner)]
            per_run = ", ".join(str(n) for n in s.per_run_passes)
            lines.append(
                f"- {runner} : {s.mean_passes:.1f}/{s.n_cases} "
                f"({s.min_passes} à {s.max_passes} sur {len(s.per_run_passes)} runs ; par run : {per_run}) "
                f"| {s.median_case_duration_s:.1f} s par cas | {s.median_run_duration_s:.0f} s par run"
            )
        lines.append("")

        case_ids = sorted({c for d, c, _ in summary.cases if d == dataset})
        header = "| Cas | " + " | ".join(runner_names) + " |"
        lines.append(header)
        lines.append("| --- | " + " | ".join("---" for _ in runner_names) + " |")
        unstable: list[str] = []
        for case_id in case_ids:
            cells = []
            for runner in runner_names:
                cs = summary.cases.get((dataset, case_id, runner))
                if cs is None:
                    cells.append("n/a")
                    continue
                cells.append(f"{cs.passes}/{cs.runs}")
                if cs.unstable:
                    unstable.append(f"{case_id} ({runner}, {cs.passes}/{cs.runs})")
            lines.append(f"| {case_id} | " + " | ".join(cells) + " |")
        lines.append("")
        lines.append("Cas instables : " + (", ".join(unstable) if unstable else "aucun"))
        lines.append("")

    return "\n".join(lines)
