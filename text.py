import json
from pathlib import Path

from prettytable import PrettyTable
from sflkit.analysis.spectra import Spectrum
from sflkit.evaluation import Scenario

from get_analysis import distances
from get_summary import subjects

text_translation = {
    Spectrum.Tarantula.__name__: "TARANTULA",
    Spectrum.Ochiai.__name__: "OCHIAI",
    Spectrum.DStar.__name__: "D*",
    Spectrum.Naish1.__name__: "NAISH1",
    Spectrum.Naish2.__name__: "NAISH2",
    Spectrum.GP13.__name__: "GP13",
    Scenario.BEST_CASE.value: "Best Case Debugging",
    Scenario.WORST_CASE.value: "Worst Case Debugging",
    Scenario.AVG_CASE.value: "Average Case Debugging",
    "exam": "EXAM",
    "wasted-effort": "W Effort",
    "line": "w/o TW",
    "line_line": "TW_L",
    "line_defuse": "TW_DU",
    "line_defuses": "TW_DUU",
    "line_assert_use": "TW_ADU",
    "line_assert_uses": "TW_ADUU",
    "PRFL": "PRFL",
    "PRFL_line": "PRFL_L",
    "PRFL_defuse": "PRFL_DU",
    "PRFL_defuses": "PRFL_DUU",
    "PRFL_assert_use": "PRFL_ADU",
    "PRFL_assert_uses": "PRFL_ADUU",
}


scenario_order = [
    Scenario.BEST_CASE.value,
    Scenario.AVG_CASE.value,
    Scenario.WORST_CASE.value,
]

metric_order = [
    Spectrum.Tarantula.__name__,
    Spectrum.Ochiai.__name__,
    Spectrum.DStar.__name__,
    Spectrum.Naish1.__name__,
    Spectrum.Naish2.__name__,
    Spectrum.GP13.__name__,
]

distance_order = [f"line{suffix}" for suffix, _ in distances]
distance_prfl_order = [f"PRFL{suffix}" for suffix, _ in distances]

localization_order = [
    "top-1",
    "top-5",
    "top-10",
    "top-200",
    "exam",
    "wasted-effort",
]

localization_comp = [
    True,
    True,
    True,
    True,
    False,
    False,
]

HEADER = [
    "Approach",
    "Metric",
    "BC Top-1",
    "BC Top-5",
    "BC Top-10",
    "BC Top-200",
    "BC Exam",
    "BC Effort",
    "AC Top-1",
    "AC Top-5",
    "AC Top-10",
    "AC Top-200",
    "AC Exam",
    "AC Effort",
    "WC Top-1",
    "WC Top-5",
    "WC Top-10",
    "WC Top-200",
    "WC Exam",
    "WC Effort",
]


