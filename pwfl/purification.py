"""
Test Case Purification Integration for PWFL Pipeline

This module integrates test case purification into the event collection pipeline.
It purifies failing tests, instruments the code, and collects events in one pass.
"""

import json
import os
import shutil
import time
import traceback
from pathlib import Path
from typing import Optional

import tests4py.api as t4p
from sflkit import Config, Analyzer
from sflkit.analysis.analysis_type import AnalysisType
from sflkit.analysis.factory import LineFactory
from sflkit.analysis.spectra import Spectrum
from sflkit.analysis.suggestion import Suggestion
from sflkit.evaluation import Rank, Scenario
from sflkit.language.language import Language
from sflkit.runners import PytestRunner
from sflkit.weights import ProximityAnalyzer
from tests4py.environment import env_on, activate_venv
from tests4py.projects import TestStatus, Project
from tests4py.sfl import (
    SFLInstrumentReport,
    instrument,
    get_events_path,
    SFLEventsReport,
    DEFAULT_TIME_OUT,
)
from tests4py.sfl.constants import DEFAULT_EXCLUDES
from tests4py.tests.utils import get_pytest_skip

from pwfl.analyze import get_event_files, distances
from pwfl.logger import LOGGER
from pwfl.utils import fix_sanic, fix_sanic_after

# Import purify_tests from the tcp package
from tcp.purification import purify_tests, rank_refinement


def create_config(
    project: Project,
    src: Path,
    dst: Path,
    metrics: str = None,
    events_path: Optional[Path] = None,
    mapping: Optional[Path] = None,
    include_suffix: bool = False,
):
    if project.included_files:
        includes = project.included_files
        excludes = project.excluded_files
    elif project.excluded_files:
        includes = list()
        excludes = project.excluded_files
    else:
        includes = list()
        excludes = DEFAULT_EXCLUDES
    if project.project_name in ("calculator", "markup", "thefuck"):
        project.test_base = Path("tests")
    test_files = list({str(file.split("::")[0]) for file in project.test_cases})
    return Config.create(
        path=str(src.absolute()),
        language="python",
        events="line",
        test_events="test_start,test_end,test_line,test_def,test_use,test_assert",
        ignore_inner=str(
            project.project_name == "pysnooper"
        ),  # pysnooper defines a testcase function inside a
        # testcase, which it traces. With the instrumentation, the trace is not correct because the correct trace is
        # asserted. Hence, inner functions are ignored.
        metrics=metrics or "",
        predicates="line",
        passing=str(
            get_events_path(
                project=project,
                passing=True,
                events_path=events_path,
                include_suffix=include_suffix,
            )
        ),
        failing=str(
            get_events_path(
                project=project,
                passing=False,
                events_path=events_path,
                include_suffix=include_suffix,
            )
        ),
        working=str(dst.absolute()),
        include='"' + '","'.join(includes) + '"',
        exclude='"' + '","'.join(excludes) + '"',
        test_files='"' + '","'.join(test_files) + '"',
        mapping_path=str(mapping.absolute()) if mapping else "",
    )


def sflkit_instrument(
    project: Project,
    src: os.PathLike,
    dst: os.PathLike,
    mapping: os.PathLike = None,
    report: SFLInstrumentReport = None,
):
    report = report or SFLInstrumentReport()
    work_dir = Path(src)
    try:
        if dst is None:
            raise ValueError("Destination required for instrument")
        report.project = project
        instrument(
            create_config(
                project,
                work_dir,
                Path(dst),
                mapping=Path(mapping) if mapping else None,
            ),
        )
        report.successful = True
    except BaseException as e:
        report.raised = e
        report.successful = False
    return report


