import argparse
import json
import os
import time
from pathlib import Path

import numpy as np
import tests4py.api as t4p
from sflkit import Analyzer
from sflkit.analysis.analysis_type import AnalysisType
from sflkit.analysis.spectra import Spectrum, Line
from sflkit.weights import TimeAnalyzer
from sflkit.evaluation import Rank, Scenario
from sflkit.language.language import Language
from tests4py.projects import TestStatus

from get_analysis import distances


def get_lines_map(project):
    path_to_lines = os.path.join(
        "call_graphs", f"{project.get_identifier()}_lines.json"
    )
    with open(path_to_lines, "r") as f:
        lines = json.load(f)
    lines_map = dict()
    for function_id in lines:
        details, function_lines = lines[function_id]
        for line in function_lines:
            lines_map[line] = details
    return lines_map


def get_page_ranks(project):
    path_to_ranks = os.path.join("call_graphs", f"{project.get_identifier()}_pr.json")
    with open(path_to_ranks, "r") as f:
        return json.load(f)


def assign_weights_to_lines(type_, analyzer: Analyzer, lines, page_ranks):
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
                sfi = 1
                spi = 1
        else:
            sfi = 1
            spi = 1
        spectrum.failed_observed = sfi * spectrum.failed_observed
        spectrum.passed_observed = spi * spectrum.passed_observed
        spectrum.failed_not_observed = spectrum.failed - spectrum.failed_observed
        spectrum.passed_not_observed = spectrum.passed - spectrum.passed_observed


# def prfl_TARANTULA(spectrum: Spectrum):
#     return (
#         spectrum.ef
#         / (spectrum.ef + spectrum.nf)
#         / (
#             spectrum.ef / (spectrum.ef + spectrum.nf)
#             + spectrum.ep / (spectrum.ep + spectrum.np)
#         )
#     )
#
#
# def prfl_OCHIAI(spectrum: Spectrum):
#     return spectrum.ef / np.sqrt(
#         (spectrum.ef + spectrum.nf) * (spectrum.ep + spectrum.np)
#     )
#
#
# def prfl_DSTAR(spectrum: Spectrum):
#     return spectrum.ef**2 / (spectrum.ep + spectrum.nf)
#
#
# def prfl_NAISH1(spectrum: Spectrum):
#     return -1 if spectrum.ef < spectrum.ef + spectrum.nf else spectrum.np
#
#
# def prfl_NAISH2(spectrum: Spectrum):
#     return spectrum.ef - spectrum.ep / (spectrum.ep + spectrum.np + 1)
#
#
# def prfl_GP13(spectrum: Spectrum):
#     return spectrum.ef * (1 + 1 / (2 * spectrum.ep + spectrum.ef))


def get_results_for_type(
    type_,
    analyzer,
    project,
    location,
    faulty_lines,
    eval_metric=max,
):
    results = dict()
    times = dict()
    for metric in [
        Spectrum.Tarantula,
        Spectrum.Ochiai,
        Spectrum.DStar,
        Spectrum.Naish1,
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


def main(project_name, bug_id, start=0, end=1000):
    Language.PYTHON.setup()
    os.makedirs("results", exist_ok=True)
    reports_dir = Path("reports")
    os.makedirs(reports_dir, exist_ok=True)
    report_file = reports_dir / f"suggestion_{project_name}_prfl.json"
    time_report = dict()
    for project in t4p.get_projects(project_name, bug_id):
        if project.bug_id < start or project.bug_id > end:
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
                    analyzer = TimeAnalyzer.load_with_dependencies(
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


if __name__ == "__main__":
    args = argparse.ArgumentParser()
    args.add_argument("-p", required=True, dest="project_name", help="project name")
    args.add_argument("-i", type=int, default=None, dest="bug_id", help="bug id")
    args.add_argument("-s", type=int, default=None, dest="start", help="start")
    args.add_argument("-e", type=int, default=None, dest="end", help="end")

    arguments = args.parse_args()
    name = arguments.project_name
    id_ = arguments.bug_id
    s = arguments.start or 0
    e = arguments.end or 1000

    main(name, id_, s, e)
