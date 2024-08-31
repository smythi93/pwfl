import argparse
import json
import os
from pathlib import Path
import tests4py.api as t4p
from sflkit import Analyzer
from sflkit.analysis.analysis_type import AnalysisType
from sflkit.analysis.spectra import Spectrum
from sflkit.evaluation import Rank, Scenario, Average
from sflkit.fendr import SliceAnalyzer
from sflkit.language.language import Language

from tests4py.projects import TestStatus

from get_analysis import analyze, slices


def get_results_for_type(
    type_,
    analyzer,
    project,
    report,
    faulty_lines,
    eval_metric=max,
):
    results = dict()
    for metric in [Spectrum.Tarantula, Spectrum.Ochiai, Spectrum.DStar]:
        suggestions = analyzer.get_sorted_suggestions(report.location, metric, type_)
        rank = Rank(
            suggestions, total_number_of_locations=project.loc, metric=eval_metric
        )
        results[metric.__name__] = dict()
        for scenario in Scenario:
            results[metric.__name__][scenario.value] = {
                "top-5": rank.top_n(faulty_lines, 5, scenario),
                "top-10": rank.top_n(faulty_lines, 10, scenario),
                "top-200": rank.top_n(faulty_lines, 200, scenario),
                "exam": rank.exam(faulty_lines, scenario),
                "wasted-effort": rank.wasted_effort(faulty_lines, scenario),
            }
    return results


def main(project_name, bug_id, start=0, end=1000):
    Language.PYTHON.setup()
    os.makedirs("results", exist_ok=True)
    for project in t4p.get_projects(project_name, bug_id):
        if project.bug_id < start or project.bug_id > end:
            continue
        results_file = Path("results", f"{project.get_identifier()}.json")
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
        report = t4p.checkout(project)
        if not report.successful:
            raise report.raised
        for suffix, model_class in slices:
            analysis_file = Path("analysis", f"{project}{suffix}.json")
            if analysis_file.exists():
                if model_class is None:
                    analyzer = Analyzer.load(analysis_file)
                else:
                    analyzer = SliceAnalyzer.load_with_slice(analysis_file, model_class)
            else:
                analyzer = analyze(project, analysis_file, model_class=model_class)
            faulty_lines = set(t4p.get_faulty_lines(project))
            subject_results[f"line{suffix}"] = get_results_for_type(
                AnalysisType.LINE, analyzer, project, report, faulty_lines
            )
        results[project.get_identifier()] = subject_results
        with open(results_file, "w") as f:
            json.dump(results, f, indent=1)


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
