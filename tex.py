import json
from pathlib import Path

from sflkit.analysis.spectra import Spectrum
from sflkit.evaluation import Scenario

from get_analysis import distances
from get_summary import subjects

tex_translation = {
    Spectrum.Tarantula.__name__: "\\TARANTULA{}",
    Spectrum.Ochiai.__name__: "\\OCHIAI{}",
    Spectrum.DStar.__name__: "\\DSTAR{}",
    Scenario.BEST_CASE.value: "Best Case Debugging",
    Scenario.WORST_CASE.value: "Worst Case Debugging",
    Scenario.AVG_CASE.value: "Average Case Debugging",
    "exam": "\\EXAM{}",
    "wasted-effort": "W Effort",
    "line": "w/o \\TW{}",
    "line_line": "\\TW{}$_L$",
    "line_defuse": "\\TW{}$_{DU}$",
    "line_defuses": "\\TW{}$_{DUU}$",
    "line_assert_use": "\\TW{}$_{ADU}$",
    "line_assert_uses": "\\TW{}$_{ADUU}$",
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

localization_order = [
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
    False,
    False,
]


def get_localization_tex_table(results, best_for_each_metric, line_for_each_metric):
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
        for metric in metric_order:
            if metric == metric_order[0]:
                table += f"    \\multirow{3}*{{{tex_translation[distance]}}}"
            else:
                table += "    "
            table += f" & {tex_translation[metric]}"
            for scenario in scenario_order:
                for localization, comp in zip(localization_order, localization_comp):
                    text_underline = (
                        distance
                        in best_for_each_metric[metric][scenario][localization][0][1]
                    )
                    text_bf = (
                        (
                            results[distance][metric][scenario][localization]["avg"]
                            > line_for_each_metric[metric][scenario][localization]
                        )
                        if comp
                        else (
                            results[distance][metric][scenario][localization]["avg"]
                            < line_for_each_metric[metric][scenario][localization]
                        )
                    )
                    table += " & "
                    if text_underline:
                        table += "\\underline{"
                    if text_bf:
                        table += "\\textbf{"
                    if localization.startswith("top"):
                        table += (
                            f"{results[distance][metric][scenario][localization]['avg'] * 100:.1f}"
                            "\\%"
                        )
                    elif localization == "exam":
                        table += f"{results[distance][metric][scenario][localization]['avg']:.3f}"
                    else:
                        table += (
                            f"{results[distance][metric][scenario][localization]['avg'] / 1000:.1f}"
                            f"k"
                        )
                    if text_bf:
                        table += "}"
                    if text_underline:
                        table += "}"
            table += " \\\\\n"
        if distance != distance_order[-1]:
            table += "\\addlinespace[0.6em]\n"

    table += "\\bottomrule\n\\end{tabular}\n"
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
    improvements,
    total_improvements,
    overhead,
):
    tex_output = Path("tex")
    if not tex_output.exists():
        tex_output.mkdir()
    localization_table = get_localization_tex_table(
        results, best_for_each_metric, line_for_each_metric
    )
    with Path(tex_output, "localization.tex").open("w") as f:
        f.write(localization_table)
    found_table = get_found_tex_table(results)
    with Path(tex_output, "found.tex").open("w") as f:
        f.write(found_table)
    improvement_table = get_improvement_tex_table(improvements, total_improvements)
    with Path(tex_output, "improvement.tex").open("w") as f:
        f.write(improvement_table)
    disadvantage_table = get_disadvantages_tex_table(improvements, total_improvements)
    with Path(tex_output, "disadvantage.tex").open("w") as f:
        f.write(disadvantage_table)
    times_table = get_overhead_tex_table(overhead)
    with Path(tex_output, "times.tex").open("w") as f:
        f.write(times_table)


def analyze(results):
    """analyze bests for the various metrics and report highest p-value"""
    line_for_each_metric = dict()
    best_for_each_metric = dict()
    improvements = {
        distance: {
            m: {s: {lo: list() for lo in localization_order} for s in scenario_order}
            for m in metric_order
        }
        for distance in distance_order[1:]
    }
    total_improvements = {
        distance: {
            m: {s: {lo: list() for lo in localization_order} for s in scenario_order}
            for m in metric_order
        }
        for distance in distance_order[1:]
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
                for distance in distance_order:
                    avg = results[distance][metric][scenario][localization]["avg"]
                    if distance == "line":
                        line_for_each_metric[metric][scenario][localization] = avg
                    else:
                        for distance_result, line_result, subject in zip(
                            results[distance][metric][scenario][localization]["all"],
                            results["line"][metric][scenario][localization]["all"],
                            results["subjects"],
                        ):
                            if comp:
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
    if not summary.exists():
        return
    with summary.open() as f:
        results = json.load(f)
    (
        best_for_each_metric,
        line_for_each_metric,
        improvements,
        total_improvements,
    ) = analyze(results)

    _, overhead = get_times()
    if tex:
        write_tex(
            results,
            best_for_each_metric,
            line_for_each_metric,
            improvements,
            total_improvements,
            overhead,
        )


if __name__ == "__main__":
    main(tex=True)
