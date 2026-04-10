"""
Docker helper for self-contained PWFL workflows.

This helper can build the image, run the reduced evaluation inside a persistent
container, copy the generated artifacts back to the host, and leave the
container available for later inspection.
"""

from __future__ import annotations

import argparse
import subprocess
import threading
import time
import webbrowser
from datetime import datetime
from pathlib import Path

IMAGE = "pwfl"
CONTAINER = "pwfl-eval"
WORKSPACE = "/workspace"
OUTPUT_ROOT = Path("docker-output")


def run(command: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    """
    Run a Docker CLI command.

    :param command: Docker CLI arguments including the ``docker`` executable.
    :param check: Raise an exception when the command fails.
    :returns: Completed process object.
    """
    return subprocess.run(command, text=True, check=check)


def _open_notebook_in_browser(url: str, delay_seconds: float = 3.0) -> None:
    """
    Open the notebook URL in the default browser after a short delay.

    :param url: URL to open.
    :param delay_seconds: Delay to give Jupyter time to start.
    :returns: None
    """
    time.sleep(delay_seconds)
    try:
        webbrowser.open(url, new=2)
    except Exception as error:
        print(f"Could not open browser automatically: {error}")


def build_image(no_cache: bool = False) -> None:
    """
    Build the PWFL image.

    :param no_cache: Build without using Docker layer cache.
    :returns: None
    """
    command = ["docker", "build", "-t", IMAGE]
    if no_cache:
        command.append("--no-cache")
    command.append(".")
    run(command)


def image_exists() -> bool:
    """
    Check whether the PWFL image already exists locally.

    :returns: True when image is present, False otherwise.
    """
    inspect = subprocess.run(
        ["docker", "image", "inspect", IMAGE],
        text=True,
        capture_output=True,
    )
    return inspect.returncode == 0


def get_image_id() -> str:
    """
    Return the Docker image id for ``IMAGE``.

    :returns: Image id string.
    :raises RuntimeError: If the image does not exist locally.
    """
    inspect = subprocess.run(
        ["docker", "image", "inspect", "-f", "{{.Id}}", IMAGE],
        text=True,
        capture_output=True,
    )
    if inspect.returncode != 0:
        raise RuntimeError(f"Docker image not found: {IMAGE}")
    return inspect.stdout.strip()


def ensure_image(force_build: bool = False, no_cache: bool = False) -> str:
    """
    Build the image only when required and return its image id.

    :param force_build: Rebuild even when the image already exists.
    :param no_cache: Build without using Docker cache.
    :returns: Current image id.
    """
    if force_build:
        build_image(no_cache=no_cache)
        return get_image_id()
    if not image_exists():
        build_image(no_cache=no_cache)
    return get_image_id()


def container_exists() -> bool:
    """
    Check whether the helper container exists.

    :returns: True when container exists, otherwise False.
    """
    inspect = subprocess.run(
        ["docker", "inspect", CONTAINER],
        text=True,
        capture_output=True,
    )
    return inspect.returncode == 0


def get_container_image_id() -> str:
    """
    Return the image id currently used by the helper container.

    :returns: Image id string.
    :raises RuntimeError: If the container does not exist.
    """
    inspect = subprocess.run(
        ["docker", "inspect", "-f", "{{.Image}}", CONTAINER],
        text=True,
        capture_output=True,
    )
    if inspect.returncode != 0:
        raise RuntimeError(f"Docker container not found: {CONTAINER}")
    return inspect.stdout.strip()


def remove_container() -> None:
    """
    Remove the helper container if it exists.

    :returns: None
    """
    if container_exists():
        run(["docker", "rm", "-f", CONTAINER])


def ensure_container(image_id: str) -> None:
    """
    Create the long-lived helper container if it does not already exist.

    The container stays alive so that users can inspect the generated files or
    open an interactive shell afterward.

    :returns: None
    """
    if container_exists():
        # Recreate the long-lived container when image changed after a rebuild.
        if get_container_image_id() != image_id:
            print("Container image is outdated; recreating helper container.")
            remove_container()
        else:
            inspect = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Running}}", CONTAINER],
                text=True,
                capture_output=True,
            )
            if inspect.returncode == 0 and inspect.stdout.strip() != "true":
                run(["docker", "start", CONTAINER])
            return
    run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            CONTAINER,
            IMAGE,
            "bash",
            "-lc",
            "trap : TERM INT; while true; do sleep 3600; done",
        ]
    )


def exec_in_container(args: list[str]) -> None:
    """
    Execute a command in the persistent helper container.

    :param args: Command to run inside the container.
    :returns: None
    """
    run(["docker", "exec", CONTAINER, *args])


def copy_paths(paths_to_copy: list[str]) -> Path:
    """
    Copy selected outputs from the container back to the host.

    :returns: Host output directory.
    """
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = OUTPUT_ROOT / stamp
    target.mkdir(parents=True, exist_ok=True)

    for relative in paths_to_copy:
        run(
            [
                "docker",
                "cp",
                f"{CONTAINER}:{WORKSPACE}/{relative}",
                str(target / relative),
            ]
        )
    return target


def print_summary_files(output_dir: Path) -> None:
    """
    Print copied JSON artifacts so results are easy to inspect.

    :param output_dir: Host directory containing copied artifacts.
    :returns: None
    """
    json_files = sorted(output_dir.rglob("*.json"))
    if not json_files:
        print("No JSON summary files were copied.")
        return
    print("Copied summary files:")
    for path in json_files:
        print(f"  - {path.relative_to(output_dir)}")


