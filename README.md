# Proximity-Weighted Fault Localization

## Abstract

When a program fails, statistical fault localization (SFL) provides important debugging hints by identifying the 
locations whose execution most correlates with failures.
However, such correlations can be significantly weakened if a test contains both _passing_ and _failing_ assertions, 
creating ambiguous and misleading associations.
Likewise, if multiple lines correlate with failure with the same strength, SFL provides little guidance to disambiguate 
between them.
    
This paper proposes a novel proximity-based weighting scheme for SFL that assigns different _weights_ to code locations 
in the test subject based on temporal proximity to failure.
The more recently a subject line is executed before the test fails, the higher its weight.
We operationalize a well-known debugging heuristic into a lightweight statistical form compatible with existing SFL 
formulas.
Our approach applies to _any test_, from simple single-line tests (where it preserves traditional SFL behavior), to 
single-assertion tests with multiple setup lines (where it benefits from temporal proximity), to complex 
multi-assertion tests (where it provides the most benefit by distinguishing failing from passing assertions).
Once computed, proximity weights can be integrated into any existing SFL technique.
    
Our evaluation of proximity-weighted fault localization on 310~real-world programs shows that it consistently 
outperforms fault localization techniques across all test types.
Proximity-weighted fault localization shows per-subject relative improvements of 200%-400%, meaning that, for a 
typical subject, it provides 3 to 5 times the baseline effectiveness.
These improvements represent substantial gains over baseline techniques.
Our approach can be integrated into existing fault localization techniques to improve performance, making it a valuable 
addition to automated debugging.

## Structure

## Setup

We leverage SFLKit to collect the event data for the subjects. SFLKit is a tool that instruments the subject
programs to collect the event data. The event data is a sequence of events that occur during the execution of the 
subject.

We have modified SFLKit to collect the execution features for the subjects. The modified version of SFLKit is available
in the `sflkit` directory. 

As subjects of our evaluation, we leverage [Tests4Py](https://github.com/smythi93/Tests4Py).

Additionally, we have implemented multiple scripts to run the experiments and analyze the results.

## Docker

If you prefer an isolated environment, you can build a single image that embeds
the repository files needed for the notebook and evaluation workflows. The
container does not rely on a host bind mount, so it runs independently of your
local Python environment.

Build the image:

```bash
docker build -t pwfl .
```

Open an interactive shell with the project already available inside the image:

```bash
docker run -it pwfl
```

Because the image is self-contained, avoid ``--rm`` when you want to inspect the
generated files afterwards. If you remove the container on exit, the evaluation
artifacts disappear with it.

Run the notebook example and expose Jupyter on port 8888:

```bash
docker run --rm -it \
  -p 8888:8888 \
  pwfl \
  jupyter lab --ip=0.0.0.0 --port=8888 --no-browser --allow-root \
  --ServerApp.token='' --ServerApp.password='' --notebook-dir=/workspace
```

Run the reduced evaluation driver and copy the outputs back to the host:

```bash
python docker_pwfl.py small-eval
```

This command keeps a persistent helper container alive, copies the generated
`small_eval/` directory into `docker-output/<timestamp>/`, and prints the shell
command you can use to inspect the container afterwards. It only builds the
image when missing.

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
python evaluation.py events -p black -i 1
python evaluation.py analyze -p black -i 1
python evaluation.py evaluate -p black -i 1
```

If you need to persist generated artifacts such as `results/`, `reports/`, or
`analysis/`, copy them out of the container after the run or use the helper
script to export the evaluation directory automatically.

### Installing Requirements

To install the requirements, run the following command:

```bash
python setup.py
```

We recommend using a virtual environment to install the requirements. To create a virtual environment, run the following command:

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

If you want to check out how proximity-weighted fault localization works, we recommend checking out the example in `example.ipynb`.

## Reproducing our Results

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

So the collected events and mapping of the `black` project and bug one will be stored in `sflkit_events/black/1/bug` for 
the buggy version, `sflkit_events/black/1/fix` for the fixed version, and `mappings/black_1.json` for the mapping.

Remove the `reports/report_<project_name>.json` file if you want to collect the event data from scratch.

***

***THEFUCK_17:*** We ran into a particular case for the subject `thefuck_17`. We were able to reproduce the fault, but only under MacOS. If you want to reproduce all our results, we recommend running this subject under MacOS.

### Analyzing the Collected Events

Next, you need to analyze the collected events by running:

```bash
python evaluation.py analyze -p <project_name> [-i <bug_id>]
```

The analyzed events, i.e., the information to calculate the suspiciousness scores, including the weight, will get stored in the `analysis` directory.

### Evaluating the Correlation and Fault Localization

To evaluate the correlation and fault localization, run the following command:

```bash
python evaluation.py evaluate -p <project_name> [-i <bug_id>]
```

The results of the correlation and fault localization will be stored in the `results` directory for each subject 
individually as a JSON file with the name `<project_name>_<bug_id>.json`.

If you want to evaluate the correlation and fault localization from scratch, you need to remove the corresponding 
files in the `results` directory.

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

During the collection of events the script will produce the mappings of the purified test cases in `tcp_mappings/<project_name>_<bug_id>.json`.
During the analysis of the collected events, the script will produce the purified spectra in `tcp_spectra/<project_name>_<bug_id>.json`.
These files are used during the evaluation of the fault localization to calculate the refined suspiciousness scores for the purified test cases.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
