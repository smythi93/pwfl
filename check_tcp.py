import json
from pathlib import Path


def main():
    mappings_path = Path(__file__).parent / "tcp_mappings"
    reports_path = Path(__file__).parent / "reports"
    errors = []
    for subject in mappings_path.iterdir():
        subject_name = subject.stem.split("_")[0]
        if subject.is_file() and subject.suffix == ".json":
            with open(subject, "r") as f:
                data = json.load(f)
            if data == {}:
                errors.append(subject.stem)
                print(f"Subject {subject.stem} has no TCP mappings.")
                with open(reports_path / f"tcp_{subject_name}.json", "r") as f:
                    report_data = json.load(f)
                if subject.stem in report_data:
                    report_data[subject.stem]["status"] = "error"
                    with open(reports_path / f"tcp_{subject_name}.json", "w") as f:
                        json.dump(report_data, f, indent=1)

    if errors:
        print("Subjects with errors:")
        for error in sorted(errors):
            print(f"- {error}")


if __name__ == "__main__":
    main()
