from __future__ import annotations

import json
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict, cast


class CoverageSummary(TypedDict):
    num_statements: int
    covered_lines: int
    num_branches: int
    covered_branches: int


class FileCoverage(TypedDict):
    summary: CoverageSummary


class CoverageReport(TypedDict):
    files: dict[str, FileCoverage]


@dataclass(frozen=True)
class CoverageTotals:
    statements: int
    covered_lines: int
    branches: int
    covered_branches: int

    @property
    def line_percent(self) -> float:
        return _percent(self.covered_lines, self.statements)

    @property
    def branch_percent(self) -> float:
        return _percent(self.covered_branches, self.branches)


def _percent(covered: int, total: int) -> float:
    return 100.0 if total == 0 else covered * 100.0 / total


def _combine(summaries: Iterable[CoverageSummary]) -> CoverageTotals:
    statements = covered_lines = branches = covered_branches = 0
    for summary in summaries:
        statements += summary["num_statements"]
        covered_lines += summary["covered_lines"]
        branches += summary["num_branches"]
        covered_branches += summary["covered_branches"]
    return CoverageTotals(statements, covered_lines, branches, covered_branches)


def _require_minimum(label: str, actual: float, minimum: float) -> None:
    if actual + 1e-9 < minimum:
        raise SystemExit(f"{label} {actual:.2f}% 低于门禁 {minimum:.2f}%")


def main() -> None:
    if len(sys.argv) != 6:
        raise SystemExit(
            "用法: check-backend-coverage.py REPORT OVERALL_LINES OVERALL_BRANCHES "
            "CORE_LINES CORE_BRANCHES"
        )

    report_path = Path(sys.argv[1])
    overall_line_minimum = float(sys.argv[2])
    overall_branch_minimum = float(sys.argv[3])
    core_line_minimum = float(sys.argv[4])
    core_branch_minimum = float(sys.argv[5])
    report = cast(
        CoverageReport,
        json.loads(report_path.read_text(encoding="utf-8")),
    )
    files = report["files"]

    overall = _combine(file_data["summary"] for file_data in files.values())
    core_summaries = [
        file_data["summary"]
        for file_name, file_data in files.items()
        if file_name.startswith(("src/common_agent/domain/", "src/common_agent/application/"))
    ]
    if not core_summaries:
        raise SystemExit("覆盖率报告没有包含 domain/application 核心层")
    core = _combine(core_summaries)

    print(
        "后端覆盖率: "
        f"overall lines={overall.line_percent:.2f}% branches={overall.branch_percent:.2f}%; "
        f"core lines={core.line_percent:.2f}% branches={core.branch_percent:.2f}%"
    )
    _require_minimum("后端总体行覆盖率", overall.line_percent, overall_line_minimum)
    _require_minimum("后端总体分支覆盖率", overall.branch_percent, overall_branch_minimum)
    _require_minimum("后端核心层行覆盖率", core.line_percent, core_line_minimum)
    _require_minimum("后端核心层分支覆盖率", core.branch_percent, core_branch_minimum)


if __name__ == "__main__":
    main()