def sflkit_unittest(
    work_dir: os.PathLike,
    project: Project,
    output: Path = None,
):
    report = SFLEventsReport()
    work_dir = Path(work_dir)
    try:
        if output is None:
            output = get_events_path(project, include_suffix=True)
        report.project = project
        environ = env_on(project)
        environ = activate_venv(work_dir, environ)
        runner = PytestRunner(timeout=DEFAULT_TIME_OUT)
        k = None
        if project.skip_tests:
            k = get_pytest_skip(project.skip_tests)
        files = project.relevant_test_files
        runner.run(
            directory=work_dir,
            output=output,
            files=files,
            base=project.test_base,
            environ=environ,
            k=k,
        )
        report.successful = True
        report.passing = runner.passing_tests
        report.failing = runner.failing_tests
        report.undefined = runner.undefined_tests
    except BaseException as e:
        report.raised = e
        report.successful = False
    return report


def parse_test_id(test_id: str) -> tuple:
    """
    Parse a test identifier into components.

    Args:
        test_id: Test identifier (e.g., "file.py::test_func[params]" or "file.py::Class::test_method[params]")

    Returns:
        Tuple of (file, class_name, test_name, param_suffix)
        class_name is None for module-level functions
        param_suffix is None for non-parameterized tests
    """
    # Extract parameter suffix if present (e.g., [1-hello])
    param_suffix = None
    test_id_base = test_id
    if "[" in test_id and test_id.endswith("]"):
        bracket_pos = test_id.rfind("[")
        param_suffix = test_id[bracket_pos + 1 : -1]
        test_id_base = test_id[:bracket_pos]

    parts = test_id_base.split("::")

    if len(parts) == 3:
        # Class method: file::class::method
        return parts[0], parts[1], parts[2], param_suffix
    elif len(parts) == 2:
        # Module-level function: file::function
        return parts[0], None, parts[1], param_suffix
    else:
        # Unknown format
        return None, None, None, None


def purify(
    project: Project,
    identifier: str,
    report: dict,
    enable_slicing: bool = True,
):
    # Initialize report for this project
    report[identifier]["time"] = dict()

    # Step 1: Checkout the project
    original_checkout = Path("tmp", f"{identifier}")
    if not original_checkout.exists():
        r = t4p.checkout(project)
        if r.successful:
            report[identifier]["checkout"] = "successful"
        else:
            report[identifier]["checkout"] = "failed"
            report[identifier]["error"] = traceback.format_exception(r.raised)
            return None
        original_checkout = r.location
    else:
        report[identifier]["checkout"] = "cached"

    if project.project_name == "sanic":
        fix_sanic(
            project=project,
            original_checkout=original_checkout,
        )

    r = t4p.build(original_checkout)
    if not r.successful:
        report[identifier]["build"] = "failed"
        report[identifier]["error"] = traceback.format_exception(r.raised)
        return None
    if project.project_name == "sanic":
        fix_sanic_after(
            project=project,
            original_checkout=original_checkout,
        )
    report[identifier]["build"] = "successful"

    venv_env = env_on(project)
    venv_env = activate_venv(original_checkout, venv_env)

    purified_tests_dir = Path("tmp", f"{identifier}_purified")
    purified_tests_dir.mkdir(parents=True, exist_ok=True)

    if project.project_name in ("calculator", "markup", "thefuck"):
        project.test_base = Path("tests")
    test_base = original_checkout / (project.test_base or Path("tests"))
    if test_base.is_file():
        test_base = test_base.parent

    start = time.time()
    # noinspection PyBroadException
    try:
        purified_mapping = purify_tests(
            src_dir=original_checkout,
            dst_dir=purified_tests_dir,
            failing_tests=project.test_cases,
            enable_slicing=enable_slicing,
            test_base=test_base,
            venv=venv_env,
        )
        report[identifier]["time"]["purification"] = time.time() - start
        report[identifier]["purification"] = "successful"
        report[identifier]["purified_tests"] = {
            test_id: [
                {
                    "file": str(purified_file.relative_to(purified_tests_dir)),
                    "params": param_suffix,
                }
                for purified_file, param_suffix in file_param_tuples
            ]
            for test_id, file_param_tuples in purified_mapping.items()
        }
        return purified_mapping
    except:
        report[identifier]["time"]["purification"] = time.time() - start
        report[identifier]["purification"] = "failed"
        report[identifier]["error"] = traceback.format_exc()
    return None