def small_eval(force_build: bool = False, tiny: bool = False) -> None:
    """
    Run the reduced evaluation, copy results out, and print inspection info.

    :returns: None
    """
    image_id = ensure_image(force_build=force_build)
    ensure_container(image_id=image_id)
    cmd = ["python", "run_small_eval.py"]
    if tiny:
        cmd.append("--tiny")
    exec_in_container(cmd)
    output_dir = copy_paths(["small_eval"])
    print_summary_files(output_dir)
    print(f"Copied outputs to: {output_dir.resolve()}")
    print(f"Inspect the live container with: docker exec -it {CONTAINER} bash")


def middle_cli(
    force_build: bool = False,
    no_cache: bool = False,
    mode: str = "line",
    metric: str = "tarantula",
    workers: int = 4,
    verbose: bool = False,
) -> None:
    """
    Run the middle example through the local PWFL CLI and export the ranking.

    :returns: None
    """
    image_id = ensure_image(force_build=force_build, no_cache=no_cache)
    ensure_container(image_id=image_id)
    cmd = [
        "pwfl",
        "middle",
        "-t",
        "tests.py",
        "-m",
        mode,
        "-s",
        metric,
        "-w",
        str(workers),
    ]
    if verbose:
        cmd.append("-v")
    exec_in_container(cmd)
    output_dir = copy_paths(["pwfl_ranking.json"])
    print_summary_files(output_dir)
    print(f"Copied outputs to: {output_dir.resolve()}")
    print(f"Inspect the live container with: docker exec -it {CONTAINER} bash")


def shell(force_build: bool = False) -> None:
    """
    Open an interactive shell in the persistent helper container.

    :returns: None
    """
    image_id = ensure_image(force_build=force_build)
    ensure_container(image_id=image_id)
    run(["docker", "exec", "-it", CONTAINER, "bash"], check=False)


def example(force_build: bool, auto_open: bool = True, no_cache: bool = False) -> None:
    """
    Run the Jupyter notebook example.

    :returns: None
    """
    ensure_image(force_build=force_build, no_cache=no_cache)

    # Resetting the lab workspace avoids stale kernel/session ids after restarts.
    notebook_url = "http://localhost:8888/lab/tree/example.ipynb?reset"
    if auto_open:
        threading.Thread(
            target=_open_notebook_in_browser,
            args=(notebook_url,),
            daemon=True,
        ).start()
        print(f"Opening notebook in browser: {notebook_url}")

    run(
        [
            "docker",
            "run",
            "--rm",
            "-it",
            "-p",
            "8888:8888",
            IMAGE,
            "jupyter",
            "lab",
            "--ip=0.0.0.0",
            "--port=8888",
            "--allow-root",
            "--ServerApp.token=",
            "--ServerApp.password=",
            "--notebook-dir=/workspace",
        ]
    )


def main() -> None:
    """
    Parse CLI arguments and dispatch to the selected Docker workflow.

    :returns: None
    """
    parser = argparse.ArgumentParser(description="PWFL Docker helper")
    sub = parser.add_subparsers(dest="command", required=True)
    build_parser = sub.add_parser("build", help="Build the PWFL image")
    build_parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Build without Docker layer cache",
    )
    small_eval_parser = sub.add_parser(
        "small-eval",
        help="Run run_small_eval.py inside a persistent container and copy outputs",
    )
    small_eval_parser.add_argument(
        "--build",
        action="store_true",
        help="Build the image before running, even if it already exists",
    )
    small_eval_parser.add_argument(
        "--tiny",
        action="store_true",
        help="Run the script with even fewer subject, to verify everything works as expected",
    )
    middle_parser = sub.add_parser(
        "middle-cli",
        help="Run the local PWFL CLI on middle with fixed test target tests.py",
    )
    middle_parser.add_argument(
        "--build",
        action="store_true",
        help="Build the image before running, even if it already exists",
    )
    middle_parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Build without Docker layer cache when used with --build",
    )
    middle_parser.add_argument(
        "-m",
        "--mode",
        default="line",
        help="Analysis mode for PWFL (default: line)",
    )
    middle_parser.add_argument(
        "-s",
        "--metric",
        default="tarantula",
        help="Suspiciousness metric for PWFL (default: tarantula)",
    )
    middle_parser.add_argument(
        "-w",
        "--workers",
        type=int,
        default=4,
        help="PWFL parallel workers (default: 4)",
    )
    middle_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose mode for PWFL (off by default)",
    )
    shell_parser = sub.add_parser(
        "shell", help="Open a shell inside the persistent container"
    )
    shell_parser.add_argument(
        "--build",
        action="store_true",
        help="Build the image before opening shell, even if it already exists",
    )
    example_parser = sub.add_parser(
        "example",
        help="Run the Jupyter notebook example",
    )
    example_parser.add_argument(
        "--build",
        action="store_true",
        help="Build the image before running, even if it already exists",
    )
    example_parser.add_argument(
        "--no-open",
        action="store_true",
        help="Do not automatically open the notebook URL in your browser",
    )
    example_parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Build without Docker layer cache when used with --build",
    )

    args = parser.parse_args()
    if args.command == "build":
        build_image(no_cache=args.no_cache)
    elif args.command == "small-eval":
        small_eval(force_build=args.build, tiny=args.tiny)
    elif args.command == "middle-cli":
        middle_cli(
            force_build=args.build,
            no_cache=args.no_cache,
            mode=args.mode,
            metric=args.metric,
            workers=args.workers,
            verbose=args.verbose,
        )
    elif args.command == "shell":
        shell(force_build=args.build)
    elif args.command == "example":
        example(
            force_build=args.build,
            auto_open=not args.no_open,
            no_cache=args.no_cache,
        )


if __name__ == "__main__":
    main()
