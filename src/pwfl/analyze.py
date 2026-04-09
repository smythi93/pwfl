"""
Analyzer construction for baseline and proximity-based PWFL variants.
"""

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
from sflkit.weights import (
    TestLineModel,
    TestDefUseModel,
    TestDefUsesModel,
    TestAssertDefUseModel,
    TestAssertDefUsesModel,
    ProximityAnalyzer,
)
from sflkit.weights.models import TestTimeModel
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
    events: Path, mapping: os.PathLike | EventMapping
) -> Tuple[List[EventFile], List[EventFile], List[EventFile]]:
    """
    Load failing, passing, and undefined event files with a shared mapping.

    :param events: Base directory containing ``failing/``, ``passing/``, and
        optional ``undefined/`` event subdirectories.
    :type events: pathlib.Path
    :param mapping: Event mapping object or path to mapping JSON.
    :type mapping: os.PathLike | EventMapping
    :returns: Three lists in the order ``(failing, passing, undefined)``.
    :rtype: tuple[list[EventFile], list[EventFile], list[EventFile]]
    """
    events = Path(events)
    if isinstance(mapping, EventMapping):
        resolved_mapping = mapping
    else:
        resolved_mapping = EventMapping.load_from_file(Path(mapping), None)
    if (events / "failing").exists():
        failing = [
            EventFile(
                events / "failing" / path,
                run_id,
                resolved_mapping,
                failing=True,
            )
            for run_id, path in enumerate(os.listdir(events / "failing"), start=0)
        ]
    else:
        failing = []
    if (events / "passing").exists():
        passing = [
            EventFile(
                events / "passing" / path, run_id, resolved_mapping, failing=False
            )
            for run_id, path in enumerate(
                os.listdir(events / "passing"),
                start=len(failing),
            )
        ]
    else:
        passing = []
    if (events / "undefined").exists():
        undefined = [
            EventFile(
                events / "undefined" / path, run_id, resolved_mapping, failing=False
            )
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
    model_class: Optional[type[TestTimeModel]] = None,
) -> Analyzer:
    """
    Build and persist one analyzer variant for a project.

    :param project: Subject under analysis.
    :type project: tests4py.projects.Project
    :param analysis_file: Target JSON file for the serialized analyzer.
    :type analysis_file: os.PathLike
    :param report: Mutable timing report structure for the current run.
    :type report: dict
    :param suffix: Variant suffix used in report keys and filenames.
    :type suffix: str
    :param model_class: Optional proximity model class. If ``None``, a baseline
        :class:`sflkit.Analyzer` is used.
    :type model_class: type[TestTimeModel] | None
    :returns: Constructed analyzer instance.
    :rtype: Analyzer
    :raises FileNotFoundError: If event or mapping files are missing.
    """
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
        # Baseline: rank purely from line spectra.
        analyzer = Analyzer(
            relevant_event_files=failing,
            irrelevant_event_files=passing,
            factory=LineFactory(),
        )
    else:
        # PWFL variants: fold a temporal/test-distance model into suspiciousness.
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
    """
    Run analyzer construction for all selected projects and variants.

    :param project_name: Project identifier or ``None`` for all.
    :type project_name: str | None
    :param bug_id: Optional single bug id.
    :type bug_id: int | None
    :param start: Optional lower bound for bug ids.
    :type start: int | None
    :param end: Optional upper bound for bug ids.
    :type end: int | None
    :returns: None
    """
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
