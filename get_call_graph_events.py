import argparse
import json
import os
import shutil
import traceback
from pathlib import Path
from typing import Optional, Union

import tests4py.api as t4p
from sflkit import Config
from tests4py import sfl, environment
from tests4py.api.utils import get_work_dir, load_project
from tests4py.projects import TestStatus, Project
from tests4py.sfl import get_events_path, SFLInstrumentReport, instrument
from tests4py.sfl.constants import DEFAULT_EXCLUDES

from get_events import sflkit_env

SFLKIT_LIB_ABS_PATH = (Path(__file__).parent / "sflkit-lib-extension").absolute()


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
    test_files = list({str(file.split("::")[0]) for file in project.test_cases})
    return Config.create(
        path=str(src.absolute()),
        language="python",
        events="function_enter,function_exit,function_error",
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


def get_events(
    project: Project,
    identifier: str,
    report: dict,
):
    events_base = Path("sflkit_events", project.project_name, "cg", str(project.bug_id))

    original_checkout = Path("tmp", f"{identifier}")
    if not original_checkout.exists():
        r = t4p.checkout(project)
        if r.successful:
            report[identifier]["checkout"] = "successful"
        else:
            report[identifier]["checkout"] = "failed"
            report[identifier]["error"] = traceback.format_exception(r.raised)
            return events_base
        original_checkout = r.location

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
            report[identifier]["error"] = traceback.format_exception(r.raised)
            return events_base

    mapping = os.path.join("mappings", f"{project}_cg.json")
    sfl_path = os.path.join("tmp", f"sfl_{identifier}_cg")
    r = sflkit_instrument(sfl_path, project, mapping=mapping)
    if r.successful:
        report[identifier][f"build"] = "successful"
    else:
        report[identifier][f"build"] = "failed"
        report[identifier]["error"] = traceback.format_exception(r.raised)
        return events_base

    with open(mapping, "r") as f:
        mapping_content = json.load(f)
    with open(mapping, "w") as f:
        json.dump(mapping_content, f, indent=1)

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
    r = sfl.sflkit_unittest(
        sfl_path,
        output=events_base,
        relevant_tests=True,
        all_tests=False,
        include_suffix=True,
    )

    if r.successful:
        report[identifier][f"test"] = "successful"
    else:
        report[identifier][f"test"] = "failed"
        report[identifier]["error"] = traceback.format_exception(r.raised)
    return events_base


def main(project_name, bug_id):
    report_dir = "reports"
    os.makedirs(report_dir, exist_ok=True)
    report_file = os.path.join(report_dir, f"cg_{project_name}.json")
    cg_dir = "call_graphs"
    os.makedirs(cg_dir, exist_ok=True)
    if os.path.exists(report_file):
        with open(report_file, "r") as f:
            report = json.load(f)
    else:
        report = dict()
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
            continue
        get_events(project, identifier, report)
        if "error" in report[identifier]:
            report[identifier]["check"] = "fail"
            continue

        report[identifier]["check"] = "successful"
    with open(report_file, "w") as f:
        json.dump(report, f, indent=1)


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
