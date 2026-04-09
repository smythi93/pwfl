"""
Evaluation routines for analyzer outputs.

This module computes ranking metrics (top-k, EXAM, wasted effort) for each
analyzer variant and writes per-subject and aggregate timing reports.
"""

import json
import os
import time
from pathlib import Path
from typing import Callable

import tests4py.api as t4p
from sflkit import Analyzer
from sflkit.analysis.analysis_type import AnalysisType
from sflkit.analysis.spectra import Spectrum
from sflkit.evaluation import Rank, Scenario
from sflkit.language.language import Language
from sflkit.weights import ProximityAnalyzer
from tests4py.projects import TestStatus

from pwfl.analyze import distances
from pwfl.logger import LOGGER


def max_(f1: float, f2: float) -> float:
    """
    Return the larger of two values.

    The helper exists so callers can inject a different rank aggregation
    strategy while preserving a stable default.

    :param f1: First value.
    :type f1: float
    :param f2: Second value.
    :type f2: float
    :returns: Larger value.
    :rtype: float
    """
    return max(f1, f2)


def get_results_for_type(
    type_,
    analyzer,
    project,
    location,
    faulty_lines,
    eval_metric: Callable[[float, float], float] = max_,
):
    """
    Evaluate one analysis type across all configured SBFL metrics.

    :param type_: Analysis type (typically line-level).
    :param analyzer: Loaded analyzer instance.
    :param project: Subject metadata.
    :param location: Subject checkout path.
    :param faulty_lines: Set of known faulty source locations.
    :param eval_metric: Aggregation function used by :class:`Rank`.
    :returns: Pair ``(results, times)`` keyed by metric name.
    :rtype: tuple[dict, dict]
    """
    results = dict()
    times = dict()
    for metric in [
        Spectrum.Tarantula,
        Spectrum.Ochiai,
        Spectrum.DStar,
        Spectrum.Naish2,
        Spectrum.GP13,
    ]:
        results[metric.__name__] = dict()
        time_start = time.time()
        suggestions = analyzer.get_sorted_suggestions(location, metric, type_)
        # Suggestion generation can dominate runtime, so we store timing per metric.
        times[metric.__name__] = time.time() - time_start
        rank = Rank(
            suggestions, total_number_of_locations=project.loc, metric=eval_metric
        )
        for scenario in Scenario:
            results[metric.__name__][scenario.value] = {
                "top-1": rank.top_n(faulty_lines, 1, scenario, repeat=10000),
                "top-5": rank.top_n(faulty_lines, 5, scenario, repeat=10000),
                "top-10": rank.top_n(faulty_lines, 10, scenario, repeat=10000),
                "top-200": rank.top_n(faulty_lines, 200, scenario, repeat=10000),
                "exam": rank.exam(faulty_lines, scenario),
                "wasted-effort": rank.wasted_effort(faulty_lines, scenario),
            }
    return results, times


def evaluate(project_name, bug_id, start=None, end=None):
    """
    Evaluate all saved analyzers for selected projects.

    :param project_name: Project identifier.
    :type project_name: str
    :param bug_id: Optional single bug id.
    :type bug_id: int | None
    :param start: Optional lower bound bug id.
    :type start: int | None
    :param end: Optional upper bound bug id.
    :type end: int | None
    :returns: None
    """
    Language.PYTHON.setup()
    os.makedirs("results", exist_ok=True)
    reports_dir = Path("reports")
    os.makedirs(reports_dir, exist_ok=True)
    report_file = reports_dir / f"suggestion_{project_name}.json"
    time_report = dict()
    for project in t4p.get_projects(project_name, bug_id):
        if start is not None and project.bug_id < start:
            continue
        if end is not None and project.bug_id > end:
            continue
        results_file = Path("results", f"{project.get_identifier()}.json")
        if results_file.exists():
            continue
        results = dict()
        LOGGER.info(project)
        if (
            project.test_status_buggy != TestStatus.FAILING
            or project.test_status_fixed != TestStatus.PASSING
        ):
            continue
        project.buggy = True
        subject_results = dict()
        subject_times = dict()
        location = Path("tmp", project.get_identifier())
        if not location.exists():
            report = t4p.checkout(project)
            if not report.successful:
                raise report.raised
            location = report.location
        for suffix, model_class in distances:
            analysis_file = Path("analysis", f"{project}{suffix}.json")
            if analysis_file.exists():
                if model_class is None:
                    analyzer = Analyzer.load(analysis_file)
                else:
                    analyzer = ProximityAnalyzer.load_with_dependencies(
                        analysis_file, model_class
                    )
            else:
                continue
            faulty_lines = set(t4p.get_faulty_lines(project))
            (
                subject_results[f"line{suffix}"],
                subject_times[f"line{suffix}"],
            ) = get_results_for_type(
                AnalysisType.LINE, analyzer, project, location, faulty_lines
            )
        results[project.get_identifier()] = subject_results
        time_report[project.get_identifier()] = subject_times
        with open(results_file, "w") as f:
            json.dump(results, f, indent=1)
    with open(report_file, "w") as f:
        json.dump(time_report, f, indent=1)