def get_localization_text_table(
    results,
    best_for_each_metric,
    line_for_each_metric,
    results_prfl,
    line_for_each_metric_prfl,
):
    table = PrettyTable()
    table.field_names = HEADER
    prfl_results = results_prfl["PRFL_line"]
    for distance, result_lookup in [
        (distance_order[0], results),
        (distance_prfl_order[0], results_prfl),
    ] + [(distance, results) for distance in distance_order[1:]]:
        for metric in metric_order:
            row = []
            if metric == metric_order[0]:
                row.append(text_translation[distance])
            else:
                row.append("")
            row.append(text_translation[metric])
            for scenario in scenario_order:
                for localization, comp in zip(localization_order, localization_comp):
                    if distance == distance_prfl_order[0]:
                        if comp:
                            mark_as_best = (
                                result_lookup[distance][metric][scenario][localization][
                                    "avg"
                                ]
                                >= best_for_each_metric[metric][scenario][localization][
                                    0
                                ][0]
                            )
                        else:
                            mark_as_best = (
                                result_lookup[distance][metric][scenario][localization][
                                    "avg"
                                ]
                                <= best_for_each_metric[metric][scenario][localization][
                                    0
                                ][0]
                            )
                    else:
                        mark_as_best = (
                            distance
                            in best_for_each_metric[metric][scenario][localization][0][
                                1
                            ]
                        )
                        if mark_as_best:
                            if comp:
                                mark_as_best = (
                                    result_lookup[distance][metric][scenario][
                                        localization
                                    ]["avg"]
                                    >= prfl_results[metric][scenario][localization][
                                        "avg"
                                    ]
                                )
                            else:
                                mark_as_best = (
                                    result_lookup[distance][metric][scenario][
                                        localization
                                    ]["avg"]
                                    <= prfl_results[metric][scenario][localization][
                                        "avg"
                                    ]
                                )
                    if comp:
                        mark_better_as_lines = (
                            result_lookup[distance][metric][scenario][localization][
                                "avg"
                            ]
                            > line_for_each_metric[metric][scenario][localization]
                        )
                        mark_better_as_prfl = (
                            result_lookup[distance][metric][scenario][localization][
                                "avg"
                            ]
                            > line_for_each_metric_prfl[metric][scenario][localization]
                        )
                    else:
                        mark_better_as_lines = (
                            result_lookup[distance][metric][scenario][localization][
                                "avg"
                            ]
                            < line_for_each_metric[metric][scenario][localization]
                        )
                        mark_better_as_prfl = (
                            result_lookup[distance][metric][scenario][localization][
                                "avg"
                            ]
                            < line_for_each_metric_prfl[metric][scenario][localization]
                        )

                    if mark_as_best:
                        row.append(
                            f"+ {result_lookup[distance][metric][scenario][localization]['avg']:.2f}"
                        )
                    elif mark_better_as_lines and mark_better_as_prfl:
                        row.append(
                            f"* {result_lookup[distance][metric][scenario][localization]['avg']:.2f}"
                        )
                    elif mark_better_as_lines:
                        row.append(
                            f"# {result_lookup[distance][metric][scenario][localization]['avg']:.2f}"
                        )
                    elif mark_better_as_prfl:
                        row.append(
                            f"$ {result_lookup[distance][metric][scenario][localization]['avg']:.2f}"
                        )
                    else:
                        row.append(
                            f"  {result_lookup[distance][metric][scenario][localization]['avg']:.2f}"
                        )
            table.add_row(row)
    return table


def get_localization_prfl_text_table(
    results_prfl,
    best_for_each_metric_prfl,
    line_for_each_metric_prfl,
):
    table = PrettyTable()
    table.field_names = HEADER
    for distance in distance_prfl_order:
        for metric in metric_order:
            row = []
            if metric == metric_order[0]:
                row.append(text_translation[distance])
            else:
                row.append("")
            row.append(text_translation[metric])
            for scenario in scenario_order:
                for localization, comp in zip(localization_order, localization_comp):
                    if distance == distance_prfl_order[0]:
                        mark_as_best = (
                            distance
                            in best_for_each_metric_prfl[metric][scenario][
                                localization
                            ][0][1]
                        )
                    if comp:
                        mark_better_as_prfl = (
                            results_prfl[distance][metric][scenario][localization][
                                "avg"
                            ]
                            > line_for_each_metric_prfl[metric][scenario][localization]
                        )
                    else:
                        mark_better_as_prfl = (
                            results_prfl[distance][metric][scenario][localization][
                                "avg"
                            ]
                            < line_for_each_metric_prfl[metric][scenario][localization]
                        )

                    if mark_as_best:
                        row.append(
                            f"+ {results_prfl[distance][metric][scenario][localization]['avg']:.2f}"
                        )
                    elif mark_better_as_prfl:
                        row.append(
                            f"$ {results_prfl[distance][metric][scenario][localization]['avg']:.2f}"
                        )
                    else:
                        row.append(
                            f"  {results_prfl[distance][metric][scenario][localization]['avg']:.2f}"
                        )
            table.add_row(row)
    return table


