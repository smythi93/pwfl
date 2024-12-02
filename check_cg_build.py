import json
import os
import re
import sys

PATTERN = re.compile(r"cg_(?P<name>[^.]*)_build\.json")


def main(directory=None):
    if directory is None:
        directory = "reports"
    skipped = list()
    functions = list()
    errors = list()
    check_failed = list()
    missing_bug = list()
    empty_passing = list()
    for file in os.listdir(directory):
        match = PATTERN.match(file)
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
    print(f"Total: {total}")
    print(f"Skipped: {len(skipped)}")
    print(f"Investigate: {subjects}")
    print(f"Errors: {len(errors)}")
    print(f"Check failed: {len(check_failed)}")
    print(f"Functional: {len(functions)}")
    with open("need_investigation.json", "w") as f:
        json.dump(need_investigation, f, indent=1)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        main(sys.argv[1])
    else:
        main()
