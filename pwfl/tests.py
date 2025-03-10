import ast
import json
import os
from pathlib import Path

import seaborn as sns
import tests4py.api as t4p
from tests4py.projects import Project

from pwfl.logger import LOGGER


class Visitor(ast.NodeVisitor):
    def __init__(self):
        self.total_subjects = 0
        self.total_tests = 0
        self.tests_per_subject = []
        self.tests_per_file = []
        self.assertions_per_test = []
        self.current_test_assertions = []
        self.lines_per_test = []
        self.lines_between_assertions = []
        self.last_assertion_line = []

    def dump(self):
        return {
            "total_subjects": self.total_subjects,
            "total_tests": self.total_tests,
            "tests_per_subject": self.tests_per_subject,
            "tests_per_file": self.tests_per_file,
            "assertions_per_test": self.assertions_per_test,
            "lines_per_test": self.lines_per_test,
            "lines_between_assertions": self.lines_between_assertions,
        }

    @staticmethod
    def load(data):
        visitor = Visitor()
        visitor.total_subjects = data["total_subjects"]
        visitor.total_tests = data["total_tests"]
        visitor.tests_per_subject = data["tests_per_subject"]
        visitor.tests_per_file = data["tests_per_file"]
        visitor.assertions_per_test = data["assertions_per_test"]
        visitor.lines_per_test = data["lines_per_test"]
        visitor.lines_between_assertions = data["lines_between_assertions"]
        return visitor

    def subject(self):
        self.total_subjects += 1
        self.tests_per_subject.append(0)

    def check(self, node):
        self.tests_per_file.append(0)
        self.visit(node)

    def visit_FunctionDef(self, node):
        if node.name.startswith("test"):
            self.total_tests += 1
            self.tests_per_subject[-1] += 1
            self.tests_per_file[-1] += 1
            self.current_test_assertions.append(0)
            self.lines_per_test.append(node.end_lineno - node.lineno)
            self.last_assertion_line.append(node.lineno)
            self.generic_visit(node)
            self.assertions_per_test.append(self.current_test_assertions.pop())
            self.last_assertion_line.pop()

    def visit_assertion(self, node):
        if self.current_test_assertions:
            self.current_test_assertions[-1] += 1
            self.lines_between_assertions.append(
                node.lineno - self.last_assertion_line[-1]
            )
            self.last_assertion_line[-1] = node.lineno

    def visit_Assert(self, node):
        self.visit_assertion(node)

    def visit_Call(self, node):
        if "assert" in ast.unparse(node.func).lower():
            self.visit_assertion(node)


def analyze_subject(project: Project, visitor: Visitor):
    report = t4p.checkout(project)
    if not report.successful:
        raise report.raised
    location = report.location
    if location is None:
        raise ValueError("Location is None")
    else:
        location = Path(location)
    test_base = location / project.test_base
    if not test_base.exists():
        raise FileNotFoundError(f"{test_base} does not exist")
    visitor.subject()
    for directory, _, files in os.walk(test_base):
        for file in files:
            if file.endswith(".py"):
                with open(Path(directory, file)) as f:
                    content = f.read()
                try:
                    tree = ast.parse(content)
                    visitor.check(tree)
                except SyntaxError:
                    continue


def get_results(project_name=None, bug_id=None, start=0, end=None):
    visitor = Visitor()
    for project in t4p.get_projects(project_name, bug_id):
        if start is not None and project.bug_id < start:
            continue
        if end is not None and project.bug_id > end:
            continue
        if project.project_name == "pandas":
            project.test_base = Path("pandas", "tests")
        elif project.project_name in ("calculator", "markup", "thefuck"):
            project.test_base = Path("tests")
        project.buggy = True
        try:
            analyze_subject(project, visitor)
        except:
            continue
    print_results(visitor)
    with open("../study_results.json", "w") as f:
        json.dump(visitor.dump(), f, indent=1)


def print_results(visitor):
    average_tests_per_subject = sum(visitor.tests_per_subject) / visitor.total_subjects
    average_assertions_per_test = sum(visitor.assertions_per_test) / visitor.total_tests
    average_lines_per_test = sum(visitor.lines_per_test) / visitor.total_tests
    tests_with_multiple_assertions = len(
        [a for a in visitor.assertions_per_test if a > 1]
    )
    tests_with_multiple_lines = len([l for l in visitor.lines_per_test if l > 1])
    average_lines_between_assertions = sum(visitor.lines_between_assertions) / len(
        visitor.lines_between_assertions
    )
    tests_without_assertions = len(
        [visitor.tests_per_subject for x in visitor.assertions_per_test if x == 0]
    )

    LOGGER.info(f"Total subjects: {visitor.total_subjects}")
    LOGGER.info(f"Total tests: {visitor.total_tests}")
    LOGGER.info(f"Total assertions: {sum(visitor.assertions_per_test)}")
    LOGGER.info(f"Average tests per subject: {average_tests_per_subject}")
    LOGGER.info(f"Average assertions per test: {average_assertions_per_test}")
    LOGGER.info(f"Average lines per test: {average_lines_per_test}")
    LOGGER.info(f"Tests with multiple assertions: {tests_with_multiple_assertions}")
    LOGGER.info(f"Tests with multiple lines: {tests_with_multiple_lines}")
    LOGGER.info(f"Average lines between assertions: {average_lines_between_assertions}")
    LOGGER.info(f"Tests without assertions: {tests_without_assertions}")


def analyze_file(file):
    with open(file, "r") as f:
        data = json.load(f)
    visitor = Visitor.load(data)
    test_per_subject = sns.displot(
        {"Tests per Subject": visitor.tests_per_subject},
        kde=True,
        stat="count",
        x="Tests per Subject",
        bins=50,
    )
    results = Path("../study")
    results.mkdir(exist_ok=True)
    test_per_subject.savefig(results / "tests_per_subject.pdf")
    assertions_per_test = sns.displot(
        {"Assertions per Test": [x for x in visitor.lines_per_test if x <= 15]},
        kde=True,
        stat="count",
        x="Assertions per Test",
        bins=15,
        kde_kws={"bw_adjust": 5},
    )
    assertions_per_test.savefig(results / "assertions_per_test.pdf")
    lines_per_test = sns.displot(
        {"Lines per Test": [x for x in visitor.lines_per_test if x <= 60]},
        kde=True,
        stat="count",
        x="Lines per Test",
        bins=20,
        kde_kws={"bw_adjust": 2},
    )
    lines_per_test.savefig(results / "lines_per_test.pdf")
    lines_between_assertions = sns.displot(
        {
            "Lines between Assertions": [
                x for x in visitor.lines_between_assertions if x <= 30
            ]
        },
        kde=True,
        stat="count",
        x="Lines between Assertions",
        bins=20,
        kde_kws={"bw_adjust": 5},
    )
    lines_between_assertions.savefig(results / "lines_between_assertions.pdf")
    print_results(visitor)
