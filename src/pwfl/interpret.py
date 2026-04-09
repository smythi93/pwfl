"""
Interpret summarized PWFL results and generate publication tables.

This module transforms ``summary*.json`` artifacts into comparative statistics
and LaTeX tables for baseline, PRFL, and TCP variants.
"""

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
    "wasted-effort": "WE",
    "line": "w/o \\PW{}",
    "line_line": "\\PW{}$_L$",
    "line_defuse": "\\PW{}$_{DU}$",
    "line_defuses": "\\PW{}$_{DUU}$",
    "line_assert_use": "\\PW{}$_{A_{DU}}$",
    "line_assert_uses": "\\PW{}$_{A_{DUU}}$",
    "PRFL": "\\PRFL{}",
    "PRFL_line": "\\PRFL{}$_L$",
    "PRFL_defuse": "\\PRFL{}$_{DU}$",
    "PRFL_defuses": "\\PRFL{}$_{DUU}$",
    "PRFL_assert_use": "\\PRFL{}$_{A_{DU}}$",
    "PRFL_assert_uses": "\\PRFL{}$_{A_{DUU}}$",
    "TCP": "\\TCP{}",
    "TCP_line": "\\TCP{}$_L$",
    "TCP_defuse": "\\TCP{}$_{DU}$",
    "TCP_defuses": "\\TCP{}$_{DUU}$",
    "TCP_assert_use": "\\TCP{}$_{A_{DU}}$",
    "TCP_assert_uses": "\\TCP{}$_{A_{DUU}}$",
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
distance_tcp_order = [f"TCP{suffix}" for suffix, _ in distances]

localization_order = [
    "top-1",
    "top-5",
    "top-10",
    #    "top-200",
    "exam",
    "wasted-effort",
]

localization_comp = [
    True,
    True,
    True,
    # True,
    False,
    False,
]


def get_header_tex_table(metric=True):
    """
    Build a LaTeX tabular header for localization result tables.

    :param metric: Include metric column when ``True``.
    :type metric: bool
    :returns: LaTeX header string.
    :rtype: str
    """
    columns_per_scenario = len(localization_order)
    start = 3 if metric else 2
    return (
        (
            f"\\begin{{tabular}}{{l{'l' if metric else ''}{'r' * columns_per_scenario * len(scenario_order)}}}\n"
        )
        + "    \\toprule\n\\multicolumn{1}{c}{\\multirow{4}*{Distance}} & "
        + ("\\multicolumn{1}{c}{\\multirow{4}*{Metric}} & " if metric else "")
        + (
            f"\\multicolumn{{{columns_per_scenario}}}{{c}}{{Best-Case Debugging}} & "
            f"\\multicolumn{{{columns_per_scenario}}}{{c}}{{Average-Case Debugging}} & "
            f"\\multicolumn{{{columns_per_scenario}}}{{c}}{{Worst-Case Debugging}} \\\\"
        )
        + "".join(
            [
                f"\\cmidrule(lr){{{start + i * columns_per_scenario}-{start + (i + 1) * columns_per_scenario - 1}}}"
                for i in range(3)
            ]
        )
        + "\n    "
        + ("&" if metric else "")
        + (
            (
                " & \\multicolumn{3}{c}{Top-k} & \\multicolumn{1}{c}{\\multirow{2}*{\\EXAM{}}}"
                " & \\multicolumn{1}{c}{\\multirow{2}*{WE}}\n"
            )
            * 3
        )
        + "\\\\"
        + "".join(
            [
                f"\\cmidrule{{{start + i * columns_per_scenario}-{start + i * columns_per_scenario + 2}}}"
                for i in range(3)
            ]
        )
        + "\n    "
        + ("&" if metric else "")
        + (
            (
                " & \\multicolumn{1}{c}{1} & \\multicolumn{1}{c}{5}"
                " & \\multicolumn{1}{c}{10} &"
                " &"
                "\n"
            )
            * 3
        )
        + "\\\\\\midrule\n"
    )


def get_header_tex_table_without_metric():
    """
    Build table header variant without a metric column.

    :returns: LaTeX header string.
    :rtype: str
    """
    return get_header_tex_table(metric=False)


