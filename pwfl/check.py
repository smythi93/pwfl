import json
import os
import re

from pwfl.logger import LOGGER

PATTERN_CG_BUILD = re.compile(r"cg_(?P<name>[^.]*)_build\.json")
PATTERN_CG = re.compile(r"cg_(?P<name>[^.]*)\.json")
PATTERN_CG_PR = re.compile(r"cg_(?P<name>[^.]*)_pr\.json")
PATTERN_EVENTS = re.compile(r"report_(?P<name>[^.]*)\.json")
PATTERN_TCP = re.compile(r"tcp_(?P<name>[^.]*)\.json")


def check_cg(msg, pattern, need_investigation_file, directory=None):
    if directory is None:
        directory = "reports"
    skipped = list()
    functions = list()
    errors = list()
    check_failed = list()
    missing_bug = list()
    empty_passing = list()
    for file in os.listdir(directory):
        match = pattern.match(file)
        if match:
            file = os.path.join(directory, file)
            with open(file, "r") as f:
                report = json.load(f)
            for identifier in report:
                if "check" not in report[identifier]:
                    skipped.append(identifier)
                if (
                    "check" in report[identifier]
                    and report[identifier]["check"] == "successful"
                ):
                    functions.append(identifier)
                if "error" in report[identifier]:
                    errors.append((identifier, report[identifier]["error"]))
                if (
                    "check" in report[identifier]
                    and report[identifier]["check"] == "failed"
                ):
                    check_failed.append(identifier)
                    buggy = list()
                    empty = False
                    for key, value in report[identifier].items():
                        if value == "empty":
                            empty = True
                        if value == "not_found":
                            buggy.append(key[4:])
                    if empty:
                        empty_passing.append(identifier)
                    if buggy:
                        missing_bug.append((identifier, buggy))
    need_investigation = {
        "errors": errors,
        "missing_bug": missing_bug,
        "empty_passing": empty_passing,
    }
    total = len(skipped) + len(functions) + len(check_failed) + len(errors)
    subjects = len(functions) + len(check_failed) + len(errors)
    LOGGER.info(msg)
    LOGGER.info(f"Total: {total}")
    LOGGER.info(f"Skipped: {len(skipped)}")
    LOGGER.info(f"Investigate: {subjects}")
    LOGGER.info(f"Errors: {len(errors)}")
    LOGGER.info(f"Check failed: {len(check_failed)}")
    LOGGER.info(f"Functional: {len(functions)}")
    with open(need_investigation_file, "w") as f:
        json.dump(need_investigation, f, indent=1)


def check_cg_build(directory=None):
    check_cg(
        "Checking CG build reports",
        PATTERN_CG_BUILD,
        "need_investigation_cg_build.json",
        directory,
    )


def check_cg_events(directory=None):
    check_cg(
        "Checking CG events reports",
        PATTERN_CG,
        "need_investigation_cg.json",
        directory,
    )


def check_cg_pr(directory=None):
    check_cg(
        "Checking CG PR reports",
        PATTERN_CG_PR,
        "need_investigation_cg_pr.json",
        directory,
    )


def check_events(directory=None):
    check_cg(
        "Checking events reports",
        PATTERN_EVENTS,
        "need_investigation.json",
        directory,
    )


def check_tcp(directory=None):
    check_cg(
        "Checking TCP reports",
        PATTERN_TCP,
        "need_investigation_tcp.json",
        directory,
    )
