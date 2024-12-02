import argparse
import json
import os

import numpy as np
import tests4py.api as t4p
from tests4py.projects import TestStatus


def build_transition_matrix(call_graph_data, alpha=0.001, delta=1):
    """
    Build the transition matrix P based on the call graph data.
    :param call_graph_data: JSON data representing the call graph.
    :param alpha: The weight for method-to-method transitions (as described in PRFL).
    :param delta: The weight for method-to-test transitions (as described in PRFL).
    :return: The transition matrix p.
    """
    # Create lists to hold the program entities and test cases
    covered_entities = dict()
    covered_tests_passing = dict()
    covered_tests_failing = dict()
    for entity_id, (entity_details, tests, callees) in call_graph_data.items():
        entity_name = f"{entity_details[2]} ({entity_id})"
        if entity_name not in covered_entities:
            covered_entities[entity_name] = list()
        for test in tests["PASS"]["ids"]:
            test_name = f"Pass Test ({test})"
            if test_name not in covered_tests_passing:
                covered_tests_passing[test_name] = list()
            if entity_name not in covered_tests_passing[test_name]:
                covered_tests_passing[test_name].append(entity_name)
        for test in tests["FAIL"]["ids"]:
            test_name = f"Fail Test ({test})"
            if test_name not in covered_tests_failing:
                covered_tests_failing[test_name] = list()
            if entity_name not in covered_tests_failing[test_name]:
                covered_tests_failing[test_name].append(entity_name)
        for callee_id, test_details in callees.items():
            callee_name = f"{call_graph_data[callee_id][0][2]} ({callee_id})"
            if callee_name not in covered_entities:
                covered_entities[callee_name] = list()
            if callee_name not in covered_entities[entity_name]:
                covered_entities[entity_name].append(callee_name)

    # Initialize the transition matrix with zeros
    p_mm = np.zeros((len(covered_entities), len(covered_entities)))
    p_mt_passing = np.zeros((len(covered_tests_passing), len(covered_entities)))
    p_tm_passing = np.zeros((len(covered_entities), len(covered_tests_passing)))
    p_tt_passing = np.zeros((len(covered_tests_passing), len(covered_tests_passing)))

    p_mt_failing = np.zeros((len(covered_tests_failing), len(covered_entities)))
    p_tm_failing = np.zeros((len(covered_entities), len(covered_tests_failing)))
    p_tt_failing = np.zeros((len(covered_tests_failing), len(covered_tests_failing)))

    v_m = np.zeros(len(covered_entities))
    v_t_passing = np.zeros(len(covered_tests_passing))
    v_t_failing = np.zeros(len(covered_tests_failing))

    entity_index = {entity: idx for idx, entity in enumerate(covered_entities)}
    test_index_passing = {test: idx for idx, test in enumerate(covered_tests_passing)}
    test_index_failing = {test: idx for idx, test in enumerate(covered_tests_failing)}

    for entity, covered in covered_entities.items():
        for e in covered:
            p_mm[entity_index[e], entity_index[entity]] += 1
            p_mm[entity_index[entity], entity_index[e]] += delta

    p_mm = normalize_matrix_columns(p_mm)
    p_mm *= alpha

    for test, covered in covered_tests_passing.items():
        for e in covered:
            p_tm_passing[entity_index[e], test_index_passing[test]] = 1
            p_mt_passing[test_index_passing[test], entity_index[e]] = 1
        v_t_passing[test_index_passing[test]] = (
            1 / len(covered_tests_passing) if covered_tests_passing else 0
        )

    for test, covered in covered_tests_failing.items():
        for e in covered:
            p_tm_failing[entity_index[e], test_index_failing[test]] = 1
            p_mt_failing[test_index_failing[test], entity_index[e]] = 1
        v_t_failing = 1 / len(covered) if covered else 0

    p_tm_passing = normalize_matrix_columns(p_tm_passing)
    p_mt_passing = normalize_matrix_columns(p_mt_passing)
    p_tt_passing = normalize_matrix_columns(p_tt_passing)
    p_tm_failing = normalize_matrix_columns(p_tm_failing)

    v_t_failing_sum = np.sum(v_t_failing)
    v_t_failing = v_t_failing / v_t_failing_sum if v_t_failing_sum != 0 else v_t_failing

    return (
        p_mm,
        p_tm_passing,
        p_mt_passing,
        p_tt_passing,
        p_tm_failing,
        p_mt_failing,
        p_tt_failing,
        v_m,
        v_t_passing,
        v_t_failing,
        entity_index,
        test_index_passing,
        test_index_failing,
    )