def get_baseline_tex_table(
    results,
    results_prfl,
    results_tcp,
):
    """
    Create a baseline comparison table across line/PRFL/TCP families.

    :returns: Rendered LaTeX table.
    :rtype: str
    """
    table = get_header_tex_table()
    order = [
        (distance_order[0], results),
        ("PRFL", results_prfl),
        ("TCP", results_tcp),
    ]
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
                    table += " & "
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
            table += " \\\\"
            if m < len(metric_order) - 1:
                table += "\n"
        table += "[.2em]\n"
    table += "\\bottomrule\n\\end{tabular}\n"
    return table


def get_localization_tex_table(
    order,
    best_for_each_metric,
    line_for_each_metric,
):
    """
    Render a localization table for a given dependency family order.

    :returns: Rendered LaTeX table.
    :rtype: str
    """
    table = get_header_tex_table()
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
                    mark_as_best = (
                        distance
                        in best_for_each_metric[metric][scenario][localization][0][1]
                    )
                    # For top-k metrics larger is better, but for EXAM/WE lower is better.
                    if comp:
                        mark_better_as_lines = (
                            result_lookup[distance][metric][scenario][localization][
                                "avg"
                            ]
                            > line_for_each_metric[metric][scenario][localization]
                        )
                    else:
                        mark_better_as_lines = (
                            result_lookup[distance][metric][scenario][localization][
                                "avg"
                            ]
                            < line_for_each_metric[metric][scenario][localization]
                        )
                    table += " & "
                    if mark_better_as_lines:
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
                    if mark_better_as_lines:
                        table += "}"
            table += " \\\\"
            if m < len(metric_order) - 1:
                table += "\n"
        table += "[.2em]\n"
    table += "\\bottomrule\n\\end{tabular}\n"
    return table


def get_improvement_combined_table(improvements, improvements_prfl, improvements_tcp):
    """
    Build a combined improvement table for baseline, PRFL, and TCP.

    :returns: Rendered LaTeX table.
    :rtype: str
    """
    table = get_header_tex_table_without_metric()
    table += get_improvement_tex_table(improvements, distance_order)
    table += "\\midrule\n"
    table += get_improvement_tex_table(
        improvements_prfl, distance_prfl_order, n=len(distance_order) - 1
    )
    table += "\\midrule\n"
    table += get_improvement_tex_table(
        improvements_tcp,
        distance_tcp_order,
        n=len(distance_order) + len(distance_prfl_order) - 2,
    )
    table += "\\bottomrule\n\\end{tabular}\n"
    return table


def get_improvement_tex_table(improvements, order, n=0):
    """
    Render improvement percentages for one dependency family.

    :param improvements: Improvement ratios keyed by metric/scenario/localization.
    :param order: Display order for distances.
    :param n: Row offset used for alternating row colors across concatenated tables.
    :returns: LaTeX body rows.
    :rtype: str
    """
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
                # Ignore non-positive or infinite ratios for average improvement output.
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


def get_disadvantages_combined_table(
    improvements, improvements_prfl, improvements_tcp, subs
):
    """
    Build a combined table for cases where variants underperform baseline.

    :returns: Rendered LaTeX table.
    :rtype: str
    """
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
    for distance, distance_tcp in zip(distance_order[1:], distance_tcp_order[1:]):
        for scenario in scenario_order:
            for localization in localization_order:
                for metric in metric_order:
                    for improvement in improvements_tcp[distance_tcp][metric][scenario][
                        localization
                    ]:
                        if 0 < improvement < 1:
                            actual_decrease[distance][scenario][localization].append(
                                improvement
                            )
    number_of_decreases = 0
    total_comparisons = 0
    decreased_subjects = {}
    for distance in distance_order[1:]:
        for scenario in scenario_order:
            for metric in metric_order:
                total_comparisons += 310
                for i in range(310):
                    if all(
                        [
                            improvements[distance][metric][scenario][localization][i]
                            < 1
                            for localization in localization_order
                        ]
                    ):
                        number_of_decreases += 1
                        decreased_subjects[subs[i]] = (
                            decreased_subjects.get(subs[i], 0) + 1
                        )
    LOGGER.info(f"Number of decreases: {number_of_decreases}")
    LOGGER.info(f"Total: {total_comparisons}")
    LOGGER.info(
        f"Percentage of decreases: {number_of_decreases / total_comparisons * 100:.2f}%"
    )
    for s in sorted(decreased_subjects):
        LOGGER.info(f"Decreased subject: {s} - {decreased_subjects[s]} decreases")
    table = get_header_tex_table_without_metric()
    table += get_disadvantages_tex_table(actual_decrease, distance_order)
    table += "\\bottomrule\n\\end{tabular}\n"
    return table