def update_project_purified(
    project: Project,
    identifier: str,
    purified_mapping: dict[str, list[tuple[Path, Optional[str]]]],
):
    purified_tests_dir = Path("tmp", f"{identifier}_purified")
    path = Path("tmp", f"{identifier}_tcp")
    # Copy project to tcp path
    shutil.rmtree(path, ignore_errors=True)
    shutil.copytree(
        Path("tmp", f"{identifier}"),
        path,
        ignore_dangling_symlinks=True,
    )
    if project.project_name in ("calculator", "markup", "thefuck"):
        project.test_base = Path("tests")
    test_base_sfl = path / (project.test_base or Path("tests"))
    try:
        test_base_sfl.mkdir(parents=True, exist_ok=True)
    except FileExistsError:
        test_base_sfl = test_base_sfl.parent

    for item in purified_tests_dir.rglob("*"):
        if item.is_file():
            rel_path = item.relative_to(purified_tests_dir)
            dst = test_base_sfl / rel_path
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, dst)

    failing_tests = []
    relevant_files = (
        set(project.relevant_test_files) if project.relevant_test_files else set()
    )
    for test_id in project.test_cases:
        file_path, class_name, test_name, param_suffix = parse_test_id(test_id)
        if file_path is None:
            continue
        if test_id not in purified_mapping:
            continue
        for purified_file, purified_param_suffix in purified_mapping[test_id]:
            if test_id in relevant_files:
                relevant_files.remove(test_id)
            rel_path = purified_file.relative_to(purified_tests_dir)
            purified_file_full = test_base_sfl / rel_path
            purified_file_rel = purified_file_full.relative_to(path)
            if class_name:
                base_test_id = f"{purified_file_rel}::{class_name}::{test_name}"
            else:
                base_test_id = f"{purified_file_rel}::{test_name}"
            if purified_param_suffix:
                purified_test_id = f"{base_test_id}[{purified_param_suffix}]"
            else:
                purified_test_id = base_test_id

            failing_tests.append(purified_test_id)
            relevant_files.add(purified_test_id)
    project.test_cases = failing_tests
    project.relevant_test_files = relevant_files


def build(
    project: Project,
    identifier: str,
    report: dict,
):
    mapping = Path("mappings", f"{identifier}_tcp.json")
    src_path = Path("tmp", f"{identifier}_tcp")
    sfl_path = Path("tmp", f"sfl_{identifier}_tcp")
    start = time.time()
    r = sflkit_instrument(
        project,
        src_path,
        sfl_path,
        mapping=mapping,
    )
    if project.project_name == "sanic":
        fix_sanic_after(
            project=project,
            original_checkout=sfl_path,
        )
    report[identifier]["time"]["instrument"] = time.time() - start
    if r.successful:
        report[identifier]["build"] = "successful"
    else:
        report[identifier]["build"] = "failed"
        report[identifier]["error"] = traceback.format_exception(r.raised)

    with open(mapping, "r") as f:
        mapping_content = json.load(f)
    with open(mapping, "w") as f:
        json.dump(mapping_content, f, indent=1)