def get_found_tex_table(results):
    table = (
        "\\begin{tabular}{llrrrrrrrrrrrrrrr}\n"
        "    \\toprule\n"
        "    \\multicolumn{1}{c}{\\multirow{4}*{Approach}} & \\multicolumn{1}{c}{\\multirow{4}*{Metric}} & "
        "\\multicolumn{5}{c}{Best-Case Debugging} & \\multicolumn{5}{c}{Average-Case Debugging} & "
        "\\multicolumn{5}{c}{Worst-Case Debugging} \\\\\\cmidrule(lr){3-7}\\cmidrule(lr){8-12}\\cmidrule(lr){13-17}\n"
        "    &"
        + (
            (
                " & \\multicolumn{3}{c}{Top-k} & \\multicolumn{1}{c}{\\multirow{2}*{\\EXAM{}}} & "
                "\\multicolumn{1}{c}{\\multirow{2}*{Effort}}\n"
            )
            * 3
        )
        + "\\\\\\cmidrule{3-5}\\cmidrule{8-10}\\cmidrule{13-15}\n    &"
        + (
            (
                " & \\multicolumn{1}{c}{5} & \\multicolumn{1}{c}{10} & \\multicolumn{1}{c}{200} & &\n"
            )
            * 3
        )
        + "\\\\\\midrule\n"
    )
    for distance in distance_order:
        table += f"    \\multirow{{3}}*{{{tex_translation[distance]}}}"
        for metric in metric_order:
            table += f" & {tex_translation[metric]}"
            for scenario in scenario_order:
                for localization in localization_order:
                    found = len(
                        [
                            result
                            for result in results[distance][metric][scenario][
                                localization
                            ]["all"]
                            if (result > 0 and localization.startswith("top"))
                            or (result < 1 and localization == "exam")
                            or localization == "wasted-effort"
                        ]
                    )
                    table += f" & {found}"
            table += " \\\\\n"
        if distance != distance_order[-1]:
            table += "\\addlinespace[0.6em]\n"

    table += "\\bottomrule\n\\end{tabular}\n"
    return table


def get_improvement_tex_table(improvements, total_improvements):
    table = (
        "\\begin{tabular}{llrrrrrrrrrrrrrrr}\n"
        "    \\toprule\n"
        "    \\multicolumn{1}{c}{\\multirow{4}*{Approach}} & \\multicolumn{1}{c}{\\multirow{4}*{}} & "
        "\\multicolumn{5}{c}{Best-Case Debugging} & \\multicolumn{5}{c}{Average-Case Debugging} & "
        "\\multicolumn{5}{c}{Worst-Case Debugging} \\\\\\cmidrule(lr){3-7}\\cmidrule(lr){8-12}\\cmidrule(lr){13-17}\n"
        "    &"
        + (
            (
                " & \\multicolumn{3}{c}{Top-k} & \\multicolumn{1}{c}{\\multirow{2}*{\\EXAM{}}} & "
                "\\multicolumn{1}{c}{\\multirow{2}*{Effort}}\n"
            )
            * 3
        )
        + "\\\\\\cmidrule{3-5}\\cmidrule{8-10}\\cmidrule{13-15}\n    &"
        + (
            (
                " & \\multicolumn{1}{c}{5} & \\multicolumn{1}{c}{10} & \\multicolumn{1}{c}{200} & &\n"
            )
            * 3
        )
        + "\\\\\\midrule\n"
    )
    for distance in distance_order[1:]:
        for metric in metric_order:
            if metric == metric_order[0]:
                table += f"    \\multirow{{3}}*{{{tex_translation[distance]}}}"
            table += f" & {tex_translation[metric]}"
            actual_improvement = {
                scenario: {
                    localization: [
                        improvement
                        for improvement in improvements[distance][metric][scenario][
                            localization
                        ]
                        if improvement != float("inf") and improvement > 0
                    ]
                    for localization in localization_order
                }
                for scenario in scenario_order
            }
            for scenario in scenario_order:
                for localization in localization_order:
                    if len(actual_improvement[scenario][localization]) == 0:
                        table += " & 0\\%"
                        print(
                            f"Improvement: 0% for {distance} {metric} {scenario} {localization}"
                        )
                        no_improvements = {
                            scenario: {
                                localization: [
                                    improvement
                                    for improvement in improvements[distance][metric][
                                        scenario
                                    ][localization]
                                    if improvement == float("inf") or improvement <= 0
                                ]
                                for localization in localization_order
                            }
                            for scenario in scenario_order
                        }
                        print(no_improvements)
                    else:
                        avg_percent = (
                            sum(actual_improvement[scenario][localization])
                            / len(actual_improvement[scenario][localization])
                            - 1
                        ) * 100
                        table += f" & {int(avg_percent)}\\%"
            table += " \\\\\n"
        if distance != distance_order[-1]:
            table += "\\addlinespace[0.6em]\n"

    table += "\\bottomrule\n\\end{tabular}\n"
    return table


