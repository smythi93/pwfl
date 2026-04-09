"""
PRFL (PageRank-based Fault Localization) integration.

The module builds transition matrices from call graphs, computes PageRank-based
weights, and applies them to line spectra before evaluation.
"""

import json
import os
import time
import traceback
from pathlib import Path

import numpy as np
import tests4py.api as t4p
from sflkit.analysis.analysis_type import AnalysisType
from sflkit.analysis.analyzer import Analyzer
from sflkit.analysis.spectra import Spectrum, Line
from sflkit.evaluation import Rank, Scenario
from sflkit.language.language import Language
from sflkit.weights import ProximityAnalyzer
from tests4py.projects import TestStatus

from pwfl.analyze import distances
from pwfl.evaluate import max_


def build_transition_matrix(call_graph_data, alpha=0.001, delta=1):
    """
    Build the transition matrix P based on the call graph data.
    :param call_graph_data: JSON data representing the call graph.
    :param alpha: The weight for method-to-method transitions (as described in PRFL).
    :param delta: The weight for method-to-test transitions (as described in PRFL).
    :return: The transition matrix p.
    """
    # Create lists to hold the program entities and test cases
    covered_entities = dict()
    covered_tests_passing = dict()
    covered_tests_failing = dict()
    for entity_id, (entity_details, tests, callees) in call_graph_data.items():
        entity_name = f"{entity_details[2]} ({entity_id})"
        if entity_name not in covered_entities:
            covered_entities[entity_name] = list()
        for test in tests["PASS"]["ids"]:
            test_name = f"Pass Test ({test})"
            if test_name not in covered_tests_passing:
                covered_tests_passing[test_name] = list()
            if entity_name not in covered_tests_passing[test_name]:
                covered_tests_passing[test_name].append(entity_name)
        for test in tests["FAIL"]["ids"]:
            test_name = f"Fail Test ({test})"
            if test_name not in covered_tests_failing:
                covered_tests_failing[test_name] = list()
            if entity_name not in covered_tests_failing[test_name]:
                covered_tests_failing[test_name].append(entity_name)
        for callee_id, test_details in callees.items():
            callee_name = f"{call_graph_data[callee_id][0][2]} ({callee_id})"
            if callee_name not in covered_entities:
                covered_entities[callee_name] = list()
            if callee_name not in covered_entities[entity_name]:
                covered_entities[entity_name].append(callee_name)

    # Initialize the transition matrix with zeros
    p_mm = np.zeros((len(covered_entities), len(covered_entities)))
    p_mt_passing = np.zeros((len(covered_tests_passing), len(covered_entities)))
    p_tm_passing = np.zeros((len(covered_entities), len(covered_tests_passing)))
    p_tt_passing = np.zeros((len(covered_tests_passing), len(covered_tests_passing)))

    p_mt_failing = np.zeros((len(covered_tests_failing), len(covered_entities)))
    p_tm_failing = np.zeros((len(covered_entities), len(covered_tests_failing)))
    p_tt_failing = np.zeros((len(covered_tests_failing), len(covered_tests_failing)))

    v_m = np.zeros(len(covered_entities))
    v_t_passing = np.zeros(len(covered_tests_passing))
    v_t_failing = np.zeros(len(covered_tests_failing))

    entity_index = {entity: idx for idx, entity in enumerate(covered_entities)}
    test_index_passing = {test: idx for idx, test in enumerate(covered_tests_passing)}
    test_index_failing = {test: idx for idx, test in enumerate(covered_tests_failing)}

    for entity, covered in covered_entities.items():
        for e in covered:
            p_mm[entity_index[e], entity_index[entity]] += 1
            p_mm[entity_index[entity], entity_index[e]] += delta

    p_mm = normalize_matrix_columns(p_mm)
    p_mm *= alpha

    for test, covered in covered_tests_passing.items():
        for e in covered:
            p_tm_passing[entity_index[e], test_index_passing[test]] = 1
            p_mt_passing[test_index_passing[test], entity_index[e]] = 1
        v_t_passing[test_index_passing[test]] = (
            1 / len(covered_tests_passing) if covered_tests_passing else 0
        )

    for test, covered in covered_tests_failing.items():
        for e in covered:
            p_tm_failing[entity_index[e], test_index_failing[test]] = 1
            p_mt_failing[test_index_failing[test], entity_index[e]] = 1
        v_t_failing = 1 / len(covered) if covered else 0

    p_tm_passing = normalize_matrix_columns(p_tm_passing)
    p_mt_passing = normalize_matrix_columns(p_mt_passing)
    p_tt_passing = normalize_matrix_columns(p_tt_passing)
    p_tm_failing = normalize_matrix_columns(p_tm_failing)

    v_t_failing_sum = np.sum(v_t_failing)
    v_t_failing = v_t_failing / v_t_failing_sum if v_t_failing_sum != 0 else v_t_failing

    return (
        p_mm,
        p_tm_passing,
        p_mt_passing,
        p_tt_passing,
        p_tm_failing,
        p_mt_failing,
        p_tt_failing,
        v_m,
        v_t_passing,
        v_t_failing,
        entity_index,
        test_index_passing,
        test_index_failing,
    )


