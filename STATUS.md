# STATUS

This document declares the artifact badges requested for FSE 2026 and the
rationale for each request.

## Requested Badges

1. **Artifacts Evaluated - Functional**
2. **Artifacts Evaluated - Reusable**
3. **Artifacts Available**

## Rationale

### 1) Artifacts Evaluated - Functional

We request this badge because the artifact is documented and executable with a
clear workflow:

- `README.md` describes the artifact scope and reproducibility steps.
- `INSTALL.md` provides installation and verification instructions.
- `docker_pwfl.py` supports an isolated, repeatable execution path.
- `run_small_eval.py` provides a smoke evaluation to validate end-to-end
  functionality before long runs.

### 2) Artifacts Evaluated - Reusable

We request this badge because the artifact is structured and documented for
reuse and extension:

- Modular implementation under `src/pwfl/` with dedicated pipeline modules.
- Explicit CLI entry points in `evaluation.py` for PWFL, PRFL, and TCP modes.
- A pip-installable reusable command-line tool (`python -m pip install -e .`
  provides `pwfl`) for local pytest projects.
- A reusable local CLI (`pwfl`) for arbitrary pytest projects with configurable
  test scope (`--tests`), test filters (`--pytest-k`), runtime controls
  (`--timeout`, `--workers`), and analysis settings (`--mode`, `--metric`).
- A Docker helper mode (`python docker_pwfl.py middle-cli`) that executes a
  canonical end-to-end CLI run with fixed subject/test target and exports
  `pwfl_ranking.json` for inspection; reusable tuning remains available via
  `--mode`, `--metric`, `--workers`, and optional `--verbose`.
- Reproducibility-oriented documentation (`README.md`, `INSTALL`,
  `REQUIREMENTS.md`) and consistent output directories.

### 3) Artifacts Available

We request this badge conditional on archival publication of the artifact in a
persistent repository.

- Planned archival target: Zenodo.
- DOI/link status: `TBD (to be inserted before final camera-ready packaging)`.

Once the DOI is minted, the `README.md` artifact availability section will be
updated with the final persistent identifier.

