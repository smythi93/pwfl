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
from sflkit import Config
from sflkit.runners import PytestRunner
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

from pwfl.logger import LOGGER

# Import purify_tests from the tcp package
from tcp.purification import purify_tests


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
    if project.project_name in ("calculator", "markup"):
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


def purify_and_collect_events(
    project: Project,
    identifier: str,
    report: dict,
    enable_slicing: bool = False,
):
    """
    Purify tests and collect events for a single project.

    This function:
    1. Checks out and builds the project
    2. Purifies the failing test cases
    3. Instruments the code with purified tests
    4. Runs tests once to collect both line and test events

    Args:
        project: The tests4py project
        identifier: Project identifier string
        report: Report dictionary to update
        enable_slicing: Whether to enable dynamic slicing in purification

    Returns:
        Path to the events directory
    """
    events_base = Path(
        "sflkit_events", project.project_name, "tcp", str(project.bug_id)
    )

    # Initialize report for this project
    report[identifier]["time"] = dict()

    # Step 1: Checkout the project
    start = time.time()
    original_checkout = Path("tmp", f"{identifier}")
    if not original_checkout.exists():
        r = t4p.checkout(project)
        report[identifier]["time"]["checkout"] = time.time() - start
        if r.successful:
            report[identifier]["checkout"] = "successful"
        else:
            report[identifier]["checkout"] = "failed"
            report[identifier]["error"] = traceback.format_exception(r.raised)
            return events_base
        original_checkout = r.location
    else:
        report[identifier]["checkout"] = "cached"

    # Step 2: Build the project (creates venv)
    start = time.time()
    r = t4p.build(original_checkout)
    report[identifier]["time"]["build"] = time.time() - start
    if not r.successful:
        report[identifier]["build"] = "failed"
        report[identifier]["error"] = traceback.format_exception(r.raised)
        return events_base
    report[identifier]["build"] = "successful"

    venv_env = env_on(project)
    venv_env = activate_venv(original_checkout, venv_env)

    # Step 3: Purify the failing tests
    start = time.time()
    purified_tests_dir = Path("tmp", f"{identifier}_purified")
    purified_tests_dir.mkdir(parents=True, exist_ok=True)

    # Get test base directory
    # Handle special cases for calculator and markup
    if project.project_name in ("calculator", "markup", "thefuck"):
        project.test_base = Path("tests")
    test_base = original_checkout / (project.test_base or Path("tests"))

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
                    "params": param_suffix
                }
                for purified_file, param_suffix in file_param_tuples
            ]
            for test_id, file_param_tuples in purified_mapping.items()
        }
    except Exception as e:
        report[identifier]["time"]["purification"] = time.time() - start
        report[identifier]["purification"] = "failed"
        report[identifier]["error"] = traceback.format_exc()
        LOGGER.error(f"Purification failed for {identifier}: {e}")
        return events_base

    # Step 4: Create a modified checkout with purified tests
    # Copy the original checkout to a new location
    tcp_path = Path("tmp", f"{identifier}_tcp")
    if tcp_path.exists():
        shutil.rmtree(tcp_path)
    shutil.copytree(original_checkout, tcp_path, symlinks=True)

    # Replace test files with purified versions
    test_base_sfl = tcp_path / (project.test_base or Path("tests"))

    # Ensure test_base_sfl exists
    test_base_sfl.mkdir(parents=True, exist_ok=True)

    # Copy ALL files from purified_tests_dir to test_base_sfl
    # This includes both purified test files and modified original test files
    # Need to handle both files in root and in subdirectories
    for item in purified_tests_dir.rglob("*"):
        if item.is_file():
            # Get relative path from purified_tests_dir
            rel_path = item.relative_to(purified_tests_dir)
            dst = test_base_sfl / rel_path
            # Ensure parent directory exists
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, dst)

    # Step 5: Get the new failing tests after purification
    failing_tests = []
    relevant_files = (
        set(project.relevant_test_files) if project.relevant_test_files else set()
    )
    for test_id in project.test_cases:
        file_path, class_name, test_name, param_suffix = parse_test_id(test_id)
        if file_path is None:
            continue
        # get correct test id for purified tests
        if test_id not in purified_mapping:
            continue

        # purified_mapping[test_id] is now a list of (purified_file, param_suffix) tuples
        for purified_file, purified_param_suffix in purified_mapping[test_id]:
            # Get relative path from purified_tests_dir
            rel_path = purified_file.relative_to(purified_tests_dir)

            # Construct the full path in tcp_path
            purified_file_full = test_base_sfl / rel_path

            # Get path relative to tcp_path (project root) for test ID
            purified_file_rel = purified_file_full.relative_to(tcp_path)

            # Build base test ID
            if class_name:
                # Class method: relative_path::class::method
                base_test_id = f"{purified_file_rel}::{class_name}::{test_name}"
            else:
                # Module-level function: relative_path::function
                base_test_id = f"{purified_file_rel}::{test_name}"

            # Add parameter suffix if present (for parameterized tests)
            if purified_param_suffix:
                purified_test_id = f"{base_test_id}[{purified_param_suffix}]"
            else:
                purified_test_id = base_test_id

            failing_tests.append(purified_test_id)
            relevant_files.add(purified_test_id)

    # Step 6: Instrument the code with sflkit
    LOGGER.info(f"Purified tests: {failing_tests}")
    LOGGER.info(f"Relevant files: {relevant_files}")
    project.test_cases = failing_tests
    project.relevant_test_files = relevant_files
    mapping = Path("mappings", f"{project}_tcp.json")
    sfl_path = Path("tmp", f"sfl_{identifier}_tcp")
    start = time.time()
    r = sflkit_instrument(
        project,
        tcp_path,
        sfl_path,
        mapping=mapping,
    )
    report[identifier]["time"]["instrument"] = time.time() - start
    if r.successful:
        report[identifier]["build"] = "successful"
    else:
        report[identifier]["build"] = "failed"
        report[identifier]["error"] = traceback.format_exception(r.raised)
        return events_base

    with open(mapping, "r") as f:
        mapping_content = json.load(f)
    with open(mapping, "w") as f:
        json.dump(mapping_content, f, indent=1)

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
        shutil.rmtree(original_checkout, ignore_errors=True)
    start = time.time()
    r = sflkit_unittest(
        sfl_path,
        project,
        output=events_base,
    )
    report[identifier]["time"]["test"] = time.time() - start
    if r.successful:
        report[identifier]["test"] = "successful"
    else:
        report[identifier]["test"] = "failed"
        report[identifier]["error"] = traceback.format_exception(r.raised)
        return events_base

    return events_base


def get_tcp_events(
    project_name, bug_id=None, start=None, end=None, enable_slicing=False
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
            purify_and_collect_events(
                project,
                identifier,
                report,
                enable_slicing=enable_slicing,
            )
        except Exception as e:
            report[identifier]["status"] = "error"
            report[identifier]["error"] = traceback.format_exception(e)
            LOGGER.error(f"Error processing {identifier}: {e}")

        # Save report after each project
        with open(report_file, "w") as f:
            json.dump(report, f, indent=1)

    LOGGER.info(f"TCP event collection complete. Report saved to {report_file}")
