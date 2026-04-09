"""
Aggregate per-subject evaluation outputs into study-wide summary files.
"""

import json
from pathlib import Path

from sflkit.analysis.spectra import Spectrum
from sflkit.evaluation import Scenario

from pwfl.analyze import distances

subjects = [
    "ansible",
    "black",
    "calculator",
    "cookiecutter",
    "expression",
    "fastapi",
    "httpie",
    "keras",
    "luigi",
    "markup",
    "matplotlib",
    "middle",
    "pandas",
    "pysnooper",
    "sanic",
    "scrapy",
    "spacy",
    "thefuck",
    "tornado",
    "tqdm",
    "youtubedl",
]

metrics = [
    Spectrum.Tarantula.__name__,
    Spectrum.Ochiai.__name__,
    Spectrum.DStar.__name__,
    Spectrum.Naish2.__name__,
    Spectrum.GP13.__name__,
]

dependency_types = [f"line{suffix}" for suffix, _ in distances]
dependency_PRFL = [f"PRFL{suffix}" for suffix, _ in distances]
dependency_TCP = [f"TCP{suffix}" for suffix, _ in distances]
scenarios = [scenario.value for scenario in Scenario]

localizations = ["top-1", "top-5", "top-10", "top-200", "exam", "wasted-effort"]


def summarize_all(output: str | None = None):
    """
    Summarize baseline PWFL results across all configured subjects.

    :param output: Optional output path. Defaults to ``summary.json``.
    :type output: str | None
    :returns: None
    """
    results_dir = Path("results")
    if not results_dir.exists():
        return
    results: dict[
        str, list[str] | dict[str, dict[str, dict[str, dict[str, float | list[float]]]]]
    ] = {
        "subjects": list(),
        **{
            dependency: {
                metric: {
                    scenario: {m: {"avg": 0.0, "all": list()} for m in localizations}
                    for scenario in scenarios
                }
                for metric in metrics
            }
            for dependency in dependency_types
        },
    }
    number_of_subjects = 0
    for subject in subjects:
        for i in range(100):
            subject_results = results_dir / f"{subject}_{i}.json"
            if not subject_results.exists():
                continue
            with subject_results.open() as f:
                subject_data = json.load(f)
            for s in subject_data:
                # noinspection PyUnresolvedReferences
                results["subjects"].append(s)
                number_of_subjects += 1
                # Keep raw per-subject values so we can compute aggregates and
                # still support downstream statistical analyses.
                for dependency in dependency_types:
                    for m in metrics:
                        for sce in scenarios:
                            for loc in localizations:
                                # noinspection PyUnresolvedReferences
                                results[dependency][m][sce][loc]["all"].append(
                                    subject_data[s][dependency][m][sce][loc]
                                )

    for dependency in dependency_types:
        for m in metrics:
            for sce in scenarios:
                for loc in localizations:
                    # noinspection PyTypeChecker
                    results[dependency][m][sce][loc]["avg"] = (
                        sum(results[dependency][m][sce][loc]["all"])
                        / number_of_subjects
                    )
    with open(output or "summary.json", "w") as f:
        json.dump(results, f, indent=1)


def summarize_prfl_all(output: str | None = None):
    """
    Summarize PRFL result files into one dataset.

    :param output: Optional output path. Defaults to ``summary_prfl.json``.
    :type output: str | None
    :returns: None
    """
    results_dir = Path("results")
    if not results_dir.exists():
        return
    results: dict[
        str,
        list[str] | dict[str, dict[str, dict[str, dict[str, float | list[float]]]]],
    ] = {
        "subjects": list(),
        **{
            dependency: {
                metric: {
                    scenario: {m: {"avg": 0.0, "all": list()} for m in localizations}
                    for scenario in scenarios
                }
                for metric in metrics
            }
            for dependency in dependency_PRFL
        },
    }
    number_of_subjects = 0
    for subject in subjects:
        for i in range(100):
            subject_results = results_dir / f"{subject}_{i}_pr.json"
            if not subject_results.exists():
                continue
            with subject_results.open() as f:
                subject_data = json.load(f)
            for s in subject_data:
                # noinspection PyUnresolvedReferences
                results["subjects"].append(s)
                number_of_subjects += 1
                for dependency, target in zip(dependency_types, dependency_PRFL):
                    for m in metrics:
                        for sce in scenarios:
                            for loc in localizations:
                                # noinspection PyUnresolvedReferences
                                results[target][m][sce][loc]["all"].append(
                                    subject_data[s][dependency][m][sce][loc]
                                )

    for dependency, target in zip(dependency_types, dependency_PRFL):
        for m in metrics:
            for sce in scenarios:
                for loc in localizations:
                    # noinspection PyTypeChecker
                    results[target][m][sce][loc]["avg"] = (
                        sum(results[target][m][sce][loc]["all"]) / number_of_subjects
                    )
    with open(output or "summary_prfl.json", "w") as f:
        json.dump(results, f, indent=1)


def summarize_tcp_all(output: str | None = None, clean=False):
    """
    Summarize TCP evaluation outputs.

    :param output: Optional output path. Defaults to ``summary_tcp.json``.
    :type output: str | None
    :param clean: Summarize clean-mode results when ``True``.
    :type clean: bool
    :returns: None
    """
    clean_suffix = "_clean" if clean else ""
    results_dir = Path("results")
    if not results_dir.exists():
        return
    results: dict[
        str,
        list[str] | dict[str, dict[str, dict[str, dict[str, float | list[float]]]]],
    ] = {
        "subjects": list(),
        **{
            dependency: {
                metric: {
                    scenario: {m: {"avg": 0.0, "all": list()} for m in localizations}
                    for scenario in scenarios
                }
                for metric in metrics
            }
            for dependency in dependency_TCP
        },
    }
    number_of_subjects = 0
    for subject in subjects:
        for i in range(100):
            # noinspection PyUnresolvedReferences
            subject_results = results_dir / f"{subject}_{i}{clean_suffix}_tcp.json"
            if not subject_results.exists():
                continue
            with subject_results.open() as f:
                subject_data = json.load(f)
            for s in subject_data:
                # noinspection PyUnresolvedReferences
                results["subjects"].append(s)
                number_of_subjects += 1
                for dependency, target in zip(dependency_types, dependency_TCP):
                    for m in metrics:
                        for sce in scenarios:
                            for loc in localizations:
                                # noinspection PyUnresolvedReferences
                                results[target][m][sce][loc]["all"].append(
                                    subject_data[s][dependency][m][sce][loc]
                                )
    for dependency, target in zip(dependency_types, dependency_TCP):
        for m in metrics:
            for sce in scenarios:
                for loc in localizations:
                    # noinspection PyTypeChecker
                    results[target][m][sce][loc]["avg"] = (
                        sum(results[target][m][sce][loc]["all"]) / number_of_subjects
                    )
    with open(output or "summary_tcp.json", "w") as f:
        json.dump(results, f, indent=1)
