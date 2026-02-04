import os
import subprocess
from pathlib import Path

SUBJECTS = [
    "ansible_11",
    "ansible_15",
    "ansible_16",
    "black_3",
    "httpie_3",
    "keras_20",
    "keras_34",
    "keras_36",
    "keras_39",
    "keras_4",
    "keras_41",
    "keras_45",
    "luigi_22",
    "luigi_27",
    "luigi_3",
    "luigi_31",
    "luigi_32",
    "matplotlib_10",
    "matplotlib_11",
    "matplotlib_12",
    "matplotlib_15",
    "matplotlib_18",
    "matplotlib_19",
    "matplotlib_20",
    "matplotlib_21",
    "matplotlib_22",
    "matplotlib_23",
    "matplotlib_24",
    "matplotlib_25",
    "matplotlib_26",
    "matplotlib_28",
    "matplotlib_29",
    "matplotlib_30",
    "matplotlib_6",
    "matplotlib_8",
    "matplotlib_9",
    "sanic_4",
    "scrapy_21",
    "scrapy_22",
    "scrapy_27",
    "scrapy_29",
    "spacy_10",
    "spacy_3",
    "spacy_4",
    "spacy_5",
    "thefuck_30",
    "tornado_16",
    "tornado_3",
    "tornado_4",
    "tqdm_3",
    "tqdm_5",
    "tqdm_7",
    "youtubedl_14",
    "youtubedl_2",
    "youtubedl_22",
    "youtubedl_30",
]

analysis_path = Path("analysis")
result_path = Path("results")


def main():
    for subject in SUBJECTS:
        example = analysis_path / f"{subject}_buggy_tcp.json"
        if example.exists():
            print(f"Removing files for {subject}...")
            subprocess.run(
                f"rm {analysis_path / f'{subject}_buggy*_tcp.json'}", shell=True
            )
            subprocess.run(f"rm {result_path / f'{subject}_tcp.json'}", shell=True)


if __name__ == "__main__":
    main()
