"""
Run a reduced PWFL evaluation suite over a fixed subject subset.

The script copies ``evaluation.py`` into ``small_eval/`` and executes a
deterministic sequence of pipeline commands for selected subject/bug pairs.
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

SUBJECTS = {
    "calculator": [1],
    "expression": [1],
    "markup": [1, 2],
    "middle": [1, 2],
}

PARENT_DIR = Path(__file__).parent

EVALUATION_SCRIPT = PARENT_DIR / "evaluation.py"
TARGET_DIR = PARENT_DIR / "small_eval"
TARGET_SCRIPT = TARGET_DIR / "evaluation.py"


def copy_eval_script():
    """
    Copy the main evaluation CLI into the isolated ``small_eval`` directory.

    :returns: None
    """
    shutil.copyfile(EVALUATION_SCRIPT, TARGET_SCRIPT)


def iterate_subjects():
    """
    Yield configured ``(subject, bug_id)`` pairs.

    :yields: Subject identifier and bug id to process.
    :rtype: tuple[str, int]
    """
    for subject in SUBJECTS:
        for bug_id in SUBJECTS[subject]:
            yield subject, bug_id


def run(args):
    """
    Execute ``evaluation.py`` with the provided argument tail.

    :param args: CLI arguments appended after the script path.
    :type args: list[str]
    :returns: None
    """
    subprocess.run(
        [
            sys.executable,
            TARGET_SCRIPT,
        ]
        + list(args),
        cwd=TARGET_DIR,
        stdout=sys.stdout,
        stderr=sys.stderr,
        check=True,
    )


def collect_events():
    """
    Collect baseline line and test events for each selected subject.

    :returns: None
    """
    for subject, bug_id in iterate_subjects():
        run(
            [
                "events",
                "-p",
                subject,
                "-i",
                str(bug_id),
            ],
        )


def analyze_events():
    """
    Run analyzer generation for each selected subject.

    :returns: None
    """
    for subject, bug_id in iterate_subjects():
        run(
            [
                "analyze",
                "-p",
                subject,
                "-i",
                str(bug_id),
            ]
        )


def evaluate_events():
    """
    Evaluate fault-localization rankings for each subject.

    :returns: None
    """
    for subject, bug_id in iterate_subjects():
        run(
            [
                "evaluate",
                "-p",
                subject,
                "-i",
                str(bug_id),
            ]
        )


def summarize_results():
    """
    Aggregate baseline evaluation results into one summary file.

    :returns: None
    """
    run(["summarize", "--out", "small_eval_results.json"])


def call_graph_events():
    """
    Collect call-graph-oriented events for PRFL processing.

    :returns: None
    """
    for subject, bug_id in iterate_subjects():
        run(["cg", "events", "-p", subject, "-i", str(bug_id)])


def build_call_graph():
    """
    Build call graphs from previously collected call-graph events.

    :returns: None
    """
    for subject, bug_id in iterate_subjects():
        run(["cg", "build", "-p", subject, "-i", str(bug_id)])


def prfl_build():
    """
    Compute PageRank-style weights from call graphs.

    :returns: None
    """
    for subject, bug_id in iterate_subjects():
        run(["prfl", "build", "-p", subject, "-i", str(bug_id)])


def prfl_evaluate():
    """
    Evaluate the PRFL-weighted localization variant.

    :returns: None
    """
    for subject, bug_id in iterate_subjects():
        run(["prfl", "evaluate", "-p", subject, "-i", str(bug_id)])


def prfl_summarize():
    """
    Aggregate PRFL results across all configured subjects.

    :returns: None
    """
    run(["summarize-prfl", "--out", "small_eval_prfl_results.json"])


def tcp_events():
    """
    Run test-case purification and collect TCP event traces.

    :returns: None
    """
    for subject, bug_id in iterate_subjects():
        run(["tcp", "events", "-p", subject, "-i", str(bug_id)])


def tcp_analyze():
    """
    Build TCP analyzers for all configured subjects.

    :returns: None
    """
    for subject, bug_id in iterate_subjects():
        run(["tcp", "analyze", "-p", subject, "-i", str(bug_id)])


def tcp_evaluate():
    """
    Evaluate TCP-refined fault-localization performance.

    :returns: None
    """
    for subject, bug_id in iterate_subjects():
        run(["tcp", "evaluate", "-p", subject, "-i", str(bug_id)])


def tcp_summarize():
    """
    Aggregate TCP evaluation results into one summary file.

    :returns: None
    """
    run(["summarize-tcp", "--out", "small_eval_tcp_results.json"])


def main():
    """
    Execute the complete reduced experiment workflow.

    The order is intentional: each stage depends on artifacts produced by
    previous stages.

    :returns: None
    """
    argument_parser = argparse.ArgumentParser()
    argument_parser.add_argument(
        "--tiny",
        action="store_true",
        help="Run an even smaller evaluation with three subjects",
    )

    args = argument_parser.parse_args()

    if args.tiny:
        del SUBJECTS["expression"]
        del SUBJECTS["markup"]

    # Prepare an isolated execution directory to avoid polluting top-level files.
    os.makedirs(TARGET_DIR, exist_ok=True)
    copy_eval_script()

    # Baseline PWFL pipeline.
    collect_events()
    analyze_events()
    evaluate_events()
    summarize_results()

    # Call-graph/PRFL extension.
    call_graph_events()
    build_call_graph()
    prfl_build()
    prfl_evaluate()
    prfl_summarize()

    # Test purification.
    tcp_events()
    tcp_analyze()
    tcp_evaluate()
    tcp_summarize()


if __name__ == "__main__":
    main()
