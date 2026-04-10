"""CLI for local-project fault localization using SFLKit instrumentation."""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

try:
    import argcomplete
except ImportError:  # pragma: no cover - optional runtime dependency
    argcomplete = None

from sflkit import Analyzer, Config, instrument
from sflkit.analysis.analysis_type import AnalysisType
from sflkit.analysis.factory import LineFactory
from sflkit.analysis.spectra import Spectrum
from sflkit.analysis.suggestion import Suggestion
from sflkit.events.event_file import EventFile
from sflkit.events.mapping import EventMapping
from sflkit.language.language import Language
from sflkit.runners import ParallelPytestRunner
from sflkit.weights import (
    ProximityAnalyzer,
    TestAssertDefUseModel,
    TestAssertDefUsesModel,
    TestDefUseModel,
    TestDefUsesModel,
    TestLineModel,
)
from sflkit.weights.models import TestTimeModel

from pwfl.logger import LOGGER

DEFAULT_EXCLUDES = [
    "setup.py",
    "env",
    "build",
    "bin",
    "docs",
    "examples",
    "hacking",
    ".git",
    ".github",
    "extras",
    "profiling",
    "plugin",
    "gallery",
    "blib2to3",
    "docker",
    "contrib",
    "changelogs",
    "licenses",
    "packaging",
    "setupext.py",
]


def get_event_files(
    events: Path, mapping: os.PathLike | EventMapping
) -> tuple[list[EventFile], list[EventFile], list[EventFile]]:
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


def run(
    command: list[str], cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    """Execute a subprocess command and capture text output."""
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        check=False,
    )


MODELS: dict[str, type[TestTimeModel] | None] = {
    "line": TestLineModel,
    "def-use": TestDefUseModel,
    "def-uses": TestDefUsesModel,
    "assert-def-use": TestAssertDefUseModel,
    "assert-def-uses": TestAssertDefUsesModel,
    "none": None,
}


def _quote_csv(values: list[str]) -> str:
    """Render list values in the CSV-like quoted format expected by Config."""
    if not values:
        return '""'
    return '"' + '","'.join(values) + '"'


def _collect_with_sflkit(
    project_dir: Path,
    mode: str,
    tests: list[str] | None,
    pytest_filter: str | None,
    timeout: int,
    workers: int,
    work_dir: Path,
) -> tuple[Path, Path, Path, list[str], list[str], list[str], set[str]]:
    """Instrument project, run pytest with SFLKit, and return event artifacts."""
    LOGGER.debug(
        "Collecting events with mode=%s, timeout=%s, workers=%s, tests=%s, pytest_k=%s",
        mode,
        timeout,
        workers,
        tests,
        pytest_filter,
    )
    instrumented = work_dir / "instrumented"
    events_dir = work_dir / "events"
    mapping = work_dir / "mapping.json"

    shutil.rmtree(instrumented, ignore_errors=True)
    shutil.rmtree(events_dir, ignore_errors=True)
    instrumented.mkdir(parents=True, exist_ok=True)
    events_dir.mkdir(parents=True, exist_ok=True)

    mode_test_events = {
        "line": "test_line",
        "def-use": "test_line,test_def,test_use",
        "def-uses": "test_line,test_def,test_use",
        "assert-def-use": "test_line,test_assert,test_def,test_use",
        "assert-def-uses": "test_line,test_assert,test_def,test_use",
        "none": None,
    }
    test_events = mode_test_events[mode]

    files: list[Path] | None = None
    base: Path = Path(".")
    selected_tests_paths: list[Path] = []
    if tests:
        files = []
        for test_entry in tests:
            selected_tests_path = Path(test_entry)
            absolute_tests_path = project_dir / selected_tests_path
            if not absolute_tests_path.exists():
                raise FileNotFoundError(
                    "Tests path does not exist inside project directory: "
                    f"{selected_tests_path}"
                )
            selected_tests_paths.append(selected_tests_path)
            files.append(selected_tests_path)

    # Resolve concrete test files so SFLKit can emit test events correctly.
    discovery_runner = ParallelPytestRunner(
        timeout=timeout,
        workers=max(workers, 1),
        thread_support=True,
    )
    discovered_tests = discovery_runner.get_tests(
        directory=project_dir,
        files=files,
        base=base,
        environ=os.environ.copy(),
        python=sys.executable,
        k=pytest_filter,
    )
    test_files = sorted(
        {test.split("::")[0] for test in discovered_tests if "::" in test}
    )
    if not test_files and selected_tests_paths:
        # Fall back to provided test paths if discovery returns no node ids.
        test_files = [str(path) for path in selected_tests_paths]
    LOGGER.debug("Resolved %d test files for test events", len(test_files))

    # Test files should emit test events, not regular line spectra events.
    effective_excludes = [*DEFAULT_EXCLUDES, *test_files]

    config = Config.create(
        path=str(project_dir),
        language="python",
        events="line",
        test_events=test_events,
        ignore_inner="False",
        metrics="",
        predicates="line",
        passing=str(events_dir / "passing"),
        failing=str(events_dir / "failing"),
        working=str(instrumented),
        include=_quote_csv([]),
        exclude=_quote_csv(effective_excludes),
        test_files=_quote_csv(test_files),
        mapping_path=str(mapping),
    )
    config_path = work_dir / "config.ini"
    config.write(config_path)
    LOGGER.debug("Wrote SFLKit config to %s", config_path)
    instrument(config_path)
    LOGGER.debug("Instrumentation finished: %s", instrumented)

    runner = ParallelPytestRunner(
        timeout=timeout,
        workers=workers,
        thread_support=True,
    )

    runner.run(
        directory=instrumented,
        output=events_dir,
        files=files,
        base=base,
        environ=os.environ.copy(),
        python=sys.executable,
        k=pytest_filter,
    )
    LOGGER.debug("Pytest runner finished; outputs in %s", events_dir)

    def _list_event_files(directory: Path) -> list[str]:
        if not directory.exists():
            return []
        return sorted(path.name for path in directory.iterdir() if path.is_file())

    normalized_test_files = {
        path.replace("\\", "/").lstrip("./") for path in test_files
    }

    return (
        instrumented,
        events_dir,
        mapping,
        _list_event_files(events_dir / "failing"),
        _list_event_files(events_dir / "passing"),
        _list_event_files(events_dir / "undefined"),
        normalized_test_files,
    )


