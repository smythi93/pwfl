"""
Call-graph event collection and construction utilities.

This module instruments subjects for function-level events, builds per-project
call graphs, and stores graph artifacts for subsequent PRFL weighting.
"""

import json
import os
import shutil
import time
import traceback
from pathlib import Path
from typing import Optional, Union
from typing import Tuple, Set

import tests4py.api as t4p
from sflkit import Config
from sflkit.analysis.analysis_type import AnalysisObject
from sflkit.analysis.factory import CombinationFactory
from sflkit.events.event_file import EventFile
from sflkit.model.model import Model
from sflkit.model.scope import Scope
from sflkitlib.events.event import (
    FunctionEnterEvent,
    FunctionErrorEvent,
    FunctionExitEvent,
    LineEvent,
    Event,
)
from tests4py import sfl, environment
from tests4py.api.utils import get_work_dir, load_project
from tests4py.projects import TestStatus, Project
from tests4py.sfl import get_events_path, SFLInstrumentReport, instrument
from tests4py.sfl.constants import DEFAULT_EXCLUDES

from pwfl.analyze import get_event_files
from pwfl.events import sflkit_env
from pwfl.logger import LOGGER
from pwfl.utils import fix_sanic, fix_sanic_after

Function = Tuple[str, int, str, int]
Line = Tuple[str, int]


class CallGraphBuilder(Model):
    """
    Model that reconstructs call edges and covered lines from event traces.
    """

    def __init__(self, factory):
        """
        Initialize graph, call-stack, and line-coverage state.

        :param factory: SFLKit analysis factory.
        :returns: None
        """
        super().__init__(factory)
        # The graph dict contains:
        #   1. The function tuple (file, line, function name, function id)
        #   2. A dict with the number of passing and failing tests that execute the function and the ids of those tests
        #   3. A dict with the called functions, where the key is the function id and the value is a dict with the
        #      number of passing and failing tests that execute the call and the ids of those tests
        self.graph: dict[
            int,
            tuple[
                Function,
                dict[str, dict[str, int | list[int]]],
                dict[int, dict[str, dict[str, int | list[int]]]],
            ],
        ] = {}
        self.call_stack: dict[int | None, list[Function]] = {}
        self.lines: dict[int, tuple[Function, list[Line]]] = {}

    def prepare(self, event_file):
        """
        Reset per-event-file state before processing a new trace.

        :param event_file: Input event file.
        :returns: None
        """
        super().prepare(event_file)
        self.call_stack = {}

    def handle_event(
        self,
        event: Event,
        event_file: EventFile,
        scope: Scope = None,
    ) -> Set[AnalysisObject]:
        """
        Handle generic events (unused for this model).

        :returns: Empty set because only specialized handlers mutate state.
        :rtype: set
        """
        return set()

    def handle_line_event(self, event: LineEvent, event_file: EventFile):
        """
        Attach visited source lines to the currently active function.

        :param event: Line event.
        :param event_file: Origin trace metadata.
        :returns: None
        """
        if self.call_stack:
            function_id = self.call_stack[event.thread_id][-1][3]
            if function_id not in self.lines:
                self.lines[function_id] = (self.call_stack[event.thread_id][-1], list())
            line = (event.file, event.line)
            if line not in self.lines[function_id][1]:
                self.lines[function_id][1].append(line)

    def handle_function_enter_event(
        self, event: FunctionEnterEvent, event_file: EventFile
    ):
        """
        Record function execution and caller-to-callee transitions.

        :param event: Function enter event.
        :param event_file: Origin trace metadata.
        :returns: None
        """
        function = (event.file, event.line, event.function, event.function_id)
        function_id = event.function_id
        if event.thread_id not in self.call_stack:
            self.call_stack[event.thread_id] = []
        if self.call_stack[event.thread_id]:
            caller = self.call_stack[event.thread_id][-1]
            caller_id = caller[3]
            if caller_id not in self.graph:
                self.graph[caller_id] = (
                    caller,
                    {
                        "PASS": {"count": 0, "ids": list()},
                        "FAIL": {"count": 0, "ids": list()},
                    },
                    dict(),
                )
            if function_id not in self.graph[caller_id][1]:
                self.graph[caller_id][2][function_id] = {
                    "PASS": {"count": 0, "ids": list()},
                    "FAIL": {"count": 0, "ids": list()},
                }
            if event_file.failing:
                # Track both hit counts and distinct run ids per edge and outcome.
                self.graph[caller_id][2][function_id]["FAIL"]["count"] += 1
                if (
                    event_file.run_id
                    not in self.graph[caller_id][2][function_id]["FAIL"]["ids"]
                ):
                    # noinspection PyUnresolvedReferences
                    self.graph[caller_id][2][function_id]["FAIL"]["ids"].append(
                        event_file.run_id
                    )
            else:
                self.graph[caller_id][2][function_id]["PASS"]["count"] += 1
                if (
                    event_file.run_id
                    not in self.graph[caller_id][2][function_id]["PASS"]["ids"]
                ):
                    # noinspection PyUnresolvedReferences
                    self.graph[caller_id][2][function_id]["PASS"]["ids"].append(
                        event_file.run_id
                    )
        self.call_stack[event.thread_id].append(function)
        if function_id not in self.graph:
            self.graph[function_id] = (
                function,
                {
                    "PASS": {"count": 0, "ids": list()},
                    "FAIL": {"count": 0, "ids": list()},
                },
                dict(),
            )
        if event_file.failing:
            self.graph[function_id][1]["FAIL"]["count"] += 1
            if event_file.run_id not in self.graph[function_id][1]["FAIL"]["ids"]:
                # noinspection PyUnresolvedReferences
                self.graph[function_id][1]["FAIL"]["ids"].append(event_file.run_id)
        else:
            self.graph[function_id][1]["PASS"]["count"] += 1
            if event_file.run_id not in self.graph[function_id][1]["PASS"]["ids"]:
                # noinspection PyUnresolvedReferences
                self.graph[function_id][1]["PASS"]["ids"].append(event_file.run_id)

    def handle_function_exit_event(
        self, event: FunctionExitEvent, event_file: EventFile
    ):
        """
        Pop the current function frame when execution returns.

        :returns: None
        """
        if event.thread_id in self.call_stack:
            if self.call_stack[event.thread_id]:
                self.call_stack[event.thread_id].pop()

    def handle_function_error_event(
        self, event: FunctionErrorEvent, event_file: EventFile
    ):
        """
        Pop the current function frame when execution aborts via error.

        :returns: None
        """
        if event.thread_id in self.call_stack:
            if self.call_stack[event.thread_id]:
                self.call_stack[event.thread_id].pop()


