"""
Utilities for analyzing test-suite structure in the PWFL study.
"""

import ast
import json
import os
from contextlib import contextmanager
from pathlib import Path

import matplotlib as mpl
import seaborn as sns
import tests4py.api as t4p
from tests4py.projects import Project, TestStatus

from pwfl.logger import LOGGER


class Visitor(ast.NodeVisitor):
    """
    AST visitor collecting per-test and per-subject statistics.

    The visitor tracks counts for tests, assertions, test lengths, and spacing
    between assertions to support the motivation study.
    """

    def __init__(self):
        """
        Initialize all counters and accumulator lists.

        :returns: None
        """
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
        """
        Serialize visitor state into a JSON-friendly dictionary.

        :returns: Collected metrics.
        :rtype: dict
        """
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
        """
        Reconstruct a :class:`Visitor` from serialized state.

        :param data: Data produced by :meth:`dump`.
        :type data: dict
        :returns: Restored visitor.
        :rtype: Visitor
        """
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
        """
        Start accumulation for a new subject.

        :returns: None
        """
        self.total_subjects += 1
        self.tests_per_subject.append(0)

    def check(self, node):
        """
        Visit an AST module and create a file-level test counter.

        :param node: Parsed module AST.
        :type node: ast.AST
        :returns: None
        """
        self.tests_per_file.append(0)
        self.visit(node)

    def visit_FunctionDef(self, node):
        """
        Process a function definition and track it if it is a test.

        :param node: Function definition node.
        :type node: ast.FunctionDef
        :returns: None
        """
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
        """
        Track an assertion-like statement in the current test.

        :param node: Assertion AST node (assert statement or assert-like call).
        :type node: ast.AST
        :returns: None
        """
        if self.current_test_assertions:
            line_number = getattr(node, "lineno", None)
            if line_number is None:
                return
            self.current_test_assertions[-1] += 1
            self.lines_between_assertions.append(
                line_number - self.last_assertion_line[-1]
            )
            self.last_assertion_line[-1] = line_number

    def visit_Assert(self, node):
        """
        Handle ``assert`` statements.

        :param node: Assert node.
        :type node: ast.Assert
        :returns: None
        """
        self.visit_assertion(node)

    def visit_Call(self, node):
        """
        Handle unittest/pytest-style assertion helper calls.

        :param node: Call node.
        :type node: ast.Call
        :returns: None
        """
        if "assert" in ast.unparse(node.func).lower():
            self.visit_assertion(node)


@contextmanager
def pdf_font_context():
    """
    Temporarily configure Matplotlib to embed TrueType fonts in PDF output.

    Matplotlib defaults to Type 3 fonts for PDFs in some environments, which
    can look poor in many viewers. Setting both PDF and PS font types to 42
    keeps the exported figures text-based and more portable.

    :returns: Context manager yielding control with the updated rcParams.
    """
    with mpl.rc_context({"pdf.fonttype": 42, "ps.fonttype": 42}):
        yield


def analyze_subject(project: Project, visitor: Visitor):
    """
    Collect test-structure metrics for one project checkout.

    :param project: Subject metadata.
    :type project: Project
    :param visitor: Shared metrics visitor.
    :type visitor: Visitor
    :returns: None
    """
    report = t4p.checkout(project)
    if not report.successful:
        raise report.raised
    location = report.location
    if location is None:
        raise ValueError("Location is None")
    else:
        location = Path(location)
    if project.test_base is None:
        test_base = location
    else:
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


def get_results(project_name=None, bug_id=None, start=0, end=None, skip=False):
    """
    Run the motivation-study scan across selected projects.

    :param project_name: Optional project name filter.
    :type project_name: str | None
    :param bug_id: Optional single bug id filter.
    :type bug_id: int | None
    :param start: Lower bound bug id.
    :type start: int | None
    :param end: Upper bound bug id.
    :type end: int | None
    :param skip: Skip subjects that do not satisfy baseline test-status criteria.
    :type skip: bool
    :returns: None
    """
    visitor = Visitor()
    for project in t4p.get_projects(project_name, bug_id):
        if skip and (
            project.test_status_buggy != TestStatus.FAILING
            or project.test_status_fixed != TestStatus.PASSING
            or project.project_name == "pandas"
        ):
            continue
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
    with open(f"../study_results{'_skipped' if skip else ''}.json", "w") as f:
        json.dump(visitor.dump(), f, indent=1)


def print_results(visitor):
    """
    Log aggregate statistics derived from a populated visitor.

    :param visitor: Metrics visitor.
    :type visitor: Visitor
    :returns: None
    """
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
    """
    Render distribution plots from a serialized motivation-study file.

    :param file: Path to stored visitor statistics JSON.
    :type file: str | os.PathLike
    :returns: None
    """
    with open(file, "r") as f:
        data = json.load(f)
    visitor = Visitor.load(data)
    results = Path("study")
    results.mkdir(exist_ok=True)
    with pdf_font_context():
        test_per_subject = sns.displot(
            {"Tests per Subject": visitor.tests_per_subject},
            kde=True,
            stat="count",
            x="Tests per Subject",
            bins=50,
        )
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
