import argparse
import json
from pathlib import Path

from scipy import stats
from sflkit.analysis.spectra import Spectrum
from sflkit.evaluation import Scenario

from get_analysis import dependencies

tex_translation = {
    Spectrum.Tarantula.__name__: "\\TARANTULA{}",
    Spectrum.Ochiai.__name__: "\\OCHIAI{}",
    Spectrum.DStar.__name__: "\\DSTAR{}",
    Scenario.BEST_CASE.value: "Best Case Debugging",
    Scenario.WORST_CASE.value: "Worst Case Debugging",
    Scenario.AVG_CASE.value: "Average Case Debugging",
    "exam": "\\EXAM{}",
    "wasted-effort": "W Effort",
    "line": "w/o \\DW{}",
    "line_line": "\\DW{}$_L$",
    "line_defuse": "\\DW{}$_S$",
    "line_defuses": "\\DW{}$_U$",
    "line_assert_use": "\\DW{}$_{AS}$",
    "line_assert_uses": "\\DW{}$_{AU}$",
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
]

dependency_order = [f"line{suffix}" for suffix, _ in dependencies]

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
        "    \\multicolumn{1}{c}{\\multirow{4}*{Dependency}} & \\multicolumn{1}{c}{\\multirow{4}*{Metric}} & "
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
    for dependency in dependency_order:
        for metric in metric_order:
            if metric == metric_order[0]:
                table += f"    \\multirow{3}*{{{tex_translation[dependency]}}}"
            else:
                table += "    "
            table += f" & {tex_translation[metric]}"
            for scenario in scenario_order:
                for localization, comp in zip(localization_order, localization_comp):
                    text_underline = (
                        dependency
                        in best_for_each_metric[metric][scenario][localization][0][1]
                    )
                    text_bf = (
                        (
                            results[dependency][metric][scenario][localization]["avg"]
                            > line_for_each_metric[metric][scenario][localization]
                        )
                        if comp
                        else (
                            results[dependency][metric][scenario][localization]["avg"]
                            < line_for_each_metric[metric][scenario][localization]
                        )
                    )
                    table += " & "
                    if text_underline:
                        table += "\\underline{"
                    if text_bf:
                        table += "\\textbf{\\color{deepblue}"
                    if localization.startswith("top"):
                        table += (
                            f"{results[dependency][metric][scenario][localization]['avg'] * 100:.1f}"
                            "\\%"
                        )
                    elif localization == "exam":
                        table += f"{results[dependency][metric][scenario][localization]['avg']:.3f}"
                    else:
                        table += (
                            f"{results[dependency][metric][scenario][localization]['avg'] / 1000:.1f}"
                            f"k"
                        )
                    if text_bf:
                        table += "}"
                    if text_underline:
                        table += "}"
            table += " \\\\\n"
        if dependency != dependency_order[-1]:
            table += "\\addlinespace[0.6em]\n"

    table += "\\bottomrule\n\\end{tabular}\n"
    return table


