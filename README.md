# Proximity-Weighted Fault Localization

## Abstract

When a program fails, statistical fault localization (SFL) provides important debugging hints by identifying the program locations whose execution most correlates with failures.
However, such correlations can be significantly weakened if a test contains passing and failing assertions, creating ambiguous and misleading associations.
Likewise, if multiple lines correlate with failure with the same strength, SFL provides little orientation to disambiguate between these lines.
   
This paper proposes a novel approach that assigns different _weights_ to code locations in the test subject:
The more recently a subject line is executed before the test fails, the higher its weight.
This way, code executed last before a failing assertion gets a higher weight than earlier (passing) assertions or test setup code.
Once computed, the weight of lines can be integrated into any SFL metric.
   
Our evaluation of proximity-weighted fault localization on 310 real-world programs shows that it vastly outperforms traditional and state-of-the-art fault localization techniques.
On average, per test subject, proximity-weighted fault localization ranks faulty lines higher by between 200% and 300%, _reducing the effort to find faulty locations by a factor of three to four_.
Our approach can be easily integrated into existing fault localization techniques to improve performance, making it a valuable addition to automated debugging.

## Setup

We leverage SFLKit to collect the event data for the subjects. SFLKit is a tool that instruments the subject
programs to collect the event data. The event data is a sequence of events that occur during the execution of the 
subject.

We have modified SFLKit to collect the execution features for the subjects. The modified version of SFLKit is available
in the `sflkit` directory. 

As subjects of our evaluation, we leverage [Tests4Py](https://github.com/smythi93/Tests4Py).

Additionally, we have implemented multiple scripts to run the experiments and analyze the results.

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
python evaluation.py events -p <project_name> [-b <bug_id>]
```

For instance, to collect the event data for bug 1 of the project `black`, run the following command:

```bash
python evaluation.py events -p black -b 1
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