def normalize_matrix_columns(p):
    """
    Normalize the columns of the matrix P so that each column sums to 1.
    :param p: The matrix to be normalized.
    :return: The normalized matrix.
    """
    column_sums = p.sum(axis=0)  # Sum along columns
    column_sums[column_sums == 0] = 1  # Avoid division by zero, set 0 sums to 1
    return p / column_sums  # Normalize the columns


def get_page_rank(
    p_mm,
    p_tm,
    p_mt,
    p_tt,
    v_m,
    v_t,
    d=0.7,
    tol=1e-6,
    max_iter=100,
):
    """
    Compute the PageRank of the entities and tests in the call graph.
    :param p_mm: Method-to-method transition matrix (P_MM).
    :param p_tm: Test-to-method transition matrix (P_TM).
    :param p_mt: Method-to-test transition matrix (P_MT).
    :param p_tt: Test-to-test transition matrix (P_TT).
    :param v_m: Teleportation vector for methods.
    :param v_t: Teleportation vector for tests.
    :param d: Damping factor for PageRank.
    :param tol: Tolerance for convergence.
    :param max_iter: Maximum number of iterations.
    :return: Tuple of (x_m, x_t) where x_m are the PageRank scores for methods and x_t for tests.
    """
    x_m = np.zeros(p_mm.shape[0])
    x_t = np.zeros(p_tt.shape[0])

    for _ in range(max_iter):
        x_m_old = x_m.copy()
        x_t_old = x_t.copy()

        y_m = d * (p_mm @ x_m + p_tm @ x_t)
        y_t = d * p_mt @ x_m + (1 - d) * v_t

        max_m = np.max(y_m)
        if max_m != 0:
            x_m = y_m / max_m

        max_t = np.max(y_t)
        if max_t != 0:
            x_t = y_t / max_t

        if np.linalg.norm(x_m - x_m_old) < tol and np.linalg.norm(x_t - x_t_old) < tol:
            break

    return x_m, x_t


def main(project_name, bug_id):
    cg_dir = "call_graphs"
    os.makedirs(cg_dir, exist_ok=True)

    for project in t4p.get_projects(project_name, bug_id):
        identifier = project.get_identifier()
        print(identifier)
        if (
            project.test_status_buggy != TestStatus.FAILING
            or project.test_status_fixed != TestStatus.PASSING
        ):
            continue
        cg_file = os.path.join(cg_dir, f"{identifier}.json")
        if not os.path.exists(cg_file):
            continue
        with open(cg_file, "r") as f:
            call_graph_data = json.load(f)
        (
            p_mm,
            p_tm_passing,
            p_mt_passing,
            p_tt_passing,
            p_tm_failing,
            p_mt_failing,
            p_tt_failing,
            v_m,
            v_t_passing,
            v_t_failing,
            entity_index,
            test_index_passing,
            test_index_failing,
        ) = build_transition_matrix(call_graph_data)
        x_m_passing, x_t_passing = get_page_rank(
            p_mm, p_tm_passing, p_mt_passing, p_tt_passing, v_m, v_t_passing
        )
        x_m_failing, x_t_failing = get_page_rank(
            p_mm, p_tm_failing, p_mt_failing, p_tt_failing, v_m, v_t_failing
        )
        page_rank_results = {
            "PASS": dict(),
            "FAIL": dict(),
        }
        for entity, idx in entity_index.items():
            page_rank_results["PASS"][entity] = x_m_passing[idx]
            page_rank_results["FAIL"][entity] = x_m_failing[idx]
        for test, idx in test_index_passing.items():
            page_rank_results["PASS"][test] = x_t_passing[idx]
        for test, idx in test_index_failing.items():
            page_rank_results["FAIL"][test] = x_t_failing[idx]

        with open(os.path.join(cg_dir, f"{identifier}_page_rank.json"), "w") as f:
            json.dump(page_rank_results, f, indent=1)


if __name__ == "__main__":
    args = argparse.ArgumentParser()
    args.add_argument("-p", required=True, dest="project_name", help="project name")
    args.add_argument("-i", default=None, dest="bug_id", help="bug_id")

    arguments = args.parse_args()
    name = arguments.project_name
    id_ = arguments.bug_id
    if id_ is not None:
        id_ = int(id_)

    main(name, id_)
