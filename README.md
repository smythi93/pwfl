# Proximity-Weighted Fault Localization

## Abstract

When a program fails, statistical fault localization (SFL) provides important debugging hints by identifying the locations whose execution most correlates with failures.
However, such correlations can be weakened if a test contains both _passing_ and _failing_ assertions, creating ambiguous and misleading associations.
Likewise, if multiple lines correlate with the same strength, SFL provides little guidance to disambiguate between them.
    
This paper proposes a novel proximity-based weighting scheme for SFL that assigns different _weights_ to locations in the test subject based on temporal proximity to a failure.
The more recently a subject line is executed before the test fails, the higher its weight.
We operationalize a known heuristic into a lightweight statistical form compatible with existing SFL formulas.
Our approach applies to _any test_, from simple single-line tests (where it preserves SFL behavior), to single-assertion tests with multiple lines (where it benefits from temporal proximity), to complex multi-assertion tests (where it provides the most benefit by distinguishing failing from passing assertions).
Once computed, the weights can be integrated into any existing SFL technique.
    
Our evaluation of proximity-weighted fault localization on 310~real-world programs shows that it consistently outperforms fault localization techniques across all test types.
Proximity-weighted fault localization shows per-subject relative improvements of 200%–400%, meaning that, for a typical subject, it provides 3 to 5 times the baseline effectiveness.
These improvements represent substantial gains over baseline techniques.
Our approach can be integrated into existing fault localization techniques to improve performance, making it a valuable addition to automated debugging.

## Structure

The repository is organized around the evaluation scripts, the Docker helper,
and the generated analysis artifacts:

```text
pwfl/
├── docker_pwfl.py          # Self-contained Docker entrypoint for the workflow
├── Dockerfile              # Image definition used by docker_pwfl.py
├── evaluation.py           # Main evaluation, analysis, and summary driver
├── run_small_eval.py       # Reduced evaluation used for quick checks
├── example.ipynb           # Notebook walkthrough of the approach
├── pyproject.toml          # Project metadata and Python dependencies
├── src/                    # Installable package code
│   └── pwfl/               # Proximity-weighted fault localization implementation
│       ├── analyze.py      # Analyzer / spectra construction
│       ├── cg.py           # Get event and build call graph for PRFL
│       ├── check.py        # Verify the correctness of the collected events and mappings
│       ├── evaluate.py     # Fault localization scoring
│       ├── events.py       # Event collection pipeline
│       ├── interpret.py    # Interpret the results and output latex tables
│       ├── logger.py       # Logging utilities
│       ├── prfl.py         # PRFL implementation and evaluation
│       ├── purification.py # Test case purification integration using the pyurify library
│       ├── summarize.py    # Aggregate result summaries
│       ├── tests.py        # Motivation-study statistics and plots
│       └── utils.py        # Utility functions for file handling, data manipulation, etc.
├── reports/                # Per-project run metadata and suggestions
├── results/                # Per-subject final FL outputs
├── sflkit_events/          # Collected runtime events
├── mappings/               # Event-to-location mappings
├── tcp_mappings/           # Purification mappings
├── tcp_spectra/            # Purification spectra
├── call_graphs/            # PRFL call graph artifacts
└── docker-output/          # Exported outputs from docker_pwfl.py
```

## Artifact Availability and Provenance

This artifact provides the PWFL implementation, evaluation scripts, and
generated-study data artifacts used in the paper.

- **Source repository**: this project repository.
- **Persistent archival link (for FSE Available badge)**: `TBD (Zenodo DOI to be inserted)`.
- **Primary data provenance**: execution traces and derived analysis outputs are
  produced by this codebase from Tests4Py subjects via `tests4py`, `sflkit`,
  and `pyurify`.
- **Generated data directories**: `sflkit_events/`, `mappings/`,
  `tcp_mappings/`, `tcp_spectra/`, `call_graphs/`, `reports/`, `results/`, and
  `docker-output/`.
- **Ethical and legal statement**: the artifact operates on open-source subject
  projects and generates program-execution metadata; it is not designed to
  process personal/sensitive user data.

Storage demand depends on run scope: smoke runs are small, while full
reproduction across all subjects and variants can generate multiple GB of
intermediate and result artifacts.

## Setup

We leverage SFLKit 0.5.7 to collect the event data for the subjects. PWFL is
included in that release, so the workflow uses the upstream implementation to
instrument the subject programs and record the execution events.

The collected event data is a sequence of events that occur during the
execution of the subject.

