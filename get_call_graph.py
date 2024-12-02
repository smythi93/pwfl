import argparse
import json
import os
import time
import traceback
from pathlib import Path
from typing import Tuple, Dict, List, Set

import tests4py.api as t4p
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
)
from tests4py.projects import TestStatus

from get_analysis import get_event_files

Function = Tuple[str, int, str, int]
Line = Tuple[str, int]


class CallGraphBuilder(Model):
    def __init__(self, factory):
        super().__init__(factory)
        self.graph: Dict[
            int,
            Tuple[
                Function,
                Dict[str, int | List[int]],
                Dict[int, Dict[str, Dict[str, int | List[int]]]],
            ],
        ] = dict()
        self.call_stack: List[Function] = list()
        self.lines: Dict[int, Tuple[Function, List[Line]]] = dict()

    def prepare(self, event_file):
        super().prepare(event_file)
        self.call_stack = list()

    def handle_event(self, event, scope: Scope = None) -> Set[AnalysisObject]:
        return set()

    def handle_line_event(self, event):
        event: LineEvent
        if self.call_stack:
            function_id = self.call_stack[-1][3]
            if function_id not in self.lines:
                self.lines[function_id] = (self.call_stack[-1], list())
            line = (event.file, event.line)
            if line not in self.lines[function_id][1]:
                self.lines[function_id][1].append(line)

    def handle_function_enter_event(self, event):
        event: FunctionEnterEvent
        function = (event.file, event.line, event.function, event.function_id)
        function_id = event.function_id
        if self.call_stack:
            caller = self.call_stack[-1]
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
                self.graph[caller_id][1][function_id] = {
                    "PASS": {"count": 0, "ids": list()},
                    "FAIL": {"count": 0, "ids": list()},
                }
            self.current_event_file: EventFile
            if self.current_event_file.failing:
                self.graph[caller_id][1][function_id]["FAIL"]["count"] += 1
                if (
                    self.current_event_file.run_id
                    not in self.graph[caller_id][1][function_id]["FAIL"]["ids"]
                ):
                    self.graph[caller_id][1][function_id]["FAIL"]["ids"].append(
                        self.current_event_file.run_id
                    )
            else:
                self.graph[caller_id][1][function_id]["PASS"]["count"] += 1
                if (
                    self.current_event_file.run_id
                    not in self.graph[caller_id][1][function_id]["PASS"]["ids"]
                ):
                    self.graph[caller_id][1][function_id]["PASS"]["ids"].append(
                        self.current_event_file.run_id
                    )
        self.call_stack.append(function)
        if function_id not in self.graph:
            self.graph[function_id] = (
                function,
                {
                    "PASS": {"count": 0, "ids": list()},
                    "FAIL": {"count": 0, "ids": list()},
                },
                dict(),
            )
        if self.current_event_file.failing:
            self.graph[function_id][1]["FAIL"]["count"] += 1
            if (
                self.current_event_file.run_id
                not in self.graph[function_id][1]["FAIL"]["ids"]
            ):
                self.graph[function_id][1]["FAIL"]["ids"].append(
                    self.current_event_file.run_id
                )
        else:
            self.graph[function_id][1]["PASS"]["count"] += 1
            if (
                self.current_event_file.run_id
                not in self.graph[function_id][1]["PASS"]["ids"]
            ):
                self.graph[function_id][1]["PASS"]["ids"].append(
                    self.current_event_file.run_id
                )

    def handle_function_exit_event(self, event):
        event: FunctionExitEvent
        if self.call_stack:
            self.call_stack.pop()

    def handle_function_error_event(self, event):
        event: FunctionErrorEvent
        if self.call_stack:
            self.call_stack.pop()


def build_call_graph(project):
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
                event.handle(model)
    return model.graph, model.lines


def main(project_name, bug_id):
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
        identifier = project.get_identifier()
        if identifier not in report:
            report[identifier] = dict()
        cg_file = os.path.join(cg_dir, f"{identifier}.json")
        cg_lines_file = os.path.join(cg_dir, f"{identifier}_lines.json")
        print(identifier)
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
            call_graph, lines = build_call_graph(project)
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