def get_disadvantages_tex_table(actual_decrease, order, n=0):
    """
    Render LaTeX rows for decrease percentages.

    :returns: LaTeX body rows.
    :rtype: str
    """
    table = ""
    for d, distance in enumerate(order[1:], start=n):
        if d % 2 == 1:
            table += "\\rowcolor{row}\n"
        table += f"    {tex_translation[distance]}"
        table += "\\rowstrut{}"
        for scenario in scenario_order:
            for localization in localization_order:
                # noinspection PyUnresolvedReferences
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
    """
    Render runtime overhead table for non-baseline distances.

    :param overhead: Relative overhead ratios from :func:`get_times`.
    :param average_times: Absolute average times in seconds.
    :returns: Rendered LaTeX table.
    :rtype: str
    """
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
    # test_overhead = (sum(overhead["test"]) / len(overhead["test"]) - 1) * 100
    # table += (
    #    "    Instrument & \\multicolumn{5}{c}{"
    #    f"{instrument_overhead:.2f}"
    #    "\\%} \\\\\n"
    # )
    # table += (
    #     "    \\rowcolor{row} Test\\rowstrut{} & \\multicolumn{5}{c}{"
    #     f"{test_overhead:.2f}"
    #     "\\%} \\\\\n"
    # )

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
        if stage == "Suggest":
            table += "\\rowstrut{}"
        for distance in distance_order[1:]:
            table += " & "
            overheads = overhead[distance][stage.lower()]
            # noinspection PyUnresolvedReferences
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
    results_tcp,
    best_for_each_metric,
    best_for_each_metric_prfl,
    best_for_each_metric_tcp,
    line_for_each_metric,
    line_for_each_metric_prfl,
    line_for_each_metric_tcp,
    improvements,
    improvements_prfl,
    improvements_tcp,
    overhead,
    average_times,
    subs,
):
    """
    Write all generated LaTeX tables to the ``tex/`` directory.

    :returns: None
    """
    tex_output = Path("tex")
    if not tex_output.exists():
        tex_output.mkdir()
    baseline_table = get_baseline_tex_table(results, results_prfl, results_tcp)
    with Path(tex_output, "baseline.tex").open("w") as f:
        f.write(baseline_table)
    localization_table = get_localization_tex_table(
        [(distance, results) for distance in distance_order[1:]],
        best_for_each_metric,
        line_for_each_metric,
    )
    with Path(tex_output, "localization.tex").open("w") as f:
        f.write(localization_table)
    localization_prfl_table = get_localization_tex_table(
        [(distance, results_prfl) for distance in distance_prfl_order[1:]],
        best_for_each_metric_prfl,
        line_for_each_metric_prfl,
    )
    with Path(tex_output, "localization-prfl.tex").open("w") as f:
        f.write(localization_prfl_table)
    localization_tcp_table = get_localization_tex_table(
        [(distance, results_tcp) for distance in distance_tcp_order[1:]],
        best_for_each_metric_tcp,
        line_for_each_metric_tcp,
    )
    with Path(tex_output, "localization-tcp.tex").open("w") as f:
        f.write(localization_tcp_table)
    improvement_table = get_improvement_combined_table(
        improvements, improvements_prfl, improvements_tcp
    )
    with Path(tex_output, "improvement.tex").open("w") as f:
        f.write(improvement_table)
    disadvantage_table = get_disadvantages_combined_table(
        improvements, improvements_prfl, improvements_tcp, subs
    )
    with Path(tex_output, "disadvantage.tex").open("w") as f:
        f.write(disadvantage_table)
    times_table = get_overhead_tex_table(overhead, average_times)
    with Path(tex_output, "times.tex").open("w") as f:
        f.write(times_table)