As subjects of our evaluation, we leverage [Tests4Py](https://github.com/smythi93/Tests4Py).

Additionally, we have implemented multiple scripts to run the experiments and analyze the results.

## Docker

If you prefer an isolated environment, you can build a single image that embeds
the repository files needed for the notebook and evaluation workflows. The
container does not rely on a host bind mount, so it runs independently of your
local Python environment.

The two quickest entrypoints are the following commands:

- `python docker_pwfl.py example` — build/run the notebook image and open the example automatically.
- `python docker_pwfl.py small-eval --tiny` — run a fast smoke test of the reduced evaluation.
- `python docker_pwfl.py middle-cli` — run the local PWFL CLI on the `middle` example and export `pwfl_ranking.json`.

Build the image:

```bash
python docker_pwfl.py build
```

Open an interactive shell with the project already available inside the image:

```bash
python docker_pwfl.py shell
```

Because the image is self-contained, the helper keeps a persistent container
alive for evaluation runs so the generated files remain available afterward.
If you want a fresh image build, pass `--build` to the selected helper command.
For a cache-bypassing rebuild, run `python docker_pwfl.py build --no-cache`
before the workflow command.

Run the notebook example and expose Jupyter on port 8888:

```bash
python docker_pwfl.py example
```

This command starts JupyterLab inside the container and opens the notebook
automatically. Use `--no-open` if you want to skip launching the browser.

Run the reduced evaluation driver and copy the outputs back to the host:

```bash
python docker_pwfl.py small-eval
```

This command keeps a persistent helper container alive, copies the generated
`small_eval/` directory into `docker-output/<timestamp>/`, and prints the shell
command you can use to inspect the container afterward. It only builds the
image when missing.

For a quick smoke test that still exercises the full pipeline, use:

```bash
python docker_pwfl.py small-eval --tiny
```

The smoke run is intended as a fast verification pass. Depending on your
machine, it usually finishes in a few minutes (< 5 minutes).

To run the reusable local CLI workflow inside Docker on the bundled `middle`
example, use:

```bash
python docker_pwfl.py middle-cli
```

This executes `pwfl middle -t tests.py -s tarantula` in the container and
copies `pwfl_ranking.json` into `docker-output/<timestamp>/`.

The Docker helper keeps this mode reproducible by fixing the subject (`middle`),
test target (`tests.py`), output filename (`pwfl_ranking.json`), top-k (200),
and timeout (120), while allowing reusable tuning via `--mode`, `--metric`,
`--workers`, and optional `--verbose`.

For example, you can switch the analysis mode and worker count with this command:

```bash
python docker_pwfl.py middle-cli --mode def-use --metric tarantula --workers 8
```

For full reproduction over all subjects and variants (PWFL + PRFL + TCP),
expect a long-running workload that can take multiple days.

If you want to rebuild explicitly, pass:

```bash
python docker_pwfl.py small-eval --build
```

You can also open a shell directly with:

```bash
python docker_pwfl.py shell
```

To force a rebuild before opening the shell:

```bash
python docker_pwfl.py shell --build
```

From the interactive shell, you can run the full pipeline manually, for example:

```bash
python evaluation.py events \
    -p black -i 1
python evaluation.py analyze \
    -p black -i 1
python evaluation.py evaluate \
    -p black -i 1
```

If you need to persist generated artifacts such as `results/`, `reports/`, or
`analysis/`, copy them out of the container after the run or use the helper
script to export the evaluation directory automatically.

### Installing Requirements

To install the requirements, run the following command:

```bash
python -m pip install --upgrade pip
python -m pip install -e .
```

This editable pip installation is the recommended reusable setup because it
installs the `pwfl` CLI entrypoint and keeps local source changes immediately
available during experimentation.

If you prefer a plain requirements-file installation, use:

```bash
python -m pip install -r requirements.txt
```

We recommend using a virtual environment. To create one, run the following
command:

```bash
python -m venv .venv
```

To activate the virtual environment, run the following command:
```bash
. .venv/bin/activate
```
or
```bash
source .venv/bin/activate
```

## Example

If you want to check out how proximity-weighted fault localization works, we
recommend checking out the example in `example.ipynb` or simply running:

```bash
python docker_pwfl.py example
```

The helper opens the notebook automatically by default, so this is the most
direct way to explore the workflow in an isolated environment.

## Local Project CLI

You can also run PWFL directly on a local pytest project and produce a ranked
JSON file of suspicious lines:

```bash
pwfl /path/to/your/project -o ranking.json
```

This command discovers pytest tests, classifies tests as passing/failing,
collects per-test executed lines, computes Ochiai suspiciousness, and writes a
developer-oriented ranking to `pwfl_ranking.json` by default.

The CLI uses SFLKit instrumentation. By default it runs in `line` mode. You can
switch to proximity-aware modes with `--mode`:

```bash
pwfl /path/to/your/project --mode def-use -o local_ranking.json
```

You can pass one or more explicit test targets (files and/or directories):

```bash
pwfl /path/to/your/project -t tests/unit tests/integration/test_api.py
```

Reusable knobs for different projects include:

- `-t/--tests` for one or more test paths.
- `-k/--pytest-k` to filter discovered tests.
- `--timeout` and `-w/--workers` to tune execution resources.
- `-m/--mode` and `-s/--metric` to switch analysis and ranking behavior.
- `--work-dir` and `--keep-workdir` for debugging/inspection workflows.

Test files are still instrumented for test events, but test-source lines are
excluded from the final ranked output to keep the ranking actionable for
subject code.

Shell completion is supported for `pwfl` via `argcomplete`. After installing
with pip, you can enable completion in your current shell session using:

```bash
eval "$(register-python-argcomplete pwfl)"
```

## Reproducing our Results

To make the workflow explicit, reproduce results in this order:

1. Collect baseline events.
2. Build analyzers.
3. Evaluate baseline PWFL.
4. Summarize baseline results.
5. Run PRFL extension (`cg` + `prfl`) and summarize.
6. Run TCP extension (`tcp`) and summarize.

### Subject List

The full study currently uses the following subjects:

`ansible`, `black`, `calculator`, `cookiecutter`, `expression`, `fastapi`,
`httpie`, `keras`, `luigi`, `markup`, `matplotlib`, `middle`, `pandas`,
`pysnooper`, `sanic`, `scrapy`, `spacy`, `thefuck`, `tornado`, `tqdm`,
`youtubedl`.

For a smoke run, use `python docker_pwfl.py small-eval --tiny`, which evaluates
only a very small subset to validate the pipeline and verify that (1) the project is functional as expected, 
and (2) the results are reproducible. The smoke run is intended as a fast verification pass, so it only evaluates a 
few subjects and variants, and it usually finishes in a few minutes (< 5 minutes) depending on your machine.

### Collecting The Event Data

To collect the event data, run the following command:

```bash
python evaluation.py events -p <project_name> [-i <bug_id>]
```

For instance, to collect the event data for bug 1 of the project `black`, run the following command:

```bash
python evaluation.py events -p black -i 1
```

The collected event data will be stored in the `sflkit_events` directory.
Additionally, this script maps all possible events for the subjects and stores them in 
`mappings/<project_name>_<bug_id>.json`.

So the collected events and mapping of the `black` project and bug one will be
stored in `sflkit_events/black/1/bug` for the buggy version,
`sflkit_events/black/1/fix` for the fixed version, and `mappings/black_1.json`
for the mapping.

Remove the `reports/report_<project_name>.json` file if you want to collect the event data from scratch.

***

***THEFUCK_17:*** We ran into a particular case for the subject `thefuck_17`.
We were able to reproduce the fault, but only under macOS. If you want to
reproduce all our results, we recommend running this subject under macOS.

### Analyzing the Collected Events

Next, you need to analyze the collected events by running:

```bash
python evaluation.py analyze -p <project_name> [-i <bug_id>]
```

The analyzed events, i.e., the information to calculate the
suspiciousness scores, including the weight, will get stored in the
`analysis` directory.

### Evaluating the Correlation and Fault Localization

To evaluate the correlation and fault localization, run the following command:

```bash
python evaluation.py evaluate \
    -p <project_name> [-i <bug_id>]
```

The results of the correlation and fault localization will be stored in the
`results` directory for each subject individually as a JSON file with the
name `<project_name>_<bug_id>.json`.

If you want to evaluate the correlation and fault localization from scratch,
you need to remove the corresponding files in the `results` directory.

To summarize the results of all subjects, run the following command:

```bash
python evaluation.py summarize
```

The summarized results will be stored in a file called `summary.json`.

### Reproducing the Results for PRFL

To reproduce the results for PRFL, run the following steps:

```bash
python evaluation.py cg events -p <project_name> [-i <bug_id>]
python evaluation.py cg build -p <project_name> [-i <bug_id>]
python evaluation.py prfl build -p <project_name> [-i <bug_id>]
python evaluation.py prfl evaluate -p <project_name> [-i <bug_id>]
python evaluation.py summarize-prfl
```

### Reproducing the Results for test case purification

To reproduce the results for test case purification, run the following steps:

```bash
python evaluation.py tcp events -p <project_name> [-i <bug_id>]
python evaluation.py tcp analyze -p <project_name> [-i <bug_id>]
python evaluation.py tcp evaluate -p <project_name> [-i <bug_id>]
python evaluation.py summarize-tcp
```

During the collection of events the script will produce the mappings of the
purified test cases in `tcp_mappings/<project_name>_<bug_id>.json`.
During the analysis of the collected events, the script will produce the
purified spectra in `tcp_spectra/<project_name>_<bug_id>.json`.
These files are used during the evaluation of the fault localization to
calculate the refined suspiciousness scores for the purified test cases.

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.