def collect(
    project: Project,
    identifier: str,
    report: dict,
):
    sfl_path = Path("tmp", f"sfl_{identifier}_tcp")
    events_base = Path(
        "sflkit_events", project.project_name, "tcp", str(project.bug_id)
    )
    # Step 7: Run tests to collect events
    shutil.rmtree(events_base, ignore_errors=True)
    if project.project_name == "ansible":
        """
        When ansible is executed it sometimes loads the original version.
        Even though it is never installed and the virtual environment clearly
        contains the instrumented version.
        This prevents an event collection.
        Removing the original version fixes this problem.
        """
        shutil.rmtree(Path("tmp", f"{identifier}"), ignore_errors=True)
    start = time.time()
    r = sflkit_unittest(
        sfl_path,
        project,
        output=events_base,
    )
    report[identifier]["time"]["test"] = time.time() - start
    if r.successful:
        report[identifier]["test"] = "successful"

        # For TCP, save mapping of event files to purified test names
        if (events_base / "failing").exists():
            test_event_mapping = {}
            # Map each event file to its corresponding test name
            # Event files are numbered starting from 0
            # The test order matches project.test_cases
            for run_id, filename in enumerate(
                sorted(os.listdir(events_base / "failing"))
            ):
                if run_id < len(project.test_cases):
                    test_name = project.test_cases[run_id]
                    test_event_mapping[filename] = test_name

            # Save the mapping
            mapping_dir = Path("tcp_mappings")
            mapping_dir.mkdir(exist_ok=True, parents=True)
            mapping_file = mapping_dir / f"{identifier}.json"
            with open(mapping_file, "w") as f:
                json.dump(test_event_mapping, f, indent=1)
    else:
        report[identifier]["test"] = "failed"
        report[identifier]["error"] = traceback.format_exception(r.raised)
        return events_base

    return events_base


def get_tcp_events(
    project_name, bug_id=None, start=None, end=None, enable_slicing=True
):
    """
    Collect events using test case purification.

    This is the main entry point for TCP-based event collection.
    It replaces the original get_events function when using TCP.

    Args:
        project_name: Name of the project
        bug_id: Specific bug ID (optional)
        start: Start bug ID for range (optional)
        end: End bug ID for range (optional)
        enable_slicing: Whether to enable dynamic slicing (default: False)
    """
    report_dir = Path("reports")
    report_dir.mkdir(exist_ok=True)
    report_file = report_dir / f"tcp_{project_name}.json"

    if report_file.exists():
        with open(report_file, "r") as f:
            report = json.load(f)
    else:
        report = {}

    for project in t4p.get_projects(project_name, bug_id):
        if start is not None and project.bug_id < start:
            continue
        if end is not None and project.bug_id > end:
            continue

        identifier = project.get_identifier()
        LOGGER.info(f"Processing {identifier} with TCP")

        # Skip if already processed successfully
        if (
            identifier in report
            and "check" in report[identifier]
            and report[identifier]["check"] == "successful"
        ):
            LOGGER.info(f"Skipping {identifier} - already processed")
            continue

        report[identifier] = {}

        # Check project status
        if (
            project.test_status_buggy != TestStatus.FAILING
            or project.test_status_fixed != TestStatus.PASSING
        ):
            report[identifier]["status"] = "skipped"
            LOGGER.info(f"Skipping {identifier} - invalid test status")
            continue

        report[identifier]["status"] = "running"

        # Run the purification and event collection pipeline
        try:
            purified_mapping = purify(
                project,
                identifier,
                report,
                enable_slicing=enable_slicing,
            )
            if purified_mapping is None:
                report[identifier]["status"] = "error"
                continue

            update_project_purified(
                project,
                identifier,
                purified_mapping,
            )
            LOGGER.info(f"Updated project purified for {identifier}")

            build(
                project,
                identifier,
                report,
            )
            if report[identifier]["build"] != "successful":
                report[identifier]["status"] = "error"
                LOGGER.error(f"TCP Build failed for {identifier}")
                continue
            events_path = collect(
                project,
                identifier,
                report,
            )
            if events_path is None:
                report[identifier]["status"] = "error"
                LOGGER.error(f"TCP Event collection failed for {identifier}")
                continue
            else:
                LOGGER.info(f"TCP Event collection successful for {identifier}")

            report[identifier]["check"] = "successful"
            report[identifier]["status"] = "completed"
        except Exception as e:
            report[identifier]["status"] = "error"
            report[identifier]["error"] = traceback.format_exception(e)
            LOGGER.error(f"Skipping {identifier} - {e}")
        finally:
            # Save report after each project
            with open(report_file, "w") as f:
                json.dump(report, f, indent=1)

    LOGGER.info(f"TCP event collection complete. Report saved to {report_file}")


