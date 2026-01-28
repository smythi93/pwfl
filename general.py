def pwfl_improvement(
    n_tests,
    avg_assertions,
    avg_lines,
    avg_lines_between_assertions,
    multi_assertion_ratio,
    multi_line_ratio,
):
    if multi_line_ratio == 1:
        multi_line_ratio = 0
    if multi_assertion_ratio == 1:
        multi_assertion_ratio = 0
    return (avg_lines * avg_lines_between_assertions * avg_assertions) / (
        n_tests
        * (
            (1 - multi_assertion_ratio)
            * (1 - multi_line_ratio)
            / ((1 - multi_assertion_ratio) + (1 - multi_line_ratio))
        )
    )


def pwfl_improvement_percentage(
    n_tests,
    avg_assertions,
    avg_lines,
    avg_lines_between_assertions,
    multi_assertion_ratio,
    multi_line_ratio,
):
    return (
        pwfl_improvement(
            n_tests,
            avg_assertions,
            avg_lines,
            avg_lines_between_assertions,
            multi_assertion_ratio,
            multi_line_ratio,
        )
        - 1
    ) * 100


if __name__ == "__main__":
    print(pwfl_improvement(4176, 2.3, 15.26, 5.66, 0.44, 0.97))
    print(pwfl_improvement_percentage(4176, 2.3, 15.26, 5.66, 0.44, 0.97))
    print(pwfl_improvement(906, 2.21, 14.09, 5.27, 0.4414, 0.9487))
    print(pwfl_improvement_percentage(906, 2.21, 14.09, 5.27, 0.4414, 0.9487))