def get_improvement_tex_table(improvements, total_improvements):
    table = (
        "\\begin{tabular}{llrrrrrrrrrrrrrrr}\n"
        "    \\toprule\n"
        "    \\multicolumn{1}{c}{\\multirow{4}*{Dependency}} & \\multicolumn{1}{c}{\\multirow{4}*{}} & "
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
    for dependency in dependency_order[1:]:
        table += f"    \\multirow{{3}}*{{{tex_translation[dependency]}}}"
        table += " & Improved"
        actual_improvement = {
            scenario: {
                localization: [
                    improvement
                    for metric in metric_order
                    for improvement in improvements[dependency][metric][scenario][
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
                table += " & "
                total = len(
                    [
                        improvement
                        for metric in metric_order
                        for improvement in improvements[dependency][metric][scenario][
                            localization
                        ]
                        if improvement > 1
                    ]
                )
                table += f"{total}"
        table += " \\\\\n"
        table += " & New"
        for scenario in scenario_order:
            for localization in localization_order:
                table += " & "
                newly_found = len(
                    [
                        improvement
                        for metric in metric_order
                        for improvement in improvements[dependency][metric][scenario][
                            localization
                        ]
                        if improvement == float("inf")
                    ]
                )
                table += f"{newly_found if newly_found > 0 else '---'}"
        table += " \\\\\n"
        table += " & Average"
        for scenario in scenario_order:
            for localization in localization_order:
                avg_percent = (
                    sum(actual_improvement[scenario][localization])
                    / len(actual_improvement[scenario][localization])
                    - 1
                ) * 100
                table += f" & {int(avg_percent)}\\%"
        table += " \\\\\n"
        if dependency != dependency_order[-1]:
            table += "\\addlinespace[0.6em]\n"

    table += "\\bottomrule\n\\end{tabular}\n"
    return table


def get_disadvantages_tex_table(improvements, total_improvements):
    table = (
        "\\begin{tabular}{llrrrrrrrrrrrrrrr}\n"
        "    \\toprule\n"
        "    \\multicolumn{1}{c}{\\multirow{4}*{Dependency}} & \\multicolumn{1}{c}{\\multirow{4}*{}} & "
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
    for dependency in dependency_order[1:]:
        table += f"    \\multirow{{3}}*{{{tex_translation[dependency]}}}"
        table += " & Decreased"
        actual_decrease = {
            scenario: {
                localization: [
                    improvement
                    for metric in metric_order
                    for improvement in improvements[dependency][metric][scenario][
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
                table += " & "
                total = len(actual_decrease[scenario][localization])
                table += f"{total}"
        table += " \\\\\n"
        table += " & New"
        for scenario in scenario_order:
            for localization in localization_order:
                table += " & "
                newly_found = len(
                    [
                        improvement
                        for metric in metric_order
                        for improvement in improvements[dependency][metric][scenario][
                            localization
                        ]
                        if improvement == 0
                    ]
                )
                table += f"{newly_found if newly_found > 0 else '---'}"
        table += " \\\\\n"
        table += " & Average"
        for scenario in scenario_order:
            for localization in localization_order:
                avg_percent = (
                    sum(actual_decrease[scenario][localization])
                    / len(actual_decrease[scenario][localization])
                    - 1
                ) * 100
                table += f" & {int(avg_percent)}\\%"
        table += " \\\\\n"
        if dependency != dependency_order[-1]:
            table += "\\addlinespace[0.6em]\n"

    table += "\\bottomrule\n\\end{tabular}\n"
    return table


def write_tex(
    results,
    best_for_each_metric,
    line_for_each_metric,
    improvements,
    total_improvements,
):
    tex_output = Path("tex")
    if not tex_output.exists():
        tex_output.mkdir()
    localization_table = get_localization_tex_table(
        results, best_for_each_metric, line_for_each_metric
    )
    with Path(tex_output, "localization.tex").open("w") as f:
        f.write(localization_table)
    improvement_table = get_improvement_tex_table(improvements, total_improvements)
    with Path(tex_output, "improvement.tex").open("w") as f:
        f.write(improvement_table)
    disadvantage_table = get_disadvantages_tex_table(improvements, total_improvements)
    with Path(tex_output, "disadvantage.tex").open("w") as f:
        f.write(disadvantage_table)


def analyze(results):
    """analyze bests for the various metrics and report highest p-value"""
    line_for_each_metric = dict()
    best_for_each_metric = dict()
    p_values = dict()
    max_p = 0
    improvements = {
        dependency: {
            m: {s: {lo: list() for lo in localization_order} for s in scenario_order}
            for m in metric_order
        }
        for dependency in dependency_order[1:]
    }
    total_improvements = {
        dependency: {
            m: {s: {lo: list() for lo in localization_order} for s in scenario_order}
            for m in metric_order
        }
        for dependency in dependency_order[1:]
    }
    for metric in metric_order:
        line_for_each_metric[metric] = dict()
        best_for_each_metric[metric] = dict()
        p_values[metric] = dict()
        for scenario in scenario_order:
            best_for_each_metric[metric][scenario] = dict()
            line_for_each_metric[metric][scenario] = dict()
            p_values[metric][scenario] = dict()
            for localization, comp in zip(localization_order, localization_comp):
                p_values[metric][scenario][localization] = dict()
                bests = dict()
                for dependency in dependency_order:
                    avg = results[dependency][metric][scenario][localization]["avg"]
                    if dependency == "line":
                        line_for_each_metric[metric][scenario][localization] = avg
                    else:
                        for dependency_result, line_result in zip(
                            results[dependency][metric][scenario][localization]["all"],
                            results["line"][metric][scenario][localization]["all"],
                        ):
                            if comp:
                                if line_result > 0:
                                    improvements[dependency][metric][scenario][
                                        localization
                                    ].append(dependency_result / line_result)
                                else:
                                    improvements[dependency][metric][scenario][
                                        localization
                                    ].append(float("inf"))
                                total_improvements[dependency][metric][scenario][
                                    localization
                                ].append(dependency_result - line_result)
                            else:
                                if dependency_result > 0:
                                    improvements[dependency][metric][scenario][
                                        localization
                                    ].append(line_result / dependency_result)
                                else:
                                    improvements[dependency][metric][scenario][
                                        localization
                                    ].append(float("inf"))
                                total_improvements[dependency][metric][scenario][
                                    localization
                                ].append(line_result - dependency_result)
                    if avg in bests:
                        bests[avg].append(dependency)
                    else:
                        bests[avg] = [dependency]
                    for dependency2 in dependency_order:
                        if dependency == dependency2:
                            continue
                        _, p = stats.ranksums(
                            results[dependency][metric][scenario][localization]["all"],
                            results[dependency2][metric][scenario][localization]["all"],
                        )
                        p_values[metric][scenario][localization][
                            f"{dependency}-{dependency2}"
                        ] = p
                        max_p = max(max_p, p)
                bests = sorted([(score, bests[score]) for score in bests], reverse=comp)
                best_for_each_metric[metric][scenario][localization] = bests

    return (
        best_for_each_metric,
        line_for_each_metric,
        p_values,
        improvements,
        total_improvements,
    )


def main(tex=False):
    summary = Path("summary.json")
    if not summary.exists():
        return
    with summary.open() as f:
        results = json.load(f)
    (
        best_for_each_metric,
        line_for_each_metric,
        p_values,
        improvements,
        total_improvements,
    ) = analyze(results)

    with Path("p_values.json").open("w") as f:
        json.dump(p_values, f, indent=1)
    if tex:
        write_tex(
            results,
            best_for_each_metric,
            line_for_each_metric,
            improvements,
            total_improvements,
        )


if __name__ == "__main__":
    args = argparse.ArgumentParser()
    args.add_argument(
        "-t", default=False, action="store_true", dest="tex", help="generate tex tables"
    )
    arguments = args.parse_args()
    main(tex=arguments.tex)
