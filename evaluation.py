import argparse
import logging
import sys

from pwfl.analyze import analyze
from pwfl.cg import build_call_graph, get_call_graph_events
from pwfl.check import (
    check_events,
    check_cg_build,
    check_cg_events,
    check_cg_pr,
    check_tcp,
)
from pwfl.evaluate import evaluate
from pwfl.events import get_events
from pwfl.interpret import interpret
from pwfl import logger as pwfl_logger
from sflkit import logger as sflkit_logger
from tcp import logger as tcp_logger
from pwfl.prfl import build_pr, evaluate_prfl
from pwfl.summarize import summarize_all, summarize_prfl_all, summarize_tcp_all
from pwfl.purification import get_tcp_events, tcp_analyze, tcp_evaluate
from pwfl.tests import get_results, analyze_file


def get_parser():
    argument_parser = argparse.ArgumentParser(description="Evaluate PWFL")
    argument_parser.add_argument(
        "-v", "--verbose", action="store_true", help="increase output verbosity"
    )
    command = argument_parser.add_subparsers(
        dest="command", required=True, help="sub-command help"
    )

    # Check parser
    check = command.add_parser("check", help="check reports")
    check.add_argument("-d", type=str, default=None, dest="directory", help="directory")
    check.add_argument("--events", action="store_true", help="check events")
    check.add_argument("--cg-build", action="store_true", help="check CG build")
    check.add_argument("--cg-events", action="store_true", help="check CG events")
    check.add_argument("--cg-pr", action="store_true", help="check CG PR")
    check.add_argument("--tcp", action="store_true", help="check TCP events")

    # Tests parser
    tests = command.add_parser("tests", help="analyze tests for motivation study")
    tests_command = tests.add_subparsers(
        dest="tests_command", required=True, help="sub-command help"
    )
    tests_get = tests_command.add_parser("get", help="get values of all subjects")
    tests_get.add_argument(
        "--skip",
        default=False,
        action="store_true",
        dest="skip",
        help="skip subjects with non-failing tests",
    )

    tests_analyze = tests_command.add_parser("analyze", help="analyze values")
    tests_analyze.add_argument(
        "-f", type=str, default=None, dest="file", help="file to analyze"
    )

    # Events parser
    events = command.add_parser("events", help="analyze events")

    # Analysis parser
    analysis = command.add_parser("analyze", help="analyze projects")

    # Evaluation parser
    evaluate = command.add_parser("evaluate", help="evaluate projects")

    # CG parser
    cg = command.add_parser("cg", help="construct call graphs")
    cg_command = cg.add_subparsers(
        dest="cg_command", required=True, help="sub-command help"
    )
    cg_events = cg_command.add_parser("events", help="get call graph events")
    cg_build = cg_command.add_parser("build", help="build call graph")

    # prfl parser
    prfl = command.add_parser("prfl", help="analyze prfl")
    prfl_command = prfl.add_subparsers(
        dest="prfl_command", required=True, help="sub-command help"
    )
    prfl_build = prfl_command.add_parser("build", help="build pr")
    prfl_evaluate = prfl_command.add_parser("evaluate", help="evaluate prfl")

    # tcp parser
    tcp = command.add_parser("tcp", help="test case purification with event collection")
    tcp_command = tcp.add_subparsers(
        dest="tcp_command", required=True, help="sub-command help"
    )
    tcp_events = tcp_command.add_parser("events", help="get tcp events")
    tcp_events.add_argument(
        "--disable_slicing",
        default=True,
        action="store_false",
        dest="enable_slicing",
        help="disable dynamic slicing during purification",
    )
    tcp_analyze = tcp_command.add_parser("analyze", help="analyze tcp")
    tcp_evaluate = tcp_command.add_parser("evaluate", help="evaluate tcp")
    tcp_evaluate.add_argument(
        "--clean",
        default=False,
        action="store_true",
        dest="clean",
        help="Do not leverage the refinement score and use the original spectrum for evaluation, i.e., "
        "the purified tests are only used for event collection, not for rank refinement.",
    )

    # summarize parser
    command.add_parser("summarize", help="summarize results")
    command.add_parser("summarize-prfl", help="summarize prfl results")
    summarize_tcp = command.add_parser("summarize-tcp", help="summarize tcp results")
    summarize_tcp.add_argument(
        "--clean",
        default=False,
        action="store_true",
        dest="clean",
        help="Do not leverage the refinement score and use the original spectrum for evaluation, i.e., "
        "the purified tests are only used for event collection, not for rank refinement.",
    )

    # interpret parser
    command.add_parser("interpret", help="interpret results and write tex tables")

    # add p, i, s, e to all parsers
    for subparser in [
        tests_get,
        events,
        analysis,
        evaluate,
        cg_events,
        cg_build,
        prfl_build,
        prfl_evaluate,
        tcp_events,
        tcp_analyze,
        tcp_evaluate,
    ]:
        subparser.add_argument(
            "-p", type=str, default=None, dest="project_name", help="project name"
        )
        subparser.add_argument(
            "-i", type=int, default=None, dest="bug_id", help="bug id"
        )
        subparser.add_argument("-s", type=int, default=0, dest="start", help="start")
        subparser.add_argument("-e", type=int, default=None, dest="end", help="end")

    return argument_parser