def _extract_suggestion_locations(suggestion: Suggestion) -> list[dict[str, Any]]:
    """Extract file/line pairs from an SFLKit suggestion object."""
    extracted: list[dict[str, Any]] = []

    if hasattr(suggestion, "lines"):
        for line in getattr(suggestion, "lines"):
            file_name = getattr(line, "file", None)
            line_no = getattr(line, "line", None)
            if file_name and isinstance(line_no, int):
                extracted.append({"file": str(file_name), "line": line_no})

    if extracted:
        return extracted

    for attr in ("line", "location"):
        location = getattr(suggestion, attr, None)
        if location is None:
            continue
        file_name = getattr(location, "file", None)
        line_no = getattr(location, "line", None)
        if file_name and isinstance(line_no, int):
            extracted.append({"file": str(file_name), "line": line_no})
            return extracted

    return extracted


def _extract_score(suggestion: Any) -> float | None:
    """Extract suspiciousness score from a suggestion when available."""
    for name in ("suspiciousness", "score", "value"):
        value = getattr(suggestion, name, None)
        if isinstance(value, (float, int)):
            return float(value)
    return None


def _build_analyzer(
    events_dir: Path,
    mapping_file: Path,
    mode: str,
) -> Analyzer:
    """Create and execute the requested analyzer for collected events."""
    failing, passing, _undefined = get_event_files(events_dir, mapping_file)
    LOGGER.debug(
        "Building analyzer for mode=%s with %d failing and %d passing event files",
        mode,
        len(failing),
        len(passing),
    )
    model_class = MODELS[mode]
    if model_class is None:
        analyzer: Analyzer = Analyzer(
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
    LOGGER.debug("Analyzer completed")
    return analyzer


def _rank_from_analyzer(
    analyzer: Analyzer,
    base_dir: Path,
    mode: str,
    metric_name: str,
    top: int,
    test_files: set[str],
) -> list[dict[str, Any]]:
    """Generate ranked line entries from SFLKit suggestions."""
    metric_by_name = {
        "tarantula": Spectrum.Tarantula,
        "ochiai": Spectrum.Ochiai,
        "dstar": Spectrum.DStar,
        "naish2": Spectrum.Naish2,
        "gp13": Spectrum.GP13,
    }
    metric = metric_by_name[metric_name]
    use_weight = mode != "none"

    LOGGER.debug(
        "Generating sorted suggestions with metric=%s, mode=%s, use_weight=%s",
        metric_name,
        mode,
        use_weight,
    )
    suggestions = analyzer.get_sorted_suggestions(
        base_dir,
        metric,
        AnalysisType.LINE,
        use_weight=use_weight,
    )
    ranking: list[dict[str, Any]] = []

    for suggestion in suggestions:
        locations = _extract_suggestion_locations(suggestion)
        if not locations:
            continue
        score = _extract_score(suggestion)
        for location in locations:
            if not location["file"]:
                continue
            normalized_file = str(location["file"]).replace("\\", "/").lstrip("./")
            if normalized_file in test_files:
                continue
            ranking.append(
                {
                    "file": location["file"],
                    "line": location["line"],
                    "score": score,
                    "suggestion": str(suggestion),
                }
            )
            if len(ranking) >= top:
                break
        if len(ranking) >= top:
            break

    for index, entry in enumerate(ranking, start=1):
        entry["rank"] = index
    return ranking


def run_pipeline(args: argparse.Namespace) -> dict[str, Any]:
    """Run end-to-end SFLKit-based fault localization and return payload."""
    project_dir = Path(args.project_dir).resolve()
    if not project_dir.exists() or not project_dir.is_dir():
        raise FileNotFoundError(f"Project directory does not exist: {project_dir}")

    Language.PYTHON.setup()
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    LOGGER.debug("Starting local fault localization for %s", project_dir)

    if args.work_dir:
        work_dir = Path(args.work_dir).resolve()
        work_dir.mkdir(parents=True, exist_ok=True)
        cleanup = False
    else:
        work_dir = Path(tempfile.mkdtemp(prefix="pwfl-local-"))
        cleanup = not args.keep_workdir

    pytest_filter = args.pytest_k

    try:
        (
            instrumented_dir,
            events_dir,
            mapping_file,
            failing,
            passing,
            undefined,
            test_files,
        ) = _collect_with_sflkit(
            project_dir=project_dir,
            mode=args.mode,
            tests=args.tests,
            pytest_filter=pytest_filter,
            timeout=args.timeout,
            workers=args.workers,
            work_dir=work_dir,
        )

        if not failing:
            raise RuntimeError(
                "No failing tests found. Fault localization requires at least one failing test."
            )
        if not passing:
            raise RuntimeError(
                "No passing tests found. Fault localization requires at least one passing test."
            )

        analyzer = _build_analyzer(events_dir, mapping_file, args.mode)
        ranking = _rank_from_analyzer(
            analyzer=analyzer,
            base_dir=instrumented_dir,
            mode=args.mode,
            metric_name=args.metric,
            top=args.top,
            test_files=test_files,
        )
    finally:
        if cleanup:
            shutil.rmtree(work_dir, ignore_errors=True)
            LOGGER.debug("Removed temporary work directory %s", work_dir)

    if not ranking:
        raise RuntimeError(
            "No ranked suspicious lines were produced. Try a different --mode."
        )

    return {
        "project_dir": str(project_dir),
        "summary": {
            "mode": args.mode,
            "metric": args.metric,
            "failing_tests": len(failing),
            "passing_tests": len(passing),
            "undefined_tests": len(undefined),
            "ranked_locations": len(ranking),
        },
        "tests": {
            "failing": failing,
            "passing": passing,
            "undefined": undefined,
        },
        "ranking": ranking,
    }


def build_parser() -> argparse.ArgumentParser:
    """Create argument parser for the local-project CLI."""
    parser = argparse.ArgumentParser(
        description="Run local SFLKit-based fault localization and export ranked lines to JSON.",
    )
    parser.add_argument("project_dir", help="Path to the local project directory.")
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose debug logging.",
    )
    parser.add_argument(
        "-t",
        "--tests",
        nargs="+",
        type=str,
        default=None,
        help="One or more relative paths to test files/directories inside the project directory. "
        "If omitted, SFLKit attempts test discovery automatically.",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="pwfl_ranking.json",
        help="Output JSON path (default: pwfl_ranking.json).",
    )
    parser.add_argument(
        "-n",
        "--top",
        type=int,
        default=200,
        help="Maximum number of ranked lines to store (default: 200).",
    )
    parser.add_argument(
        "-m",
        "--mode",
        choices=list(MODELS.keys()),
        default="line",
        help="Analysis mode (default: line).",
    )
    parser.add_argument(
        "-s",
        "--metric",
        default="ochiai",
        help="Suspiciousness metric used for ranking (default: ochiai). "
        "Check SFLKit for all possible metrics.",
    )
    parser.add_argument(
        "-k",
        "--pytest-k",
        default=None,
        help="Optional pytest -k filter expression to restrict executed tests.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Pytest runner timeout in seconds (default: 120).",
    )
    parser.add_argument(
        "-w",
        "--workers",
        type=int,
        default=4,
        help="Number of parallel pytest workers used by SFLKit (default: 4).",
    )
    parser.add_argument(
        "--work-dir",
        default=None,
        help="Optional directory for instrumentation/events/mapping artifacts.",
    )
    parser.add_argument(
        "--keep-workdir",
        action="store_true",
        help="Keep generated work directory when using an auto-created temporary one.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = build_parser()
    if argcomplete is not None:
        argcomplete.autocomplete(parser)
    args = parser.parse_args(argv)

    if not LOGGER.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(name)s :: %(levelname)-8s :: %(message)s",
        )
    if args.verbose:
        LOGGER.setLevel(logging.DEBUG)
        LOGGER.debug("Verbose logging enabled")

    try:
        payload: dict[str, Any] = run_pipeline(args)
    except Exception as error:
        LOGGER.exception("CLI execution failed: %s", error)
        return 1

    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2))
    LOGGER.info("Wrote ranked suspicious lines to: %s", output_path)
    LOGGER.info(
        "Summary: %s failing / %s passing / %s undefined / %s ranked lines",
        payload["summary"]["failing_tests"],
        payload["summary"]["passing_tests"],
        payload["summary"]["undefined_tests"],
        payload["summary"]["ranked_locations"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