def get_disadvantages_tex_table(improvements, total_improvements):
    table = (
        "\\begin{tabular}{llrrrrrrrrrrrrrrr}\n"
        "    \\toprule\n"
        "    \\multicolumn{1}{c}{\\multirow{4}*{Approach}} & "
        "\\multicolumn{5}{c}{Best-Case Debugging} & \\multicolumn{5}{c}{Average-Case Debugging} & "
        "\\multicolumn{5}{c}{Worst-Case Debugging} \\\\\\cmidrule(lr){2-6}\\cmidrule(lr){7-11}\\cmidrule(lr){12-16}\n"
        "  "
        + (
            (
                "& \\multicolumn{3}{c}{Top-k} & \\multicolumn{1}{c}{\\multirow{2}*{\\EXAM{}}} & "
                "\\multicolumn{1}{c}{\\multirow{2}*{Effort}}\n"
            )
            * 3
        )
        + "\\\\\\cmidrule{2-4}\\cmidrule{7-9}\\cmidrule{12-14}\n   "
        + (
            (
                " & \\multicolumn{1}{c}{5} & \\multicolumn{1}{c}{10} & \\multicolumn{1}{c}{200} & &\n"
            )
            * 3
        )
        + "\\\\\\midrule\n"
    )
    for distance in distance_order[1:]:
        table += f"    {tex_translation[distance]}"
        actual_decrease = {
            scenario: {
                localization: [
                    improvement
                    for metric in metric_order
                    for improvement in improvements[distance][metric][scenario][
                        localization
                    ]
                    if 0 < improvement < 1
                ]
                for localization in localization_order
            }
            for scenario in scenario_order
        }
        for scenario in scenario_order:
            for localization in localization_order:
                avg_percent = (
                    sum(actual_decrease[scenario][localization])
                    / len(actual_decrease[scenario][localization])
                    - 1
                ) * 100
                table += f" & ${int(avg_percent)}\\%$"
        table += " \\\\\n"
        if distance != distance_order[-1]:
            table += "\\addlinespace[0.6em]\n"

    table += "\\bottomrule\n\\end{tabular}\n"
    return table


def get_overhead_tex_table(overhead):
    table = (
        "\\begin{tabular}{lrrrrr}\n"
        "    \\toprule\n"
        "    Stage & "
        + " & ".join(
            [
                f"\\multicolumn{{1}}{{c}}{{{tex_translation[distance]}}}"
                for distance in distance_order[1:]
            ]
        )
        + "\\\\\\midrule\n"
    )
    # Somehow the instrument overhead is negative, because lines get tested first, so dependencies are already
    # downloaded, which saves time so we ignore it
    # instrument_overhead = (
    #    sum(overhead["instrument"]) / len(overhead["instrument"]) - 1
    # ) * 100
    test_overhead = (sum(overhead["test"]) / len(overhead["test"]) - 1) * 100
    # table += (
    #    "    Instrument & \\multicolumn{5}{c}{"
    #    f"{instrument_overhead:.2f}"
    #    "\\%} \\\\\n"
    # )
    table += "    Test & \\multicolumn{5}{c}{" f"{test_overhead:.2f}" "\\%} \\\\\n"

    for stage in [
        "Analyze",
        "Suggest",
        "Overall",
    ]:
        if stage == "Overall":
            table += "    \\midrule\n"
        table += f"    {stage}"
        for distance in distance_order[1:]:
            table += " & "
            overheads = overhead[distance][stage.lower()]
            avg_overhead = (sum(overheads) / len(overheads) - 1) * 100
            table += f"{avg_overhead:.2f}\\%"
        table += " \\\\\n"
    table += "\\bottomrule\n\\end{tabular}\n"
    return table


