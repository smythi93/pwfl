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

import tests4py.api as t4p
from tests4py import sfl
from tests4py.projects import TestStatus, Project

from pwfl.events import (
    sflkit_instrument,
)
from pwfl.logger import LOGGER

# Import purify_tests from the tcp package
from tcp.purification import purify_tests


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


def get_venv_python(project: Project) -> Path:
    """
    Get the path to the Python executable in the project's virtual environment.

    Args:
        project: The tests4py project

    Returns:
        Path to the Python executable in the venv
    """
    venv_location = (
        Path.home()
        / ".t4p"
        / "projects"
        / project.project_name
        / f"venv_{project.bug_id}"
    )
    return venv_location / "bin" / "python"


def get_venv_environment(project: Project) -> dict:
    """
    Get the environment variables for running tests in the project's venv.

    Args:
        project: The tests4py project

    Returns:
        Dictionary of environment variables
    """
    venv_location = (
        Path.home()
        / ".t4p"
        / "projects"
        / project.project_name
        / f"venv_{project.bug_id}"
    )

    env = os.environ.copy()
    env["VIRTUAL_ENV"] = str(venv_location)
    env["PATH"] = f"{venv_location / 'bin'}:{env.get('PATH', '')}"
    return env


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
    venv_location = (
        Path.home()
        / ".t4p"
        / "projects"
        / project.project_name
        / f"venv_{project.bug_id}"
    )
    if not venv_location.exists():
        start = time.time()
        r = t4p.build(original_checkout)
        report[identifier]["time"]["build"] = time.time() - start
        if not r.successful:
            report[identifier]["build"] = "failed"
            report[identifier]["error"] = traceback.format_exception(r.raised)
            return events_base
        report[identifier]["build"] = "successful"
    else:
        report[identifier]["build"] = "cached"

    # Step 3: Purify the failing tests
    start = time.time()
    purified_tests_dir = Path("tmp", f"{identifier}_purified")
    purified_tests_dir.mkdir(parents=True, exist_ok=True)

    # Get venv Python and environment
    venv_python = str(get_venv_python(project))
    venv_env = get_venv_environment(project)

    # Get test base directory
    # Handle special cases for calculator and markup
    if project.project_name in ("calculator", "markup"):
        project.test_base = Path("tests")
    test_base = original_checkout / (project.test_base or Path("tests"))

    try:
        purified_mapping = purify_tests(
            src_dir=original_checkout,
            dst_dir=purified_tests_dir,
            failing_tests=project.test_cases,
            enable_slicing=enable_slicing,
            test_base=test_base,
            venv_python=venv_python,
            venv=venv_env,
        )
        report[identifier]["time"]["purification"] = time.time() - start
        report[identifier]["purification"] = "successful"
        report[identifier]["purified_tests"] = {
            test_id: [str(p.relative_to(purified_tests_dir)) for p in paths]
            for test_id, paths in purified_mapping.items()
        }
    except Exception as e:
        report[identifier]["time"]["purification"] = time.time() - start
        report[identifier]["purification"] = "failed"
        report[identifier]["error"] = traceback.format_exc()
        LOGGER.error(f"Purification failed for {identifier}: {e}")
        return events_base

    # Step 4: Create a modified checkout with purified tests
    # Copy the original checkout to a new location
    sfl_path = Path("tmp", f"sfl_{identifier}_purified")
    if sfl_path.exists():
        shutil.rmtree(sfl_path)
    shutil.copytree(original_checkout, sfl_path, symlinks=True)

    # Replace test files with purified versions
    test_base_sfl = sfl_path / (project.test_base or Path("tests"))

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

    # Step 5: Instrument the code with sflkit
    start = time.time()
    mapping = Path("mappings", f"{project}_tcp.json")
    mapping.parent.mkdir(parents=True, exist_ok=True)

    # Build list of purified test files for instrumentation
    purified_test_files = set()
    for test_id, purified_files in purified_mapping.items():
        for purified_file in purified_files:
            purified_test_files.add(purified_file.name)

    # Also include the original test file (which now has disabled tests)
    original_test_files = set()
    for test_id in purified_mapping.keys():
        parts = test_id.split("::")
        original_test_files.add(parts[0])

    # Combine purified and original test files
    all_test_files = list(purified_test_files | original_test_files)

    # Temporarily modify project.test_cases for config generation
    # This ensures sflkit knows about all test files
    purified_test_list = []
    for test_id, purified_files in purified_mapping.items():
        file_path, class_name, test_name, param_suffix = parse_test_id(test_id)

        if file_path is None:
            continue

        for purified_file in purified_files:
            if class_name:
                # Class method: file::class::method
                purified_test_id = f"{purified_file.name}::{class_name}::{test_name}"
            else:
                # Module-level function: file::function
                purified_test_id = f"{purified_file.name}::{test_name}"
            purified_test_list.append(purified_test_id)

    project.test_cases = purified_test_list

    r = sflkit_instrument(
        sfl_path,
        project,
        mapping=mapping,
        test=True,
    )
    report[identifier]["time"]["instrument"] = time.time() - start

    if r.successful:
        report[identifier]["instrument"] = "successful"
    else:
        report[identifier]["instrument"] = "failed"
        report[identifier]["error"] = traceback.format_exception(r.raised)
        return events_base

    # Save the mapping
    if mapping.exists():
        with open(mapping, "r") as f:
            mapping_content = json.load(f)
        with open(mapping, "w") as f:
            json.dump(mapping_content, f, indent=1)

    # Step 6: Collect events by running tests
    shutil.rmtree(events_base, ignore_errors=True)

    # Handle ansible special case
    if project.project_name == "ansible":
        shutil.rmtree(original_checkout, ignore_errors=True)

    start = time.time()

    # Create a modified project with purified test cases
    # We need to update the test_cases to point to the purified test files
    # Each purified test keeps the same test function name but is in a new file

    # Build list of purified test identifiers
    # Format can be:
    #   - filename::test_function (2 parts - module-level)
    #   - filename::ClassName::test_method (3 parts - class method)
    #   - Can include parameter suffix in original ID but not in purified ID
    purified_test_list = []
    for test_id, purified_files in purified_mapping.items():
        file_path, class_name, test_name, param_suffix = parse_test_id(test_id)

        if file_path is None:
            continue

        for purified_file in purified_files:
            if class_name:
                # Class method
                purified_test_id = f"{purified_file.name}::{class_name}::{test_name}"
            else:
                # Module-level function
                purified_test_id = f"{purified_file.name}::{test_name}"
            purified_test_list.append(purified_test_id)

    # Temporarily replace project test_cases with purified tests
    original_test_cases = project.test_cases
    project.test_cases = purified_test_list

    # Run sflkit_unittest with purified tests
    r = sfl.sflkit_unittest(
        sfl_path,
        output=events_base,
        relevant_tests=True,
        all_tests=False,
        include_suffix=True,
    )

    # Restore original test cases
    project.test_cases = original_test_cases

    report[identifier]["time"]["test"] = time.time() - start

    if r.successful:
        report[identifier]["test"] = "successful"
    else:
        report[identifier]["test"] = "failed"
        report[identifier]["error"] = traceback.format_exception(r.raised)
        return events_base

    # Step 7: Verify events were collected
    checks = True

    # Check that we have events for purified tests
    if not (events_base / "failing").exists() or not os.listdir(
        events_base / "failing"
    ):
        report[identifier]["check_failing"] = "empty"
        checks = False
    else:
        # Verify that purified tests generated events
        from sflkit.runners import Runner

        missing_tests = []
        for test_id, purified_files in purified_mapping.items():
            file_path, class_name, test_name, param_suffix = parse_test_id(test_id)

            if file_path is None:
                continue

            for purified_file in purified_files:
                if class_name:
                    # Class method
                    purified_test_id = (
                        f"{purified_file.name}::{class_name}::{test_name}"
                    )
                else:
                    # Module-level function
                    purified_test_id = f"{purified_file.name}::{test_name}"

                safe_test = Runner.safe(purified_test_id)
                if not (events_base / "failing" / safe_test).exists():
                    missing_tests.append(purified_test_id)

        if missing_tests:
            report[identifier]["missing_purified_tests"] = missing_tests
            LOGGER.warning(f"Missing events for {len(missing_tests)} purified tests")

    if not (events_base / "passing").exists() or not os.listdir(
        events_base / "passing"
    ):
        report[identifier]["check_passing"] = "empty"
        checks = False

    if checks:
        report[identifier]["check"] = "successful"
    else:
        report[identifier]["check"] = "failed"

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
