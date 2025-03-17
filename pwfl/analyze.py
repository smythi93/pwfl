import json
import os
import time
from pathlib import Path
from typing import List, Tuple, Optional

import tests4py.api as t4p
from sflkit import Analyzer
from sflkit.analysis.factory import (
    LineFactory,
)
from sflkit.events.event_file import EventFile
from sflkit.events.mapping import EventMapping
from sflkit.model.model import Model
from sflkit.weights import (
    TestLineModel,
    TestDefUseModel,
    TestDefUsesModel,
    TestAssertDefUseModel,
    TestAssertDefUsesModel,
    ProximityAnalyzer,
)
from tests4py.projects import TestStatus, Project

from pwfl.logger import LOGGER

distances = [
    ("", None),
    ("_line", TestLineModel),
    ("_defuse", TestDefUseModel),
    ("_defuses", TestDefUsesModel),
    ("_assert_use", TestAssertDefUseModel),
    ("_assert_uses", TestAssertDefUsesModel),
]


def get_event_files(
    events: os.PathLike, mapping: os.PathLike | EventMapping
) -> Tuple[List[EventFile], List[EventFile], List[EventFile]]:
    events = Path(events)
    if isinstance(mapping, EventMapping):
        mapping = mapping
    else:
        mapping = EventMapping.load_from_file(Path(mapping), "")
    if (events / "failing").exists():
        failing = [
            EventFile(
                events / "failing" / path,
                run_id,
                mapping,
                failing=True,
            )
            for run_id, path in enumerate(os.listdir(events / "failing"), start=0)
        ]
    else:
        failing = []
    if (events / "passing").exists():
        passing = [
            EventFile(events / "passing" / path, run_id, mapping, failing=False)
            for run_id, path in enumerate(
                os.listdir(events / "passing"),
                start=len(failing),
            )
        ]
    else:
        passing = []
    if (events / "undefined").exists():
        undefined = [
            EventFile(events / "undefined" / path, run_id, mapping, failing=False)
            for run_id, path in enumerate(
                os.listdir(events / "undefined"),
                start=len(failing) + len(passing),
            )
        ]
    else:
        undefined = []
    return failing, passing, undefined


def analyze_project(
    project: Project,
    analysis_file: os.PathLike,
    report: dict,
    suffix: str,
    model_class: Optional[type[Model]] = None,
) -> Analyzer:
    os.makedirs("analysis", exist_ok=True)
    events = Path(
        "sflkit_events",
        project.project_name,
        str(project.bug_id),
    )
    mapping_file = Path("mappings", f"{project}.json")
    if not events.exists():
        raise FileNotFoundError(f"Events not found for {project}")
    if not mapping_file.exists():
        raise FileNotFoundError(f"Mapping not found for {project}")
    failing, passing, undefined = get_event_files(events, mapping_file)
    start = time.time()
    if model_class is None:
        analyzer = Analyzer(
            relevant_event_files=failing,
            irrelevant_event_files=passing,
            factory=LineFactory(),
        )
    else:
        analyzer = ProximityAnalyzer(
            model_class,
            relevant_event_files=failing,
            irrelevant_event_files=passing,
            factory=LineFactory(),
        )
    analyzer.analyze()
    report[project.get_identifier()][f"lines{suffix}"] = time.time() - start
    analyzer.dump(analysis_file, indent=1)
    return analyzer


def analyze(project_name, bug_id=None, start=None, end=None):
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
        project.buggy = True
        report[project.get_identifier()] = dict()
        for suffix, model_class in distances:
            analysis_file = Path("analysis", f"{project}{suffix}.json")
            if analysis_file.exists():
                continue
            analyze_project(project, analysis_file, report, suffix, model_class)

    with open(report_dir / f"analysis_{project_name}.json", "w") as f:
        json.dump(report, f, indent=1)