def main(args=None):
    argument_parser = get_parser()
    arguments = argument_parser.parse_args(args or sys.argv[1:])
    if arguments.verbose:
        pwfl_logger.debug()
        sflkit_logger.LOGGER.setLevel(logging.DEBUG)
        for handler in sflkit_logger.LOGGER.handlers:
            handler.setLevel(logging.DEBUG)
        tcp_logger.debug()
    if arguments.command == "check":
        fallback = not any(
            [
                arguments.events,
                arguments.cg_build,
                arguments.cg_events,
                arguments.cg_pr,
                arguments.tcp,
            ]
        )
        if arguments.events or fallback:
            check_events(arguments.directory)
        if arguments.cg_build or fallback:
            check_cg_build(arguments.directory)
        if arguments.cg_events or fallback:
            check_cg_events(arguments.directory)
        if arguments.cg_pr or fallback:
            check_cg_pr(arguments.directory)
        if arguments.tcp or fallback:
            check_tcp(arguments.directory)
    elif arguments.command == "tests":
        if arguments.tests_command == "get":
            get_results(
                arguments.project_name,
                arguments.bug_id,
                arguments.start,
                arguments.end,
                arguments.skip,
            )
        elif arguments.tests_command == "analyze":
            analyze_file(arguments.file)
    elif arguments.command == "events":
        get_events(
            arguments.project_name, arguments.bug_id, arguments.start, arguments.end
        )
    elif arguments.command == "tcp":
        if arguments.tcp_command == "events":
            get_tcp_events(
                arguments.project_name,
                arguments.bug_id,
                arguments.start,
                arguments.end,
                arguments.enable_slicing,
            )
        elif arguments.tcp_command == "analyze":
            tcp_analyze(
                arguments.project_name, arguments.bug_id, arguments.start, arguments.end
            )
        elif arguments.tcp_command == "evaluate":
            tcp_evaluate(
                arguments.project_name,
                arguments.bug_id,
                arguments.start,
                arguments.end,
                arguments.clean,
            )
    elif arguments.command == "analysis":
        analyze(
            arguments.project_name, arguments.bug_id, arguments.start, arguments.end
        )
    elif arguments.command == "evaluate":
        evaluate(
            arguments.project_name, arguments.bug_id, arguments.start, arguments.end
        )
    elif arguments.command == "cg":
        if arguments.cg_command == "events":
            get_call_graph_events(
                arguments.project_name, arguments.bug_id, arguments.start, arguments.end
            )
        elif arguments.cg_command == "build":
            build_call_graph(
                arguments.project_name, arguments.bug_id, arguments.start, arguments.end
            )
    elif arguments.command == "prfl":
        if arguments.prfl_command == "build":
            build_pr(
                arguments.project_name, arguments.bug_id, arguments.start, arguments.end
            )
        elif arguments.prfl_command == "evaluate":
            evaluate_prfl(
                arguments.project_name, arguments.bug_id, arguments.start, arguments.end
            )
    elif arguments.command == "summarize":
        summarize_all()
    elif arguments.command == "summarize-prfl":
        summarize_prfl_all()
    elif arguments.command == "summarize-tcp":
        summarize_tcp_all()
    elif arguments.command == "interpret":
        interpret(tex=True)


if __name__ == "__main__":
    main()
