"""
Baseline event collection pipeline for PWFL.

This module checks out subjects, applies instrumentation, executes relevant
tests, and validates that expected failing/passing event files exist.
"""

import json
import os
import shutil
import subprocess
import time
import traceback
from pathlib import Path
from typing import Optional, Union

import tests4py.api as t4p
from sflkit import Config
from sflkit.runners import Runner
from tests4py import sfl, environment
from tests4py.api.utils import get_work_dir, load_project
from tests4py.constants import Environment, PYTHON
from tests4py.projects import TestStatus, Project
from tests4py.sfl import SFLInstrumentReport, instrument, get_events_path
from tests4py.sfl.constants import DEFAULT_EXCLUDES

from pwfl.logger import LOGGER
from pwfl.utils import fix_sanic, fix_sanic_after


def sflkit_env(environ: Environment):
    """
    Install runtime dependencies required by SFLKit in a subject venv.

    :param environ: Environment variables for the target virtual environment.
    :type environ: Environment
    :returns: None
    :raises RuntimeError: If dependency installation fails.
    """
    result = subprocess.run(
        [PYTHON, "-m", "pip", "install", "sflkitlib>=0.2.2"],
        env=environ,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to install sflkit-lib: {result.stdout.decode()}\n{result.stderr.decode()}"
        )


environment.sflkit_env = sflkit_env
t4p.default.sflkit_env = sflkit_env


def create_config(
    project: Project,
    src: Path,
    dst: Path,
    metrics: str = None,
    events_path: Optional[Path] = None,
    mapping: Optional[Path] = None,
    only_patched_files: bool = False,
    include_suffix: bool = False,
    test: bool = True,
):
    """
    Create an SFLKit instrumentation configuration for one project.

    :param project: Subject to instrument.
    :param src: Source checkout directory.
    :param dst: Working directory for instrumented sources.
    :param metrics: Optional metrics configuration string.
    :param events_path: Optional explicit base output path.
    :param mapping: Optional mapping file destination.
    :param only_patched_files: Restrict instrumentation to patched files.
    :param include_suffix: Use tests4py suffix-based event directories.
    :param test: Whether to include test-level events in addition to line events.
    :returns: Generated SFLKit config object.
    :rtype: sflkit.Config
    """
    if only_patched_files:
        includes = t4p.get_patched_files(project)
        excludes = list()
    elif project.included_files:
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
        test_events=(
            "test_start,test_end,test_line,test_def,test_use,test_assert"
            if test
            else None
        ),
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
    dst: os.PathLike,
    work_dir_or_project: Optional[Union[os.PathLike, Project]] = None,
    mapping: os.PathLike = None,
    only_patched_files: bool = False,
    report: SFLInstrumentReport = None,
    test: bool = True,
):
    """
    Instrument a project checkout for event collection.

    :param dst: Instrumented working directory.
    :param work_dir_or_project: Checkout path or project object.
    :param mapping: Mapping file path.
    :param only_patched_files: Restrict instrumentation to patched files.
    :param report: Optional report object to populate.
    :param test: Include test-level events when ``True``.
    :returns: Instrumentation report with success/error details.
    :rtype: tests4py.sfl.SFLInstrumentReport
    """
    report = report or SFLInstrumentReport()
    work_dir = get_work_dir(work_dir_or_project)
    try:
        if dst is None:
            raise ValueError("Destination required for instrument")
        # noinspection PyTypeChecker
        project: Project = load_project(work_dir, only_project=True)
        report.project = project
        instrument(
            create_config(
                project,
                work_dir,
                Path(dst),
                mapping=Path(mapping) if mapping else None,
                only_patched_files=only_patched_files,
                test=test,
            ),
        )
        report.successful = True
    except BaseException as e:
        report.raised = e
        report.successful = False
    return report