def normalize_matrix_columns(p):
    """
    Normalize the columns of the matrix P so that each column sums to 1.
    :param p: The matrix to be normalized.
    :return: The normalized matrix.
    """
    column_sums = p.sum(axis=0)  # Sum along columns
    column_sums[column_sums == 0] = 1  # Avoid division by zero, set 0 sums to 1
    return p / column_sums  # Normalize the columns


# noinspection PyUnusedLocal
def get_page_rank(
    p_mm,
    p_tm,
    p_mt,
    p_tt,
    v_m,
    v_t,
    d=0.7,
    tol=1e-6,
    max_iter=100,
):
    """
    Compute the PageRank of the entities and tests in the call graph.
    :param p_mm: Method-to-method transition matrix (P_MM).
    :param p_tm: Test-to-method transition matrix (P_TM).
    :param p_mt: Method-to-test transition matrix (P_MT).
    :param p_tt: Test-to-test transition matrix (P_TT).
    :param v_m: Teleportation vector for methods.
    :param v_t: Teleportation vector for tests.
    :param d: Damping factor for PageRank.
    :param tol: Tolerance for convergence.
    :param max_iter: Maximum number of iterations.
    :return: Tuple of (x_m, x_t) where x_m are the PageRank scores for methods and x_t for tests.
    """
    x_m = np.zeros(p_mm.shape[0])
    x_t = np.zeros(p_tt.shape[0])
    # check that both arrays contain at least one element
    if x_m.size == 0 or x_t.size == 0:
        return x_m, x_t

    for _ in range(max_iter):
        x_m_old = x_m.copy()
        x_t_old = x_t.copy()

        y_m = d * (p_mm @ x_m + p_tm @ x_t)
        y_t = d * p_mt @ x_m + (1 - d) * v_t

        max_m = np.max(y_m)
        if max_m != 0:
            x_m = y_m / max_m

        max_t = np.max(y_t)
        if max_t != 0:
            x_t = y_t / max_t

        if np.linalg.norm(x_m - x_m_old) < tol and np.linalg.norm(x_t - x_t_old) < tol:
            break

    return x_m, x_t


def build_pr(project_name, bug_id, start=None, end=None):
    """
    Compute and persist PRFL PageRank scores for selected projects.

    :param project_name: Project identifier.
    :param bug_id: Optional single bug id.
    :param start: Optional lower bound bug id.
    :param end: Optional upper bound bug id.
    :returns: None
    """
    cg_dir = "call_graphs"
    os.makedirs(cg_dir, exist_ok=True)

    report_dir = "reports"
    os.makedirs(report_dir, exist_ok=True)
    report_file = os.path.join(report_dir, f"cg_{project_name}_pr.json")
    if os.path.exists(report_file):
        with open(report_file, "r") as f:
            report = json.load(f)
    else:
        report = dict()

    for project in t4p.get_projects(project_name, bug_id):
        if start is not None and project.bug_id < start:
            continue
        if end is not None and project.bug_id > end:
            continue
        identifier = project.get_identifier()
        if identifier not in report:
            report[identifier] = dict()
        print(identifier)
        pr_file = os.path.join(cg_dir, f"{identifier}_pr.json")
        if (
            project.test_status_buggy != TestStatus.FAILING
            or project.test_status_fixed != TestStatus.PASSING
            or (
                "check" in report[identifier]
                and report[identifier]["check"] == "successful"
                and os.path.exists(pr_file)
            )
        ):
            continue
        cg_file = os.path.join(cg_dir, f"{identifier}.json")
        if not os.path.exists(cg_file):
            continue
        with open(cg_file, "r") as f:
            call_graph_data = json.load(f)
        try:
            start_time = time.time()
            (
                p_mm,
                p_tm_passing,
                p_mt_passing,
                p_tt_passing,
                p_tm_failing,
                p_mt_failing,
                p_tt_failing,
                v_m,
                v_t_passing,
                v_t_failing,
                entity_index,
                test_index_passing,
                test_index_failing,
            ) = build_transition_matrix(call_graph_data)
            x_m_passing, x_t_passing = get_page_rank(
                p_mm, p_tm_passing, p_mt_passing, p_tt_passing, v_m, v_t_passing
            )
            x_m_failing, x_t_failing = get_page_rank(
                p_mm, p_tm_failing, p_mt_failing, p_tt_failing, v_m, v_t_failing
            )
            report[identifier]["time"] = time.time() - start_time
        except Exception as e:
            report[identifier]["check"] = "fail"
            report[identifier]["error"] = traceback.format_exception(e)
            continue
        else:
            report[identifier]["check"] = "successful"
            if "error" in report[identifier]:
                del report[identifier]["error"]
        page_rank_results = {
            "PASS": {
                "methods": dict(),
                "tests": dict(),
            },
            "FAIL": {
                "methods": dict(),
                "tests": dict(),
            },
        }
        for entity, idx in entity_index.items():
            page_rank_results["PASS"]["methods"][entity] = x_m_passing[idx]
            page_rank_results["FAIL"]["methods"][entity] = x_m_failing[idx]
        for test, idx in test_index_passing.items():
            page_rank_results["PASS"]["tests"][test] = x_t_passing[idx]
        for test, idx in test_index_failing.items():
            page_rank_results["FAIL"]["tests"][test] = x_t_failing[idx]

        with open(pr_file, "w") as f:
            json.dump(page_rank_results, f, indent=1)

    with open(report_file, "w") as f:
        json.dump(report, f, indent=1)


