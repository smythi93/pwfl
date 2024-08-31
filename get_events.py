import argparse
import json
import os
import shutil
import subprocess
import time
import traceback
from pathlib import Path
from typing import Optional, Union

from sflkit import Config
from sflkit.runners import Runner

import tests4py.api as t4p
from tests4py import sfl, environment
from tests4py.api.utils import get_work_dir, load_project
from tests4py.constants import Environment, PYTHON
from tests4py.projects import TestStatus, Project
from tests4py.sfl import SFLInstrumentReport, instrument, get_events_path
from tests4py.sfl.constants import DEFAULT_EXCLUDES

SFLKIT_LIB_ABS_PATH = (Path(__file__).parent / "sflkit-lib-extension").absolute()


def sflkit_env(environ: Environment):
    subprocess.check_call(
        [PYTHON, "-m", "pip", "install", SFLKIT_LIB_ABS_PATH],
        env=environ,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
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
):
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
    test_files = [
        str(file)
        for file in project.test_files
        if file.is_relative_to(project.test_base) and file.suffix == ".py"
    ]
    return Config.create(
        path=str(src.absolute()),
        language="python",
        events="line",
        test_events="test_start,test_end,test_line,test_def,test_use,test_assert",
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
):
    report = report or SFLInstrumentReport()
    work_dir = get_work_dir(work_dir_or_project)
    try:
        if dst is None:
            raise ValueError("Destination required for instrument")
        project = load_project(work_dir, only_project=True)
        report.project = project
        instrument(
            create_config(
                project,
                work_dir,
                Path(dst),
                mapping=Path(mapping) if mapping else None,
                only_patched_files=only_patched_files,
            ),
        )
        report.successful = True
    except BaseException as e:
        report.raised = e
        report.successful = False
    return report


def main(project_name, bug_id):
    report_file = f"report_{project_name}.json"
    if os.path.exists(report_file):
        with open(report_file, "r") as f:
            report = json.load(f)
    else:
        report = dict()
    os.makedirs("mappings", exist_ok=True)
    for project in t4p.get_projects(project_name, bug_id):
        identifier = project.get_identifier()
        print(identifier)
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

        start = time.time()
        r = t4p.checkout(project)
        report[identifier]["time"]["checkout"] = time.time() - start
        if r.successful:
            report[identifier]["checkout"] = "successful"
        else:
            report[identifier]["checkout"] = "failed"
            report[identifier]["error"] = traceback.format_exception(r.raised)
            continue
        original_checkout = r.location

        mapping = os.path.join("mappings", f"{project}.json")
        sfl_path = os.path.join("tmp", f"sfl_{identifier}")
        start = time.time()
        r = sflkit_instrument(sfl_path, project, mapping=mapping)
        report[identifier]["time"]["instrument"] = time.time() - start
        if r.successful:
            report[identifier]["build"] = "successful"
        else:
            report[identifier]["build"] = "failed"
            report[identifier]["error"] = traceback.format_exception(r.raised)
            continue

        with open(mapping, "r") as f:
            mapping_content = json.load(f)
        with open(mapping, "w") as f:
            json.dump(mapping_content, f, indent=2)

        events_base = os.path.join(
            "sflkit_events", project.project_name, str(project.bug_id)
        )
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
        r = sfl.sflkit_unittest(
            sfl_path, relevant_tests=True, all_tests=False, include_suffix=True
        )
        report[identifier]["time"]["test"] = time.time() - start
        if r.successful:
            report[identifier]["test"] = "successful"
        else:
            report[identifier]["test"] = "failed"
            report[identifier]["error"] = traceback.format_exception(r.raised)
            continue

        checks = True
        bug_events = os.path.join(events_base, "bug")
        for failing_test in project.test_cases:
            safe_test = Runner.safe(failing_test)
            if not os.path.exists(os.path.join(bug_events, "failing", safe_test)):
                report[identifier][f"bug:{failing_test}"] = "not_found"
                checks = False
        if not os.listdir(os.path.join(bug_events, "passing")):
            report[identifier]["bug_passing"] = "empty"
            checks = False

        if checks:
            report[identifier]["check"] = "successful"
        else:
            report[identifier]["check"] = "failed"

    with open(f"report_{project_name}.json", "w") as f:
        json.dump(report, f, indent=2)


if __name__ == "__main__":
    args = argparse.ArgumentParser()
    args.add_argument("-p", required=True, dest="project_name", help="project name")
    args.add_argument("-i", default=None, dest="bug_id", help="bug_id")

    arguments = args.parse_args()
    name = arguments.project_name
    id_ = arguments.bug_id
    if id_ is not None:
        id_ = int(id_)

    main(name, id_)