def get_events_project(
    project: Project,
    identifier: str,
    report: dict,
    tests: bool = True,
):
    """
    Collect events for one project variant (line-only or full test events).

    :param project: Subject under analysis.
    :param identifier: Stable ``project_bugid`` identifier.
    :param report: Mutable report dictionary for status/timing updates.
    :param tests: Collect test events when ``True``; otherwise collect line-only
        events used for instrumentation base-lining.
    :returns: Event output base path, even in partial-failure cases.
    :rtype: pathlib.Path
    """
    if tests:
        suffix = ""
    else:
        suffix = "_lines"
    events_base = (
        Path("sflkit_events", project.project_name, str(project.bug_id))
        if tests
        else Path("sflkit_events", project.project_name, "lines", str(project.bug_id))
    )

    start = time.time()
    original_checkout = Path("tmp", f"{identifier}")
    if not original_checkout.exists():
        # Checkout is cached to avoid repeated network and build overhead.
        r = t4p.checkout(project)
        report[identifier]["time"]["checkout"] = time.time() - start
        if r.successful:
            report[identifier]["checkout"] = "successful"
        else:
            report[identifier]["checkout"] = "failed"
            # noinspection PyTypeChecker
            report[identifier]["error"] = traceback.format_exception(r.raised)
            return events_base
        original_checkout = Path(r.location or original_checkout)

    if project.project_name == "sanic":
        fix_sanic(
            project=project,
            original_checkout=original_checkout,
        )

    venv_location = (
        Path.home()
        / ".t4p"
        / "projects"
        / project.project_name
        / f"venv_{project.bug_id}"
    )
    if not venv_location.exists():
        r = t4p.build(original_checkout)
        if not r.successful:
            # noinspection PyTypeChecker
            report[identifier]["error"] = traceback.format_exception(r.raised)
            return events_base
    if project.project_name == "sanic":
        fix_sanic_after(
            project=project,
            original_checkout=original_checkout,
        )

    mapping = Path("mappings", f"{project}{suffix}.json")
    sfl_path = Path("tmp", f"sfl_{identifier}")
    start = time.time()
    r = sflkit_instrument(sfl_path, project, mapping=mapping)
    report[identifier]["time"][f"instrument{suffix}"] = time.time() - start
    if r.successful:
        report[identifier][f"build{suffix}"] = "successful"
    else:
        report[identifier][f"build{suffix}"] = "failed"
        # noinspection PyTypeChecker
        report[identifier]["error"] = traceback.format_exception(r.raised)
        return events_base

    with open(mapping, "r") as f:
        mapping_content = json.load(f)
    with open(mapping, "w") as f:
        json.dump(mapping_content, f, indent=1)

    shutil.rmtree(events_base, ignore_errors=True)
    if project.project_name == "ansible":
        # When ansible is executed it sometimes loads the original version.
        # Even though it is never installed and the virtual environment clearly
        # contains the instrumented version.
        # This prevents an event collection.
        # Removing the original version fixes this problem.
        shutil.rmtree(original_checkout, ignore_errors=True)
    start = time.time()
    r = sfl.sflkit_unittest(
        sfl_path,
        output=events_base,
        relevant_tests=True,
        all_tests=False,
        include_suffix=True,
    )
    report[identifier]["time"][f"test{suffix}"] = time.time() - start

    if r.successful:
        report[identifier][f"test{suffix}"] = "successful"
    else:
        report[identifier][f"test{suffix}"] = "failed"
        report[identifier]["error"] = traceback.format_exception(r.raised)
    return events_base


def get_events(project_name, bug_id=None, start=None, end=None):
    """
    Run baseline event collection for all selected projects.

    :param project_name: Project identifier or ``None`` for all.
    :type project_name: str | None
    :param bug_id: Optional single bug id.
    :type bug_id: int | None
    :param start: Optional lower bound bug id.
    :type start: int | None
    :param end: Optional upper bound bug id.
    :type end: int | None
    :returns: None
    """
    report_dir = "reports"
    os.makedirs(report_dir, exist_ok=True)
    report_file = os.path.join(report_dir, f"report_{project_name}.json")
    if os.path.exists(report_file):
        with open(report_file, "r") as f:
            report = json.load(f)
    else:
        report = dict()
    os.makedirs("mappings", exist_ok=True)
    for project in t4p.get_projects(project_name, bug_id):
        if start is not None and project.bug_id < start:
            continue
        if end is not None and project.bug_id > end:
            continue
        identifier = project.get_identifier()
        LOGGER.info(identifier)
        if (
            identifier in report
            and "check" in report[identifier]
            and report[identifier]["check"] == "successful"
        ):
            continue
        report[identifier] = dict()

        if (
            project.test_status_buggy != TestStatus.FAILING
            or project.test_status_fixed != TestStatus.PASSING
        ):
            report[identifier]["status"] = "skipped"
            continue
        else:
            report[identifier]["status"] = "running"

        report[identifier]["time"] = dict()

        get_events_project(project, identifier, report, tests=False)
        if "error" in report[identifier]:
            continue

        events_base = get_events_project(project, identifier, report)
        if "error" in report[identifier]:
            continue

        shutil.rmtree(
            os.path.join("sflkit_events", project.project_name, "lines"),
            ignore_errors=True,
        )

        checks = True
        # Validate that each known failing test produced an event file.
        for failing_test in project.test_cases:
            safe_test = Runner.safe(failing_test)
            if not (events_base / "failing" / safe_test).exists():
                report[identifier][f"bug:{safe_test}"] = "not_found"
                checks = False
        if not os.listdir(events_base / "passing"):
            report[identifier]["bug_passing"] = "empty"
            checks = False

        if checks:
            report[identifier]["check"] = "successful"
        else:
            report[identifier]["check"] = "failed"

    with open(report_file, "w") as f:
        json.dump(report, f, indent=1)