def tcp_analyze_project(
    project: Project,
    analysis_file: os.PathLike,
    report: dict,
    suffix: str,
    identifier: str = None,
    model_class=None,
) -> Analyzer:
    os.makedirs("analysis", exist_ok=True)
    events = Path(
        "sflkit_events",
        project.project_name,
        "tcp",
        str(project.bug_id),
    )
    mapping_file = Path("mappings", f"{identifier}_tcp.json")
    if not events.exists():
        raise FileNotFoundError(f"Events not found for {project}")
    if not mapping_file.exists():
        raise FileNotFoundError(f"Mapping not found for {project}")
    failing, passing, undefined = get_event_files(events, mapping_file)
    start = time.time()
    if model_class:
        analyzer = ProximityAnalyzer(
            model_class,
            relevant_event_files=failing,
            irrelevant_event_files=passing,
            factory=LineFactory(),
        )
    else:
        analyzer = Analyzer(
            relevant_event_files=failing,
            irrelevant_event_files=passing,
            factory=LineFactory(),
        )
    analyzer.analyze()
    report[project.get_identifier()][f"lines{suffix}"] = time.time() - start
    analyzer.dump(analysis_file, indent=1)

    identifier = project.get_identifier()
    purified_spectra = []

    # Load the test-event mapping if available
    mapping_dir = Path("tcp_mappings")
    tcp_mapping_file = mapping_dir / f"{identifier}_tcp.json"
    test_event_mapping = {}
    if tcp_mapping_file.exists():
        with open(tcp_mapping_file, "r") as f:
            test_event_mapping = json.load(f)

    # Extract coverage from each failing event file (purified test)
    for event_file in failing:
        spectrum = {}

        # Get the test name for this event file
        event_filename = Path(event_file.path).name
        test_name = test_event_mapping.get(event_filename, f"unknown_{event_filename}")
        for ao in analyzer.get_analysis_by_type(AnalysisType.LINE):
            if event_file in ao.hits:
                if ao.hits[event_file] > 0:
                    # noinspection PyUnresolvedReferences
                    spectrum[f"{ao.file}:{ao.line}"] = 1
                else:
                    # noinspection PyUnresolvedReferences
                    spectrum[f"{ao.file}:{ao.line}"] = 0
            else:
                # noinspection PyUnresolvedReferences
                spectrum[f"{ao.file}:{ao.line}"] = 0
        purified_spectra.append(
            {
                "test_name": test_name,
                "spectrum": spectrum,
            }
        )
    # Save purified spectra to file
    spectra_dir = Path("tcp_spectra")
    spectra_dir.mkdir(exist_ok=True)
    spectra_file = spectra_dir / f"{identifier}{suffix}.json"
    with open(spectra_file, "w") as f:
        json.dump(purified_spectra, f, indent=1)

    LOGGER.info(f"Saved {len(purified_spectra)} purified spectra for {identifier}")

    return analyzer


# noinspection DuplicatedCode
def tcp_analyze(project_name, bug_id=None, start=None, end=None):
    report = dict()
    report_dir = Path("reports")
    os.makedirs(report_dir, exist_ok=True)
    for project in t4p.get_projects(project_name, bug_id):
        if start is not None and project.bug_id < start:
            continue
        if end is not None and project.bug_id > end:
            continue
        LOGGER.info(project)
        if (
            project.test_status_buggy != TestStatus.FAILING
            or project.test_status_fixed != TestStatus.PASSING
        ):
            continue
        identifier = project.get_identifier()
        project.buggy = True
        report[project.get_identifier()] = dict()
        for suffix, model_class in distances:
            analysis_file = Path("analysis", f"{project}{suffix}_tcp.json")
            if analysis_file.exists():
                continue
            tcp_analyze_project(
                project, analysis_file, report, suffix, identifier, model_class
            )

    with open(report_dir / f"analysis_{project_name}_tcp.json", "w") as f:
        json.dump(report, f, indent=1)