def write_tex(
    results,
    best_for_each_metric,
    line_for_each_metric,
    results_prfl,
    best_for_each_metric_prfl,
    line_for_each_metric_prfl,
):
    text_output = Path("text")
    if not text_output.exists():
        text_output.mkdir()
    localization_table: PrettyTable = get_localization_text_table(
        results,
        best_for_each_metric,
        line_for_each_metric,
        results_prfl,
        line_for_each_metric_prfl,
    )
    with Path(text_output, "localization.txt").open("w") as f:
        f.write(localization_table.get_string())
    localization_prfl_table: PrettyTable = get_localization_prfl_text_table(
        results_prfl,
        best_for_each_metric_prfl,
        line_for_each_metric_prfl,
    )
    with Path(text_output, "localization_prfl.txt").open("w") as f:
        f.write(localization_prfl_table.get_string())

    # found_table = get_found_tex_table(results)
    # with Path(tex_output, "found.tex").open("w") as f:
    #    f.write(found_table)
    # improvement_table = get_improvement_tex_table(improvements, total_improvements)
    # with Path(tex_output, "improvement.tex").open("w") as f:
    #    f.write(improvement_table)
    # disadvantage_table = get_disadvantages_tex_table(improvements, total_improvements)
    # with Path(tex_output, "disadvantage.tex").open("w") as f:
    #    f.write(disadvantage_table)
    # times_table = get_overhead_tex_table(overhead)
    # with Path(tex_output, "times.tex").open("w") as f:
    #    f.write(times_table)


def analyze(results, prfl=False):
    """analyze bests for the various metrics and report highest p-value"""
    line_for_each_metric = dict()
    best_for_each_metric = dict()
    improvements = {
        distance: {
            m: {s: {lo: list() for lo in localization_order} for s in scenario_order}
            for m in metric_order
        }
        for distance in (distance_prfl_order[1:] if prfl else distance_order[1:])
    }
    total_improvements = {
        distance: {
            m: {s: {lo: list() for lo in localization_order} for s in scenario_order}
            for m in metric_order
        }
        for distance in (distance_prfl_order[1:] if prfl else distance_order[1:])
    }
    failed = set()
    for metric in metric_order:
        line_for_each_metric[metric] = dict()
        best_for_each_metric[metric] = dict()
        for scenario in scenario_order:
            best_for_each_metric[metric][scenario] = dict()
            line_for_each_metric[metric][scenario] = dict()
            for localization, comp in zip(localization_order, localization_comp):
                bests = dict()
                for distance in distance_prfl_order if prfl else distance_order:
                    avg = results[distance][metric][scenario][localization]["avg"]
                    if distance == "PRFL" if prfl else distance == "line":
                        line_for_each_metric[metric][scenario][localization] = avg
                    else:
                        for distance_result, line_result, subject in zip(
                            results[distance][metric][scenario][localization]["all"],
                            results["PRFL" if prfl else "line"][metric][scenario][
                                localization
                            ]["all"],
                            results["subjects"],
                        ):
                            if line_result == distance_result:
                                improvements[distance][metric][scenario][
                                    localization
                                ].append(1)
                                total_improvements[distance][metric][scenario][
                                    localization
                                ].append(0)
                            elif comp:
                                if line_result > 0:
                                    improvements[distance][metric][scenario][
                                        localization
                                    ].append(distance_result / line_result)
                                else:
                                    improvements[distance][metric][scenario][
                                        localization
                                    ].append(float("inf"))
                                total_improvements[distance][metric][scenario][
                                    localization
                                ].append(distance_result - line_result)
                            else:
                                if distance_result > 0:
                                    improvements[distance][metric][scenario][
                                        localization
                                    ].append(line_result / distance_result)
                                else:
                                    improvements[distance][metric][scenario][
                                        localization
                                    ].append(float("inf"))
                                total_improvements[distance][metric][scenario][
                                    localization
                                ].append(line_result - distance_result)
                            if (
                                improvements[distance][metric][scenario][localization][
                                    -1
                                ]
                                == 0
                            ):
                                failed.add(subject)
                    if avg in bests:
                        bests[avg].append(distance)
                    else:
                        bests[avg] = [distance]
                bests = sorted([(score, bests[score]) for score in bests], reverse=comp)
                best_for_each_metric[metric][scenario][localization] = bests
    print("\n".join(sorted(failed)))
    return (
        best_for_each_metric,
        line_for_each_metric,
        improvements,
        total_improvements,
    )


