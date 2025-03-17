import json
from pathlib import Path

from sflkit.analysis.spectra import Spectrum
from sflkit.evaluation import Scenario

from pwfl.analyze import distances
from pwfl.logger import LOGGER
from pwfl.summarize import subjects

tex_translation = {
    Spectrum.Tarantula.__name__: "\\TARANTULA{}",
    Spectrum.Ochiai.__name__: "\\OCHIAI{}",
    Spectrum.DStar.__name__: "\\DSTAR{}",
    Spectrum.Naish2.__name__: "\\NAISHTWO{}",
    Spectrum.GP13.__name__: "\\GPTHIRTEEN{}",
    Scenario.BEST_CASE.value: "Best Case Debugging",
    Scenario.WORST_CASE.value: "Worst Case Debugging",
    Scenario.AVG_CASE.value: "Average Case Debugging",
    "exam": "\\EXAM{}",
    "wasted-effort": "W Effort",
    "line": "w/o \\PW{}",
    "line_line": "\\PW{}$_L$",
    "line_defuse": "\\PW{}$_{DU}$",
    "line_defuses": "\\PW{}$_{DUU}$",
    "line_assert_use": "\\PW{}$_{ADU}$",
    "line_assert_uses": "\\PW{}$_{ADUU}$",
    "PRFL": "\\PRFL{}",
    "PRFL_line": "\\PRFL{}$_L$",
    "PRFL_defuse": "\\PRFL{}$_{DU}$",
    "PRFL_defuses": "\\PRFL{}$_{DUU}$",
    "PRFL_assert_use": "\\PRFL{}$_{ADU}$",
    "PRFL_assert_uses": "\\PRFL{}$_{ADUU}$",
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


def get_header_tex_table(metric=True):
    return (
        (
            "\\begin{tabular}{llrrrrrrrrrrrrrrrrrr}\n"
            if metric
            else "\\begin{tabular}{llrrrrrrrrrrrrrrrrr}\n"
        )
        + "    \\toprule\n\\multicolumn{1}{c}{\\multirow{4}*{Distance}} & "
        + ("\\multicolumn{1}{c}{\\multirow{4}*{Metric}} & " if metric else "")
        + (
            "\\multicolumn{6}{c}{Best-Case Debugging} & \\multicolumn{6}{c}{Average-Case Debugging} & "
            "\\multicolumn{6}{c}{Worst-Case Debugging} \\\\"
        )
        + (
            "\\cmidrule(lr){3-8}\\cmidrule(lr){9-14}\\cmidrule(lr){15-20}\n    & "
            if metric
            else "\\cmidrule(lr){2-7}\\cmidrule(lr){8-13}\\cmidrule(lr){14-19}\n    "
        )
        + (
            (
                " & \\multicolumn{4}{c}{Top-k} & \\multicolumn{1}{c}{\\multirow{2}*{\\EXAM{}}} & "
                "\\multicolumn{1}{c}{\\multirow{2}*{Effort}}\n"
            )
            * 3
        )
        + (
            "\\\\\\cmidrule{3-6}\\cmidrule{9-12}\\cmidrule{15-18}\n    &"
            if metric
            else "\\\\\\cmidrule{2-5}\\cmidrule{8-11}\\cmidrule{14-17}\n    "
        )
        + (
            (
                " & \\multicolumn{1}{c}{1} & \\multicolumn{1}{c}{5}"
                " & \\multicolumn{1}{c}{10} & \\multicolumn{1}{c}{200} & &\n"
            )
            * 3
        )
        + "\\\\\\midrule\n"
    )


def get_header_tex_table_without_metric():
    return get_header_tex_table(metric=False)


def get_localization_tex_table(
    results,
    best_for_each_metric,
    line_for_each_metric,
    results_prfl,
    line_for_each_metric_prfl,
):
    table = get_header_tex_table()
    prfl_results = results_prfl["PRFL"]
    order = [
        (distance_order[0], results),
        ("PRFL", results_prfl),
    ] + [(distance, results) for distance in distance_order[1:]]
    for d, dr_pair in enumerate(order):
        distance, result_lookup = dr_pair
        for m, metric in enumerate(metric_order):
            if d % 2 == 1:
                table += "\\rowcolor{row}\n"
            if m == len(metric_order) // 2:
                table += f"    {tex_translation[distance]}"
            else:
                table += "    "
            table += f" & {tex_translation[metric]}"
            if metric == metric_order[0]:
                table += "\\rowstrut{}"
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
                    table += " & "
                    if mark_better_as_lines:
                        table += "\\underline{"
                    if mark_better_as_prfl:
                        table += "\\textbf{"
                    if mark_as_best:
                        table += "{\\color{best}"
                    if localization.startswith("top"):
                        table += (
                            f"{result_lookup[distance][metric][scenario][localization]['avg'] * 100:.1f}"
                            "\\%"
                        )
                    elif localization == "exam":
                        table += f"{result_lookup[distance][metric][scenario][localization]['avg']:.3f}"
                    else:
                        table += (
                            f"{result_lookup[distance][metric][scenario][localization]['avg'] / 1000:.1f}"
                            f"k"
                        )
                    if mark_as_best:
                        table += "}"
                    if mark_better_as_prfl:
                        table += "}"
                    if mark_better_as_lines:
                        table += "}"
            table += " \\\\"
            if m < len(metric_order) - 1:
                table += "\n"
        table += "[.2em]\n"
    table += "\\bottomrule\n\\end{tabular}\n"
    return table


def get_localization_prfl_text_table(
    results_prfl,
    best_for_each_metric_prfl,
    line_for_each_metric_prfl,
):
    table = get_header_tex_table()
    for d, distance in enumerate(distance_prfl_order[1:]):
        for m, metric in enumerate(metric_order):
            if d % 2 == 1:
                table += "\\rowcolor{row}\n"
            if m == len(metric_order) // 2:
                table += f"    {tex_translation[distance]}"
            else:
                table += "    "
            table += f" & {tex_translation[metric]}"
            if metric == metric_order[0]:
                table += "\\rowstrut{}"
            for scenario in scenario_order:
                for localization, comp in zip(localization_order, localization_comp):
                    mark_as_best = (
                        distance
                        in best_for_each_metric_prfl[metric][scenario][localization][0][
                            1
                        ]
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
                    table += " & "
                    if mark_better_as_prfl:
                        table += "\\textbf{"
                    if mark_as_best:
                        table += "{\\color{best}"
                    if localization.startswith("top"):
                        table += (
                            f"{results_prfl[distance][metric][scenario][localization]['avg'] * 100:.1f}"
                            "\\%"
                        )
                    elif localization == "exam":
                        table += f"{results_prfl[distance][metric][scenario][localization]['avg']:.3f}"
                    else:
                        table += (
                            f"{results_prfl[distance][metric][scenario][localization]['avg'] / 1000:.1f}"
                            f"k"
                        )
                    if mark_as_best:
                        table += "}"
                    if mark_better_as_prfl:
                        table += "}"
            table += " \\\\"
            if m < len(metric_order) - 1:
                table += "\n"
        table += "[.2em]\n"
    table += "\\bottomrule\n\\end{tabular}\n"
    return table


def get_improvement_combined_table(improvements, improvements_prfl):
    table = get_header_tex_table_without_metric()
    table += get_improvement_tex_table(improvements, distance_order)
    table += "\\midrule\n"
    table += get_improvement_tex_table(
        improvements_prfl, distance_prfl_order, n=len(distance_order) - 1
    )
    table += "\\bottomrule\n\\end{tabular}\n"
    return table


def get_improvement_tex_table(improvements, order, n=0):
    table = ""
    for d, distance in enumerate(order[1:], start=n):
        if d % 2 == 1:
            table += "\\rowcolor{row}\n"
        table += f"    {tex_translation[distance]}"
        table += "\\rowstrut{}"
        actual_improvement = {
            scenario: {
                localization: [
                    improvement
                    for metric in metric_order
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
                    LOGGER.info(
                        f"Improvement: 0% for {distance} {scenario} {localization}"
                    )
                    no_improvements = {
                        scenario: {
                            localization: [
                                improvement
                                for metric in metric_order
                                for improvement in improvements[distance][metric][
                                    scenario
                                ][localization]
                                if improvement == float("inf") or improvement <= 0
                            ]
                            for localization in localization_order
                        }
                        for scenario in scenario_order
                    }
                    LOGGER.info(f"No improvements for {no_improvements}")
                else:
                    avg_percent = (
                        sum(actual_improvement[scenario][localization])
                        / len(actual_improvement[scenario][localization])
                        - 1
                    ) * 100
                    table += f" & {int(avg_percent)}\\%"
        table += " \\\\"
        if d < len(order) - 1 + n:
            table += "\n"
        table += "[.2em]\n"
    return table


def get_disadvantages_combined_table(improvements, improvements_prfl):
    actual_decrease = {
        distance: {
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
        for distance in distance_order[1:]
    }
    for distance, distance_prfl in zip(distance_order[1:], distance_prfl_order[1:]):
        for scenario in scenario_order:
            for localization in localization_order:
                for metric in metric_order:
                    for improvement in improvements_prfl[distance_prfl][metric][
                        scenario
                    ][localization]:
                        if 0 < improvement < 1:
                            actual_decrease[distance][scenario][localization].append(
                                improvement
                            )
    table = get_header_tex_table_without_metric()
    table += get_disadvantages_tex_table(actual_decrease, distance_order)
    table += "\\bottomrule\n\\end{tabular}\n"
    return table


def get_disadvantages_tex_table(actual_decrease, order, n=0):
    table = ""
    for d, distance in enumerate(order[1:], start=n):
        if d % 2 == 1:
            table += "\\rowcolor{row}\n"
        table += f"    {tex_translation[distance]}"
        table += "\\rowstrut{}"
        for scenario in scenario_order:
            for localization in localization_order:
                avg_percent = (
                    sum(actual_decrease[distance][scenario][localization])
                    / len(actual_decrease[distance][scenario][localization])
                    - 1
                ) * 100
                table += f" & ${int(avg_percent)}\\%$"
        table += " \\\\"
        if d < len(order) - 1 + n:
            table += "\n"
        table += "[.2em]\n"
    return table


def get_overhead_tex_table(overhead, average_times):
    table = (
        "\\begin{tabular}{l"
        + (">{\\raggedleft\\arraybackslash}p{1.35cm}" * (len(distance_order) - 1))
        + "}\n"
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
    table += (
        "    \\rowcolor{row} Test\\rowstrut{} & \\multicolumn{5}{c}{"
        f"{test_overhead:.2f}"
        "\\%} \\\\\n"
    )

    for stage in [
        "Analyze",
        "Suggest",
        "Overall",
    ]:
        if stage == "Suggest":
            table += "   \\rowcolor{row}"
        elif stage == "Overall":
            table += "    \\midrule\n    "
        else:
            table += "    "
        table += f"{stage}"
        if stage != "Overall":
            table += "\\rowstrut{}"
        for distance in distance_order[1:]:
            table += " & "
            overheads = overhead[distance][stage.lower()]
            avg_overhead = (sum(overheads) / len(overheads) - 1) * 100
            table += f"{avg_overhead:.2f}\\%"
        table += " \\\\\n"
    table += "    \\rowcolor{row}Avg Time\\rowstrut{}"
    for distance in distance_order[1:]:
        table += " & "
        table += f"{average_times[distance]:.1f}s"
    table += " \\\\\n"
    table += "\\bottomrule\n\\end{tabular}\n"
    return table


def write_tex(
    results,
    results_prfl,
    best_for_each_metric,
    best_for_each_metric_prfl,
    line_for_each_metric,
    line_for_each_metric_prfl,
    improvements,
    improvements_prfl,
    overhead,
    average_times,
):
    tex_output = Path("tex")
    if not tex_output.exists():
        tex_output.mkdir()
    localization_table = get_localization_tex_table(
        results,
        best_for_each_metric,
        line_for_each_metric,
        results_prfl,
        line_for_each_metric_prfl,
    )
    with Path(tex_output, "localization.tex").open("w") as f:
        f.write(localization_table)
    localization_prfl_table = get_localization_prfl_text_table(
        results_prfl,
        best_for_each_metric_prfl,
        line_for_each_metric_prfl,
    )
    with Path(tex_output, "localization-prfl.tex").open("w") as f:
        f.write(localization_prfl_table)
    improvement_table = get_improvement_combined_table(improvements, improvements_prfl)
    with Path(tex_output, "improvement.tex").open("w") as f:
        f.write(improvement_table)
    disadvantage_table = get_disadvantages_combined_table(
        improvements, improvements_prfl
    )
    with Path(tex_output, "disadvantage.tex").open("w") as f:
        f.write(disadvantage_table)
    times_table = get_overhead_tex_table(overhead, average_times)
    with Path(tex_output, "times.tex").open("w") as f:
        f.write(times_table)


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
                            elif comp:
                                if line_result > 0:
                                    improvements[distance][metric][scenario][
                                        localization
                                    ].append(distance_result / line_result)
                                else:
                                    improvements[distance][metric][scenario][
                                        localization
                                    ].append(float("inf"))
                            else:
                                if distance_result > 0:
                                    improvements[distance][metric][scenario][
                                        localization
                                    ].append(line_result / distance_result)
                                else:
                                    improvements[distance][metric][scenario][
                                        localization
                                    ].append(float("inf"))
                    if avg in bests:
                        bests[avg].append(distance)
                    else:
                        bests[avg] = [distance]
                bests = sorted([(score, bests[score]) for score in bests], reverse=comp)
                best_for_each_metric[metric][scenario][localization] = bests
    return (
        best_for_each_metric,
        line_for_each_metric,
        improvements,
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
    average_times = {distance: [] for distance in distance_order[1:]}
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
                for metric in metric_order:
                    overhead[distance]["suggest"].append(
                        run_times[project]["suggest"][distance][metric]
                        / run_times[project]["suggest"]["line"][metric]
                    )
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
                    average_times[distance].append(
                        (
                            run_times[project]["test"]
                            + run_times[project]["analysis"][distance]
                            + run_times[project]["suggest"][distance][metric]
                        )
                    )
    average_times = {
        distance: sum(average_times[distance]) / len(average_times[distance])
        for distance in distance_order[1:]
    }
    return run_times, overhead, average_times


def interpret(tex=False):
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
    ) = analyze(results)
    (
        best_for_each_metric_prfl,
        line_for_each_metric_prfl,
        improvements_prfl,
    ) = analyze(results_prfl, prfl=True)

    runtimes, overhead, average_times = get_times()
    if tex:
        write_tex(
            results,
            results_prfl,
            best_for_each_metric,
            best_for_each_metric_prfl,
            line_for_each_metric,
            line_for_each_metric_prfl,
            improvements,
            improvements_prfl,
            overhead,
            average_times,
        )