def tcp_get_results_for_type(
    type_,
    analyzer,
    project,
    location,
    faulty_lines,
    suffix: str,
    eval_metric=max,
):
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
        spectra: list[Spectrum] = analyzer.get_analysis_by_type(type_)
        weighted_sus_locations = []
        for spectrum in spectra:
            suggestion = spectrum.get_suggestion(
                metric=metric,
                base_dir=location,
                use_weight=False,
            )
            for location in suggestion.lines:
                weighted_sus_locations.append(
                    (location, suggestion.suspiciousness, spectrum.weight)
                )
        times[metric.__name__] = time.time() - time_start

        suggestions = []
        # If TCP, adjust ranks using rank_refinement
        try:
            # Build mapping: statement string -> (original Suggestion, Location)
            stmt_to_location = {}
            original_scores = {}
            weights = {}

            for line, sus, weight in weighted_sus_locations:
                stmt = str(line)
                stmt_to_location[stmt] = line
                original_scores[stmt] = sus
                weights[stmt] = weight

            # Load purified spectra from saved file
            identifier = project.get_identifier()
            spectra_dir = Path("tcp_spectra")
            spectra_file = spectra_dir / f"{identifier}{suffix}.json"

            if not spectra_file.exists():
                LOGGER.error(f"Warning: TCP spectra file not found: {spectra_file}")
                LOGGER.error("Run analysis step first to generate TCP spectra")
                raise FileNotFoundError(f"TCP spectra file not found: {spectra_file}")
            else:
                with open(spectra_file, "r") as f:
                    purified_data = json.load(f)

                # Extract just the spectra (without test names)
                purified_spectra = [item["spectrum"] for item in purified_data]

                # Apply rank refinement
                if purified_spectra:
                    refined_scores = rank_refinement(
                        original_scores, purified_spectra, technique="combined"
                    )

                    # Rebuild suggestions as Suggestion objects with refined scores
                    # Group by score (statements with same score go in one Suggestion)
                    score_to_locations = {}
                    for stmt, score in refined_scores.items():
                        score *= weights.get(stmt, 1.0)  # Reapply weight if any
                        if score not in score_to_locations:
                            score_to_locations[score] = []
                        if stmt in stmt_to_location:
                            score_to_locations[score].append(stmt_to_location[stmt])

                    # Create Suggestion objects sorted by score
                    suggestions = [
                        Suggestion(locations, score)
                        for score, locations in sorted(
                            score_to_locations.items(),
                            key=lambda x: x[0],
                            reverse=True,
                        )
                    ]

                    LOGGER.info(
                        f"TCP rank refinement applied {project}{suffix}: {len(purified_spectra)} spectra used"
                    )
                else:
                    LOGGER.info(
                        f"Warning: No purified spectra found in file for {project}{suffix}"
                    )
                    suggestions = analyzer.get_sorted_suggestions(
                        location, metric, type_
                    )
        except Exception as e:
            LOGGER.error(f"TCP rank refinement failed: {e}")
            raise e

        LOGGER.info(
            f"Generated {len(suggestions)} suggestions for {project}{suffix} using {metric.__name__}"
        )

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


def tcp_evaluate(project_name, bug_id, start=None, end=None):
    Language.PYTHON.setup()
    os.makedirs("results", exist_ok=True)
    reports_dir = Path("reports")
    os.makedirs(reports_dir, exist_ok=True)
    report_file = reports_dir / f"suggestion_{project_name}_tcp.json"
    time_report = dict()
    for project in t4p.get_projects(project_name, bug_id):
        if start is not None and project.bug_id < start:
            continue
        if end is not None and project.bug_id > end:
            continue
        results_file = Path("results", f"{project.get_identifier()}_tcp.json")
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
            analysis_file = Path("analysis", f"{project}{suffix}_tcp.json")
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
            ) = tcp_get_results_for_type(
                AnalysisType.LINE, analyzer, project, location, faulty_lines, suffix
            )
        results[project.get_identifier()] = subject_results
        time_report[project.get_identifier()] = subject_times
        with open(results_file, "w") as f:
            json.dump(results, f, indent=1)
    with open(report_file, "w") as f:
        json.dump(time_report, f, indent=1)
