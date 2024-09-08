import json
from pathlib import Path

from sflkit.analysis.spectra import Spectrum
from sflkit.evaluation import Scenario

from get_analysis import dependencies

subjects = [
    "ansible",
    "black",
    "calculator",
    "cookiecutter",
    "expression",
    "fastapi",
    "httpie",
    "keras",
    "luigi",
    "markup",
    "matplotlib",
    "middle",
    "pandas",
    "pysnooper",
    "sanic",
    "scrapy",
    "spacy",
    "thefuck",
    "tornado",
    "tqdm",
    "youtubedl",
]

metrics = [
    Spectrum.Tarantula.__name__,
    Spectrum.Ochiai.__name__,
    Spectrum.DStar.__name__,
]

dependency_types = [f"line{suffix}" for suffix, _ in dependencies]
scenarios = [scenario.value for scenario in Scenario]

localizations = ["top-5", "top-10", "top-200", "exam", "wasted-effort"]


def main():
    results_dir = Path("results")
    if not results_dir.exists():
        return
    results = {
        dependency: {
            metric: {
                scenario: {m: {"avg": 0.0, "all": list()} for m in localizations}
                for scenario in scenarios
            }
            for metric in metrics
        }
        for dependency in dependency_types
    }
    number_of_subjects = 0
    for subject in subjects:
        for i in range(100):
            subject_results = results_dir / f"{subject}_{i}.json"
            print(subject)
            if not subject_results.exists():
                continue
            with subject_results.open() as f:
                subject_data = json.load(f)
            for s in subject_data:
                number_of_subjects += 1
                for dependency in dependency_types:
                    for m in metrics:
                        for sce in scenarios:
                            for loc in localizations:
                                results[dependency][m][sce][loc]["all"].append(
                                    subject_data[s][dependency][m][sce][loc]
                                )

    for dependency in dependency_types:
        for m in metrics:
            for sce in scenarios:
                for loc in localizations:
                    results[dependency][m][sce][loc]["avg"] = (
                        sum(results[dependency][m][sce][loc]["all"])
                        / number_of_subjects
                    )
    with open("summary.json", "w") as f:
        json.dump(results, f, indent=1)


if __name__ == "__main__":
    main()