def get_times():
    run_times = dict()
    overhead = {
        "instrument": [],
        "test": [],
        **{
            distance: {
                "analyze": [],
                "suggest": [],
                "overall": [],
            }
            for distance in distance_order[1:]
        },
    }
    for subject in subjects:
        report = Path("reports", f"report_{subject}.json")
        analysis = Path("reports", f"analysis_{subject}.json")
        suggestion = Path("reports", f"suggestion_{subject}.json")
        if not report.exists() or not analysis.exists() or not suggestion.exists():
            continue
        with report.open() as f:
            report_data = json.load(f)
        with analysis.open() as f:
            analysis_data = json.load(f)
        with suggestion.open() as f:
            suggestion_data = json.load(f)
        for project in report_data:
            if report_data[project]["status"] != "running":
                continue
            run_times[project] = {
                "instrument_lines": report_data[project]["time"]["instrument_lines"],
                "instrument": report_data[project]["time"]["instrument"],
                "test_lines": report_data[project]["time"]["test_lines"],
                "test": report_data[project]["time"]["test"],
                "analysis": {
                    distance: analysis_data[project][mistake]
                    for distance, mistake in zip(
                        distance_order,
                        [
                            "lines",
                            "lines_line",
                            "lines_defuse",
                            "lines_defuses",
                            "lines_assert_use",
                            "lines_assert_uses",
                        ],
                    )
                },
                "suggest": {
                    distance: {
                        metric: suggestion_data[project][distance][metric]
                        for metric in metric_order
                    }
                    for distance in distance_order
                },
            }
            overhead["instrument"].append(
                run_times[project]["instrument"]
                / run_times[project]["instrument_lines"]
            )
            overhead["test"].append(
                run_times[project]["test"] / run_times[project]["test_lines"]
            )
            for distance in distance_order[1:]:
                overhead[distance]["analyze"].append(
                    run_times[project]["analysis"][distance]
                    / run_times[project]["analysis"]["line"]
                )
                overhead[distance]["suggest"].extend(
                    [
                        run_times[project]["suggest"][distance][metric]
                        / run_times[project]["suggest"]["line"][metric]
                        for metric in metric_order
                    ]
                )
                for metric in metric_order:
                    overhead[distance]["overall"].append(
                        (
                            run_times[project]["test"]
                            + run_times[project]["analysis"][distance]
                            + run_times[project]["suggest"][distance][metric]
                        )
                        / (
                            run_times[project]["test_lines"]
                            + run_times[project]["analysis"]["line"]
                            + run_times[project]["suggest"]["line"][metric]
                        )
                    )
    return run_times, overhead


def main(tex=False):
    summary = Path("summary.json")
    summary_prfl = Path("summary_prfl.json", prfl=True)
    if not summary.exists() or not summary_prfl.exists():
        return
    with summary.open() as f:
        results = json.load(f)
    with summary_prfl.open() as f:
        results_prfl = json.load(f)
    (
        best_for_each_metric,
        line_for_each_metric,
        improvements,
        total_improvements,
    ) = analyze(results)
    (
        best_for_each_metric_prfl,
        line_for_each_metric_prfl,
        improvements_prfl,
        total_improvements_prfl,
    ) = analyze(results_prfl, prfl=True)

    runtimes, overhead = get_times()
    if tex:
        write_tex(
            results,
            best_for_each_metric,
            line_for_each_metric,
            results_prfl,
            best_for_each_metric_prfl,
            line_for_each_metric_prfl,
        )


if __name__ == "__main__":
    main(tex=True)