def build_call_graph_project(project):
    """
    Build call graph and function-to-line mapping for one project.

    :param project: Subject metadata.
    :returns: Pair ``(graph, lines)``.
    :rtype: tuple[dict, dict]
    """
    events = Path(
        "sflkit_events",
        project.project_name,
        "cg",
        str(project.bug_id),
    )
    mapping_file = Path("mappings", f"{project}_cg.json")
    failing, passing, _ = get_event_files(events, mapping_file)
    model = CallGraphBuilder(CombinationFactory([]))
    for event_file in failing + passing:
        model.prepare(event_file)
        with event_file:
            for event in event_file.load():
                event.handle(model, event_file)
    return model.graph, model.lines


def build_call_graph(project_name, bug_id=None, start=None, end=None):
    """
    Generate call-graph artifacts for selected projects.

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
    report_file = os.path.join(report_dir, f"cg_{project_name}_build.json")
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
        cg_file = os.path.join(cg_dir, f"{identifier}.json")
        cg_lines_file = os.path.join(cg_dir, f"{identifier}_lines.json")
        LOGGER.info(identifier)
        if (
            project.test_status_buggy != TestStatus.FAILING
            or project.test_status_fixed != TestStatus.PASSING
            or (
                "check" in report[identifier]
                and report[identifier]["check"] == "successful"
                and os.path.exists(cg_file)
                and os.path.exists(cg_lines_file)
            )
        ):
            continue
        try:
            start = time.time()
            call_graph, lines = build_call_graph_project(project)
            report[identifier]["time"] = time.time() - start
        except Exception as e:
            report[identifier]["check"] = "fail"
            report[identifier]["error"] = traceback.format_exception(e)
            continue
        else:
            report[identifier]["check"] = "successful"
            if "error" in report[identifier]:
                del report[identifier]["error"]
        with open(cg_file, "w") as f:
            json.dump(call_graph, f, indent=1)
        with open(cg_lines_file, "w") as f:
            json.dump(lines, f, indent=1)

    with open(report_file, "w") as f:
        json.dump(report, f, indent=1)


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
    """
    Create instrumentation config for call-graph event collection.

    :returns: Config object configured for function and line events.
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
        events="line,function_enter,function_exit,function_error",
        ignore_inner=str(
            project.project_name == "pysnooper"
        ),  # pysnooper defines a testcase function inside a
        # testcase, which it traces. With the instrumentation, the trace is not correct because the correct trace is
        # asserted. Hence, inner functions are ignored.
        metrics=metrics or "",
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
    """
    Instrument a project checkout for call-graph event extraction.

    :returns: Instrumentation report object.
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
    """
    Collect call-graph event traces for one project.

    :param project: Subject metadata.
    :param identifier: Stable project identifier.
    :param report: Mutable report dictionary.
    :returns: Base directory containing collected events.
    :rtype: pathlib.Path
    """
    events_base = Path("sflkit_events", project.project_name, "cg", str(project.bug_id))

    original_checkout = Path("tmp", f"{identifier}")
    if not original_checkout.exists():
        r = t4p.checkout(project)
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

    mapping = Path("mappings", f"{project}_cg.json")
    sfl_path = Path("tmp", f"sfl_{identifier}_cg")
    r = sflkit_instrument(sfl_path, project, mapping=mapping)
    if project.project_name == "sanic":
        fix_sanic_after(
            project=project,
            original_checkout=original_checkout,
        )
    if r.successful:
        report[identifier][f"build"] = "successful"
    else:
        report[identifier][f"build"] = "failed"
        # noinspection PyTypeChecker
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


def get_call_graph_events(project_name, bug_id, start=None, end=None):
    """
    Collect call-graph events for all selected projects.

    :returns: None
    """
    report_dir = "reports"
    os.makedirs(report_dir, exist_ok=True)
    report_file = os.path.join(report_dir, f"cg_{project_name}.json")
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
            continue
        get_events(project, identifier, report)
        if "error" in report[identifier]:
            report[identifier]["check"] = "fail"
            continue

        report[identifier]["check"] = "successful"
    with open(report_file, "w") as f:
        json.dump(report, f, indent=1)
