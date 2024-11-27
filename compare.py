import os

HEADER = """\\begin{tabular}{llrrrrrrrrrrrrrrr}
    \\toprule
    \\multicolumn{1}{c}{\\multirow{4}*{Approach}} & \\multicolumn{1}{c}{\\multirow{4}*{}} & \\multicolumn{5}{c}{Best-Case Debugging} & \\multicolumn{5}{c}{Average-Case Debugging} & \\multicolumn{5}{c}{Worst-Case Debugging} \\\\\\cmidrule(lr){3-7}\\cmidrule(lr){8-12}\\cmidrule(lr){13-17}
    & & \\multicolumn{3}{c}{Top-k} & \\multicolumn{1}{c}{\\multirow{2}*{\\EXAM{}}} & \\multicolumn{1}{c}{\\multirow{2}*{Effort}}
 & \\multicolumn{3}{c}{Top-k} & \\multicolumn{1}{c}{\\multirow{2}*{\\EXAM{}}} & \\multicolumn{1}{c}{\\multirow{2}*{Effort}}
 & \\multicolumn{3}{c}{Top-k} & \\multicolumn{1}{c}{\\multirow{2}*{\\EXAM{}}} & \\multicolumn{1}{c}{\\multirow{2}*{Effort}}
\\\\\\cmidrule{3-5}\\cmidrule{8-10}\\cmidrule{13-15}
    & & \\multicolumn{1}{c}{5} & \\multicolumn{1}{c}{10} & \\multicolumn{1}{c}{200} & &
 & \\multicolumn{1}{c}{5} & \\multicolumn{1}{c}{10} & \\multicolumn{1}{c}{200} & &
 & \\multicolumn{1}{c}{5} & \\multicolumn{1}{c}{10} & \\multicolumn{1}{c}{200} & &
\\\\\\midrule
    \\multirow{3}*{\\TW{}$_L$}"""

FOOTER = """\\bottomrule
\\end{tabular}"""

INTER_1 = """\\addlinespace[0.6em]
    \\multirow{3}*{\\TW{}$_{DU}$}"""

INTER_2 = """\\addlinespace[0.6em]
    \\multirow{3}*{\\TW{}$_{DUU}$}"""

INTER_3 = """\\addlinespace[0.6em]
    \\multirow{3}*{\\TW{}$_{ADU}$}"""

INTER_4 = """\\addlinespace[0.6em]
    \\multirow{3}*{\\TW{}$_{ADUU}$}"""


def main():
    with open(os.path.join("tex", "improvement.tex")) as f:
        new_results = f.read()
    with open(os.path.join("tex", "improvement1.tex")) as f:
        old_results = f.read()
    new_results = (
        new_results.replace(HEADER, "")
        .replace(FOOTER, "")
        .replace(INTER_1, "")
        .replace(INTER_2, "")
        .replace(INTER_3, "")
        .replace(INTER_4, "")
        .replace(" ", "")
        .replace("\n", "")
        .replace("\\%", "")
    )
    old_results = (
        old_results.replace(HEADER, "")
        .replace(FOOTER, "")
        .replace(INTER_1, "")
        .replace(INTER_2, "")
        .replace(INTER_3, "")
        .replace(INTER_4, "")
        .replace(" ", "")
        .replace("\n", "")
        .replace("\\%", "")
    )
    new_results = new_results.split("\\")
    old_results = old_results.split("\\")
    new_results = [x.split("&") for x in new_results]
    old_results = [x.split("&") for x in old_results]
    new_results = [
        [float(y) for y in x if y and (y.isdigit() or (y[0] == "-" and y[1:].isdigit))]
        for x in new_results
    ]
    old_results = [
        [float(y) for y in x if y and (y.isdigit() or (y[0] == "-" and y[1:].isdigit))]
        for x in old_results
    ]
    new_better = 0
    old_better = 0
    same = 0
    new_total = 0
    old_total = 0
    total = 0
    for i in range(len(new_results)):
        for j in range(len(new_results[i])):
            total += 1
            new_total += new_results[i][j]
            old_total += old_results[i][j]
            if new_results[i][j] == old_results[i][j]:
                same += 1
            elif new_results[i][j] > old_results[i][j]:
                new_better += 1
            else:
                old_better += 1
    print(f"New better: {new_better}")
    print(f"Old better: {old_better}")
    print(f"Same: {same}")
    print(f"Total: {total}")
    print(f"New total: {new_total}")
    print(f"Old total: {old_total}")
    print(f"New average: {new_total / total}")
    print(f"Old average: {old_total / total}")


if __name__ == "__main__":
    main()