def get_lines_map(project):
    """
    Map each covered source line to its containing function tuple.

    :param project: Subject metadata.
    :returns: Mapping ``(file, line) -> (file, line, function, function_id)``.
    :rtype: dict[tuple[str, int], tuple]
    """
    path_to_lines = os.path.join(
        "call_graphs", f"{project.get_identifier()}_lines.json"
    )
    with open(path_to_lines, "r") as f:
        lines = json.load(f)
    lines_map = dict()
    for function_id in lines:
        details, function_lines = lines[function_id]
        details = tuple(details)
        for line in function_lines:
            line = tuple(line)
            lines_map[line] = details
    return lines_map


def get_page_ranks(project):
    """
    Load persisted PageRank scores for a project.

    :param project: Subject metadata.
    :returns: Parsed PageRank JSON payload.
    :rtype: dict
    """
    path_to_ranks = os.path.join("call_graphs", f"{project.get_identifier()}_pr.json")
    with open(path_to_ranks, "r") as f:
        return json.load(f)


def assign_weights_to_lines(type_, analyzer: Analyzer, lines, page_ranks):
    """
    Reweight analyzer spectra using method-level PRFL scores.

    :param type_: Analysis type to iterate (typically line).
    :param analyzer: Analyzer whose spectra are updated in-place.
    :param lines: Mapping from line locations to function descriptors.
    :param page_ranks: PRFL scores for failing and passing executions.
    :returns: None
    """
    for spectrum in analyzer.get_analysis_by_type(type_):
        spectrum: Line
        if (spectrum.file, spectrum.line) in lines:
            method = lines[(spectrum.file, spectrum.line)]
            entity_name = f"{method[2]} ({method[3]})"
            if (
                entity_name in page_ranks["FAIL"]["methods"]
                and entity_name in page_ranks["PASS"]["methods"]
            ):
                sfi = page_ranks["FAIL"]["methods"][entity_name]
                spi = page_ranks["PASS"]["methods"][entity_name]
            else:
                # Missing ranks default to neutral weighting to avoid dropping data.
                sfi = 1
                spi = 1
        else:
            sfi = 1
            spi = 1
        spectrum.failed_observed *= sfi
        spectrum.passed_observed *= spi
        spectrum.failed_not_observed = spectrum.failed - spectrum.failed_observed
        spectrum.passed_not_observed = spectrum.passed - spectrum.passed_observed


def get_results_for_type(
    type_,
    analyzer,
    project,
    location,
    faulty_lines,
    eval_metric=max_,
):
    """
    Evaluate PRFL-weighted suggestions for one analysis type.

    :returns: Pair ``(results, times)`` keyed by metric.
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


def evaluate_prfl(project_name, bug_id, start=None, end=None):
    """
    Evaluate fault localization after PRFL weighting.

    :param project_name: Project identifier.
    :param bug_id: Optional single bug id.
    :param start: Optional lower bound bug id.
    :param end: Optional upper bound bug id.
    :returns: None
    """
    Language.PYTHON.setup()
    os.makedirs("results", exist_ok=True)
    reports_dir = Path("reports")
    os.makedirs(reports_dir, exist_ok=True)
    report_file = reports_dir / f"suggestion_{project_name}_prfl.json"
    time_report = dict()
    for project in t4p.get_projects(project_name, bug_id):
        if start is not None and project.bug_id < start:
            continue
        if end is not None and project.bug_id > end:
            continue
        results_file = Path("results", f"{project.get_identifier()}_pr.json")
        if results_file.exists():
            continue
        results = dict()
        print(project)
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
            line = get_lines_map(project)
            page_ranks = get_page_ranks(project)
            assign_weights_to_lines(AnalysisType.LINE, analyzer, line, page_ranks)
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
