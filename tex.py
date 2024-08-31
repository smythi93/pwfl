import argparse
import json
from pathlib import Path

from scipy import stats
from sflkit.analysis.spectra import Spectrum
from sflkit.evaluation import Scenario

from get_analysis import slices

tex_translation = {
    Spectrum.Tarantula.__name__: "\\TARANTULA{}",
    Spectrum.Ochiai.__name__: "\\OCHIAI{}",
    Spectrum.DStar.__name__: "\\DSTAR{}",
    Scenario.BEST_CASE.value: "Best Case Debugging",
    Scenario.WORST_CASE.value: "Worst Case Debugging",
    Scenario.AVG_CASE.value: "Average Case Debugging",
    "exam": "\\EXAM{}",
    "wasted-effort": "W Effort",
    "line": "w/o \\FENDR{}",
    "line_line": "\\FENDR{}$_L$",
    "line_defuse": "\\FENDR{}$_S$",
    "line_defuses": "\\FENDR{}$_U$",
    "line_assert_use": "\\FENDR{}$_{AS}$",
    "line_assert_uses": "\\FENDR{}$_{AU}$",
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

slice_order = [f"line{suffix}" for suffix, _ in slices]

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
        "    \\multicolumn{1}{c}{\\multirow{4}*{Feature}} & \\multicolumn{1}{c}{\\multirow{4}*{Metric}} & "
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
    for slice_ in slice_order:
        for metric in metric_order:
            if metric == metric_order[0]:
                table += f"    \\multirow{3}*{{{tex_translation[slice_]}}}"
            else:
                table += "    "
            table += f" & {tex_translation[metric]}"
            for scenario in scenario_order:
                for localization, comp in zip(localization_order, localization_comp):
                    text_underline = (
                        slice_
                        in best_for_each_metric[metric][scenario][localization][0][1]
                    )
                    text_bf = (
                        (
                            results[slice_][metric][scenario][localization]["avg"]
                            > line_for_each_metric[metric][scenario][localization]
                        )
                        if comp
                        else (
                            results[slice_][metric][scenario][localization]["avg"]
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
                            f"{results[slice_][metric][scenario][localization]['avg'] * 100:.1f}"
                            "\\%"
                        )
                    elif localization == "exam":
                        table += f"{results[slice_][metric][scenario][localization]['avg']:.3f}"
                    else:
                        table += (
                            f"{results[slice_][metric][scenario][localization]['avg'] / 1000:.1f}"
                            f"k"
                        )
                    if text_bf:
                        table += "}"
                    if text_underline:
                        table += "}"
            table += " \\\\\n"
        if slice_ != slice_order[-1]:
            table += "\\addlinespace[0.6em]\n"

    table += "\\bottomrule\n\\end{tabular}\n"
    return table


def write_tex(results, best_for_each_metric, line_for_each_metric):
    tex_output = Path("tex")
    if not tex_output.exists():
        tex_output.mkdir()
    localization_table = get_localization_tex_table(
        results, best_for_each_metric, line_for_each_metric
    )
    with Path(tex_output, "localization.tex").open("w") as f:
        f.write(localization_table)


def analyze(results):
    """analyze bests for the various metrics and report highest p-value"""
    line_for_each_metric = dict()
    best_for_each_metric = dict()
    p_values = dict()
    max_p = 0
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
                for slice_ in slice_order:
                    avg = results[slice_][metric][scenario][localization]["avg"]
                    if slice_ == "line":
                        line_for_each_metric[metric][scenario][localization] = avg
                    if avg in bests:
                        bests[avg].append(slice_)
                    else:
                        bests[avg] = [slice_]
                    for slice_2 in slice_order:
                        if slice_ == slice_2:
                            continue
                        _, p = stats.ranksums(
                            results[slice_][metric][scenario][localization]["all"],
                            results[slice_2][metric][scenario][localization]["all"],
                        )
                        p_values[metric][scenario][localization][
                            f"{slice_}-{slice_2}"
                        ] = p
                        max_p = max(max_p, p)
                bests = sorted([(score, bests[score]) for score in bests], reverse=comp)
                best_for_each_metric[metric][scenario][localization] = bests
    return best_for_each_metric, line_for_each_metric, p_values, max_p


def main(tex=False):
    summary = Path("summary.json")
    if not summary.exists():
        return
    with summary.open() as f:
        results = json.load(f)
    best_for_each_metric, line_for_each_metric, p_values, _ = analyze(results)
    with Path("p_values.json").open("w") as f:
        json.dump(p_values, f, indent=1)
    if tex:
        write_tex(
            results,
            best_for_each_metric,
            line_for_each_metric,
        )


if __name__ == "__main__":
    args = argparse.ArgumentParser()
    args.add_argument(
        "-t", default=False, action="store_true", dest="tex", help="generate tex tables"
    )
    arguments = args.parse_args()
    main(tex=arguments.tex)
