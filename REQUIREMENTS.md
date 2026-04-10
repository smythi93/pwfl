# REQUIREMENTS

This document summarizes the environment requirements for the PWFL artifact.

## 1) Hardware Requirements

- CPU: modern x86_64 or arm64 multi-core processor (8+ cores recommended for
  full reproduction).
- RAM:
  - Smoke evaluation (`small-eval --tiny`): at least 8 GB (16 GB recommended).
  - Full evaluation (PWFL + PRFL + TCP over all subjects): 32 GB recommended.
- Disk:
  - Base checkout + Python environment: ~5 GB.
  - Smoke run artifacts: typically <5 GB.
  - Full run artifacts/intermediate files: plan for 50+ GB free space.

No non-commodity peripherals are required.

## 2) Software Requirements

- OS: Linux or macOS (validated workflows use shell-compatible UNIX systems).
- Python: 3.10 or newer.
- Optional isolation path: Docker (recommended for reproducibility).

Python package dependencies are defined in `pyproject.toml` and mirrored in
`requirements.txt` with explicit versions.

Core dependencies:

- `tests4py>=0.0.13`
- `sflkit>=0.5.7` (PWFL is included in this release)
- `pyurify>=0.0.1`
- `numpy>=2.4.4`
- `seaborn>=0.13.2`
- `pytest>=9.0.3`
- `argcomplete>=3.6.3`

## 3) Runtime and Performance Notes

- Smoke run (`python docker_pwfl.py small-eval --tiny`): expected to complete in
  a few minutes on commodity hardware.
- Full study run (all subjects and variants): long-running workload; multiple
  days are expected depending on hardware and I/O throughput.
- Local CLI runs can be tuned per environment via `--timeout` (default 120s)
  and `--workers` (default 4) to balance runtime and stability.

## 4) Reusable Local CLI Workflow

- Entry point: `pwfl` (installed from `pyproject.toml`).
- Works on arbitrary local pytest projects.
- Recommended installation command: `python -m pip install -e .`.
- Supports reusable parameterization:
  - `--tests` for one or more files/directories.
  - `--pytest-k` to filter discovered tests.
  - `--mode` and `--metric` for analysis configuration.
  - `--timeout` and `--workers` for execution control.

Shell completion is available through `argcomplete` after installation. A
session-local activation example is:

```bash
eval "$(register-python-argcomplete pwfl)"
```

For containerized reuse, `python docker_pwfl.py middle-cli` runs the canonical
`middle` example with fixed subject/test target and exports
`pwfl_ranking.json` to `docker-output/`.

The Docker `middle-cli` mode exposes reusable tuning for `--mode`, `--metric`,
`--workers`, and optional `--verbose` while keeping default reproducibility
settings stable (fixed output/top/timeout and fixed test target).

## 5) Network/External Access

Initial setup and some experiment stages may fetch subject/project resources
and Python dependencies from remote registries.

## 6) Deviations from Standard Environments

No special kernel modules, privileged execution, custom hardware accelerators,
or non-standard compiler toolchains are required.

The Docker workflow is provided to minimize host-environment drift and improve
reproducibility.

