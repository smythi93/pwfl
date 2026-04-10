# INSTALL

This file describes how to install and verify the PWFL artifact.

## Option A: Local Python Environment

### 1) Create and activate a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
```

### 2) Install dependencies and package

```bash
python -m pip install --upgrade pip
python -m pip install -e .
```

This pip-based editable installation is the recommended reusable setup because
it installs the `pwfl` executable while keeping local source edits active.

### 3) Basic installation check

```bash
python evaluation.py --help
python run_small_eval.py --tiny
pwfl --help
pwfl middle -t tests.py -v -s tarantula
```

Expected outcome:

- The first command prints CLI help with subcommands such as `events`,
  `analyze`, `evaluate`, `cg`, `prfl`, and `tcp`.
- The second command executes a reduced pipeline and writes outputs under
  `small_eval/` (including summary JSON files).
- The `pwfl` commands print local CLI help and produce `pwfl_ranking.json` for
  the `middle` example.

To enable shell completion for `pwfl` in the current session, run:

```bash
eval "$(register-python-argcomplete pwfl)"
```

## Option B: Docker (Recommended for Reproducibility)

### 1) Build image

```bash
python docker_pwfl.py build
```

### 2) Run smoke evaluation

```bash
python docker_pwfl.py small-eval --tiny
```

Expected outcome:

- A persistent helper container is started (or reused).
- Reduced evaluation runs successfully.
- Results are copied to `docker-output/<timestamp>/small_eval/`.

### 3) Run the reusable local CLI example in Docker

```bash
python docker_pwfl.py middle-cli
```

Expected outcome:

- The container runs the canonical `middle` CLI workflow with fixed
  `-t tests.py` and exports `pwfl_ranking.json`.
- `pwfl_ranking.json` is copied to `docker-output/<timestamp>/`.

Optional reusable tuning is available via `middle-cli` flags:
`--mode`, `--metric`, `--workers`, and optional `--verbose`.

Example:

```bash
python docker_pwfl.py middle-cli --mode def-use --metric tarantula --workers 8
```

### 4) Optional: open notebook example

```bash
python docker_pwfl.py example
```

Expected outcome:

- JupyterLab starts on port 8888.
- The example notebook opens automatically (unless `--no-open` is passed).

## Full Reproduction Note

The full experiment across all subjects and variants (PWFL + PRFL + TCP) is
expected to run for multiple days. Use the smoke run first to validate the
installation and workflow on your machine.

## Troubleshooting

- If dependencies fail to install, verify Python version is 3.10+.
- If Docker workflows do not reflect source updates, rebuild with:

```bash
python docker_pwfl.py build --no-cache
```

- If needed, inspect the container state with:

```bash
python docker_pwfl.py shell
```