def analyze(results, prfl=False, tcp=False):
    """
    Analyze summary results and derive best-score/improvement structures.

    :param results: Parsed summary JSON object.
    :param prfl: Interpret ``results`` as PRFL summary layout.
    :param tcp: Interpret ``results`` as TCP summary layout.
    :returns: Tuple ``(best_by_metric, line_baseline, improvements, subjects)``.
    :rtype: tuple[dict, dict, dict, list[str]]
    """
    line_for_each_metric = dict()
    best_for_each_metric = dict()
    improvements = {
        distance: {
            m: {s: {lo: list() for lo in localization_order} for s in scenario_order}
            for m in metric_order
        }
        for distance in (
            distance_prfl_order[1:]
            if prfl
            else distance_tcp_order[1:] if tcp else distance_order[1:]
        )
    }
    for metric in metric_order:
        line_for_each_metric[metric] = dict()
        best_for_each_metric[metric] = dict()
        for scenario in scenario_order:
            best_for_each_metric[metric][scenario] = dict()
            line_for_each_metric[metric][scenario] = dict()
            for localization, comp in zip(localization_order, localization_comp):
                bests = dict()
                for distance in (
                    distance_prfl_order
                    if prfl
                    else distance_tcp_order if tcp else distance_order
                ):
                    avg = results[distance][metric][scenario][localization]["avg"]
                    if (
                        distance == "PRFL"
                        if prfl
                        else distance == "TCP" if tcp else distance == "line"
                    ):
                        line_for_each_metric[metric][scenario][localization] = avg
                    else:
                        for distance_result, line_result, subject in zip(
                            results[distance][metric][scenario][localization]["all"],
                            results["PRFL" if prfl else "TCP" if tcp else "line"][
                                metric
                            ][scenario][localization]["all"],
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
        results["subjects"],
    )


def get_times():
    """
    Collect runtime breakdown and overhead ratios from report files.

    :returns: Tuple ``(run_times, overhead, average_times)``.
    :rtype: tuple[dict, dict, dict]
    """
    run_times = dict()
    overhead: dict[str, dict[str, dict[str, list[float]]] | list[float]] = {
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
            # noinspection PyUnresolvedReferences
            overhead["instrument"].append(
                run_times[project]["instrument"]
                / run_times[project]["instrument_lines"]
            )
            # noinspection PyUnresolvedReferences
            overhead["test"].append(
                run_times[project]["test"] / run_times[project]["test_lines"]
            )
            for distance in distance_order[1:]:
                # noinspection PyUnresolvedReferences
                overhead[distance]["analyze"].append(
                    run_times[project]["analysis"][distance]
                    / run_times[project]["analysis"]["line"]
                )
                for metric in metric_order:
                    # noinspection PyUnresolvedReferences
                    overhead[distance]["suggest"].append(
                        run_times[project]["suggest"][distance][metric]
                        / run_times[project]["suggest"]["line"][metric]
                    )
                    # noinspection PyUnresolvedReferences
                    overhead[distance]["overall"].append(
                        # Overall compares end-to-end suggestion pipelines to baseline.
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
    """
    Interpret summary artifacts and optionally emit LaTeX tables.

    :param tex: Write LaTeX tables when ``True``.
    :type tex: bool
    :returns: None
    """
    summary = Path("summary.json")
    summary_prfl = Path("summary_prfl.json")
    summary_tcp = Path("summary_tcp.json")
    if not summary.exists() or not summary_prfl.exists():
        return
    with summary.open() as f:
        results = json.load(f)
    with summary_prfl.open() as f:
        results_prfl = json.load(f)
    with summary_tcp.open() as f:
        results_tcp = json.load(f)
    best_for_each_metric, line_for_each_metric, improvements, subs = analyze(results)
    best_for_each_metric_prfl, line_for_each_metric_prfl, improvements_prfl, _ = (
        analyze(results_prfl, prfl=True)
    )
    best_for_each_metric_tcp, line_for_each_metric_tcp, improvements_tcp, _ = analyze(
        results_tcp, tcp=True
    )

    runtimes, overhead, average_times = get_times()
    if tex:
        write_tex(
            results,
            results_prfl,
            results_tcp,
            best_for_each_metric,
            best_for_each_metric_prfl,
            best_for_each_metric_tcp,
            line_for_each_metric,
            line_for_each_metric_prfl,
            line_for_each_metric_tcp,
            improvements,
            improvements_prfl,
            improvements_tcp,
            overhead,
            average_times,
            subs,
        )
