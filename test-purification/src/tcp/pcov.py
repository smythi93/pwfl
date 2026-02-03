DEFAULT_COVERAGE_FILENAME = ".tcpcov"
ENV_VAR = "TCP_COVERAGE_FILE"


def main(args=None):
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-s",
        "--src",
        required=True,
        type=str,
        help="Set to track coverage of a specific source file (basename only).",
    )
    parsed, script_args = parser.parse_known_args(args)
    filename = parsed.src
    import sys

    if not script_args:
        print("No script or module specified to run.", file=sys.stderr)
        sys.exit(1)

    # Prepare coverage data storage and attach to os module for access in instrumented code
    covered = set()
    import os

    os.pcov_lines = covered

    # Prepare sys.argv for the script/module
    sys.argv = script_args
    try:
        # Check if running as a module
        import runpy

        if script_args[0] == "-m":
            # Run as module
            if len(script_args) < 2:
                print("No module specified after -m.", file=sys.stderr)
                sys.exit(1)
            module_name = script_args[1]
            sys.argv = [module_name] + script_args[2:]
            runpy.run_module(module_name, run_name="__main__")
        else:
            # Run as script
            script_path = script_args[0]
            sys.argv = [script_path] + script_args[1:]
            runpy.run_path(script_path, run_name="__main__")
    finally:
        # Write coverage data
        covdata = {}
        for lineno in covered:
            covdata.setdefault(filename, []).append(lineno)
        import json

        with open(os.environ.get(ENV_VAR, DEFAULT_COVERAGE_FILENAME), "w") as f:
            json.dump(covdata, f)


if __name__ == "__main__":
    main()
