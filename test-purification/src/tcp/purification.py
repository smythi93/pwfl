"""
Test Case Purification for Fault Localization

This module implements test case purification as described in the paper.
The main phases are:
1. Test Case Atomization - Create single-assertion tests with try-except
2. Test Case Slicing - Use dynamic slicing to remove irrelevant statements
3. Rank Refinement - Combine original scores with purified test spectra
"""

import ast
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Any, Set

from .logger import LOGGER
from .slicer import PytestSlicer


# ============================================================================
# Phase 1: Test Case Atomization
# ============================================================================


class ParameterizeInfo:
    """Information about a pytest.mark.parametrize decorator."""

    def __init__(self, param_names: list[str], param_values: list):
        self.param_names = param_names
        self.param_values = param_values


class ParameterizeFinder(ast.NodeVisitor):
    """Find pytest.mark.parametrize decorators on a test function."""

    def __init__(self):
        self.parametrize_info: Optional[ParameterizeInfo] = None

    @staticmethod
    def extract_parametrize_info(decorator: ast.expr) -> Optional[ParameterizeInfo]:
        """Extract parameter info from @pytest.mark.parametrize decorator."""
        if not isinstance(decorator, ast.Call):
            return None

        # Check if this is pytest.mark.parametrize
        if isinstance(decorator.func, ast.Attribute):
            if (
                isinstance(decorator.func.value, ast.Attribute)
                and isinstance(decorator.func.value.value, ast.Name)
                and decorator.func.value.value.id == "pytest"
                and decorator.func.value.attr == "mark"
                and decorator.func.attr == "parametrize"
            ):
                # Extract arguments
                if len(decorator.args) >= 2:
                    # First arg: parameter names (string or tuple of strings)
                    param_names_node = decorator.args[0]
                    if isinstance(param_names_node, ast.Constant):
                        # Single parameter or comma-separated string
                        param_names_str = param_names_node.value
                        param_names = [
                            name.strip() for name in param_names_str.split(",")
                        ]
                    else:
                        return None

                    # Second arg: parameter values (list or iterable)
                    param_values_node = decorator.args[1]
                    # For now, we'll just mark that it's parameterized
                    # Actual values will be extracted from test ID
                    return ParameterizeInfo(param_names, [])

        return None


class AssertionFinder(ast.NodeVisitor):
    """Find all assertions in a test function."""

    def __init__(self):
        self.assertions: list[tuple[int, ast.AST]] = []  # (line_number, node)

    def visit_Assert(self, node: ast.Assert):
        """Visit assert statements."""
        self.assertions.append((node.lineno, node))
        self.generic_visit(node)

    def visit_Expr(self, node: ast.Expr):
        """Visit expression statements (for pytest assertions like assert_equal)."""
        if isinstance(node.value, ast.Call):
            func_name = self._get_func_name(node.value.func)
            if func_name and "assert" in func_name.lower():
                self.assertions.append((node.lineno, node))
        self.generic_visit(node)

    @staticmethod
    def _get_func_name(node):
        """Extract function name from a call node."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return node.attr
        return None


class FunctionFinder(ast.NodeVisitor):
    """Find test functions in a module (including methods in test classes)."""

    def __init__(self, target_test: Optional[str] = None):
        self.test_functions: dict[str, ast.FunctionDef] = {}
        self.test_classes: dict[str, ast.ClassDef] = {}
        self.target_test = target_test
        self.current_class = None

    def visit_ClassDef(self, node: ast.ClassDef):
        """Visit class definitions to find test classes."""
        # Save the current class context
        old_class = self.current_class
        # Any class can contain test methods, not just those starting with "Test"
        self.current_class = node
        self.test_classes[node.name] = node

        # Visit children (test methods inside the class)
        self.generic_visit(node)

        # Restore previous class context
        self.current_class = old_class

    def visit_FunctionDef(self, node: ast.FunctionDef):
        """Visit function definitions (including methods)."""
        if node.name.startswith("test_"):
            if self.target_test is None or node.name == self.target_test:
                self.test_functions[node.name] = node
                # Store reference to parent class if inside a class
                if self.current_class is not None:
                    node._parent_class = self.current_class

                # Check for pytest.mark.parametrize decorator
                param_info = None
                for decorator in node.decorator_list:
                    param_info = ParameterizeFinder.extract_parametrize_info(decorator)
                    if param_info:
                        break
                node._parametrize_info = param_info

        self.generic_visit(node)


class AssertionAtomizer(ast.NodeTransformer):
    """
    Transform a test function to wrap non-target assertions in try-except.
    This is used in the first phase to identify which assertions fail.
    Handles both module-level functions and class methods.
    """

    def __init__(self, target_assertion_line: int):
        self.target_assertion_line = target_assertion_line
        self.in_target_function = False
        self.in_class = False

    def visit_ClassDef(self, node: ast.ClassDef):
        """Visit class definitions."""
        # Any class can contain test methods
        self.in_class = True
        node = self.generic_visit(node)
        self.in_class = False
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef):
        """Visit function definitions."""
        if node.name.startswith("test_"):
            self.in_target_function = True
            node = self.generic_visit(node)
            self.in_target_function = False
            return node
        # Keep non-test methods in classes (like setup_method, teardown_method)
        elif self.in_class:
            return self.generic_visit(node)
        return node

    def visit_Assert(self, node: ast.Assert):
        """Wrap non-target assertions in try-except."""
        if self.in_target_function and node.lineno != self.target_assertion_line:
            return self._wrap_in_try_except(node)
        return node

    def visit_Expr(self, node: ast.Expr):
        """Wrap non-target assertion calls in try-except."""
        if self.in_target_function and isinstance(node.value, ast.Call):
            func_name = self._get_func_name(node.value.func)
            if func_name and "assert" in func_name.lower():
                if node.lineno != self.target_assertion_line:
                    return self._wrap_in_try_except(node)
        return node

    @staticmethod
    def _get_func_name(node):
        """Extract function name from a call node."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return node.attr
        return None

    @staticmethod
    def _wrap_in_try_except(node: ast.stmt):
        """Wrap a statement in try-except to catch assertion failures."""
        # Create try-except block
        try_node = ast.Try(
            body=[node],
            handlers=[
                ast.ExceptHandler(
                    type=ast.Name(id="Exception", ctx=ast.Load()),
                    name=None,
                    body=[ast.Pass()],
                )
            ],
            orelse=[],
            finalbody=[],
        )
        return ast.copy_location(try_node, node)


class SingleAssertionExtractor(ast.NodeTransformer):
    """
    Extract a single assertion from a test function.
    This creates a clean test with only one assertion (no try-except).
    Handles both module-level functions and class methods.
    REMOVES all other test functions to keep only the target test.
    """

    def __init__(
        self,
        target_test_name: str,
        target_assertion_line: int,
        target_class_name: Optional[str] = None,
    ):
        self.target_test_name = target_test_name
        self.target_assertion_line = target_assertion_line
        self.target_class_name = target_class_name
        self.in_target_function = False
        self.found_target = False
        self.current_class_name = None

    def visit_ClassDef(self, node: ast.ClassDef):
        """Visit class definitions and preserve them."""
        # Any class can contain test methods
        old_class_name = self.current_class_name
        self.current_class_name = node.name
        self.generic_visit(node)
        self.current_class_name = old_class_name
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef):
        """Visit function definitions."""
        if node.name.startswith("test_"):
            # This is a test function
            if (
                self.target_class_name
                and self.current_class_name != self.target_class_name
            ):
                # This is a test function outside the target class
                return None
            if node.name == self.target_test_name:
                # This is the target test in the correct class (or no class filter)
                self.in_target_function = True
                self.found_target = False
                # Visit the body to find and process the target assertion
                new_body = []
                for stmt in node.body:
                    # If we already found the target, stop processing
                    if self.found_target:
                        break
                    # Visit the statement to find assertions (including nested ones)
                    new_stmt = self.visit(stmt)
                    if new_stmt is not None:
                        new_body.append(new_stmt)

                node.body = new_body if new_body else [ast.Pass()]
                self.in_target_function = False
                return node
            else:
                # This is NOT the target test - remove it completely
                return None
        # Keep non-test module-level functions (helpers, fixtures, etc.)
        return node

    def visit_Assert(self, node: ast.Assert):
        """Visit assert statements."""
        if self.in_target_function:
            if node.lineno == self.target_assertion_line:
                # This is the target assertion - keep it
                self.found_target = True
                return node
            else:
                # This is not the target assertion - remove it
                return None
        return node

    def visit_Expr(self, node: ast.Expr):
        """Visit expression statements (for assertion method calls like self.assertEqual)."""
        if self.in_target_function and isinstance(node.value, ast.Call):
            func_name = self._get_func_name(node.value.func)
            if func_name and "assert" in func_name.lower():
                # This is an assertion method call
                if node.lineno == self.target_assertion_line:
                    # This is the target assertion - keep it
                    self.found_target = True
                    return node
                else:
                    # This is not the target assertion - remove it
                    return None
        # Not an assertion, keep it
        return self.generic_visit(node) if self.in_target_function else node

    @staticmethod
    def _get_func_name(node):
        """Extract function name from a call node."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return node.attr
        return None


class ParameterReplacer(ast.NodeTransformer):
    """
    Replace parameter references with concrete values in a de-parameterized test.
    Also removes the @pytest.mark.parametrize decorator.
    """

    def __init__(
        self, test_name: str, param_names: List[str], param_values: Dict[str, Any]
    ):
        self.test_name = test_name
        self.param_names = param_names
        self.param_values = param_values
        self.in_target_function = False

    def visit_FunctionDef(self, node: ast.FunctionDef):
        """Remove parametrize decorator and update function signature."""
        if node.name == self.test_name:
            self.in_target_function = True

            # Remove @pytest.mark.parametrize decorator
            new_decorators = []
            for decorator in node.decorator_list:
                if not self._is_parametrize_decorator(decorator):
                    new_decorators.append(decorator)
            node.decorator_list = new_decorators

            # Remove parameter arguments from function signature
            new_args = []
            for arg in node.args.args:
                if arg.arg not in self.param_names:
                    new_args.append(arg)
            node.args.args = new_args

            # Transform the body
            node = self.generic_visit(node)
            self.in_target_function = False
            return node

        return self.generic_visit(node)

    def visit_Name(self, node: ast.Name):
        """Replace parameter names with concrete values."""
        if self.in_target_function and node.id in self.param_names:
            # Replace with constant value
            value = self.param_values.get(node.id)
            if value is not None:
                return ast.Constant(value=value)
        return node

    @staticmethod
    def _is_parametrize_decorator(decorator: ast.expr) -> bool:
        """Check if a decorator is @pytest.mark.parametrize."""
        if isinstance(decorator, ast.Call):
            if isinstance(decorator.func, ast.Attribute):
                if (
                    isinstance(decorator.func.value, ast.Attribute)
                    and isinstance(decorator.func.value.value, ast.Name)
                    and decorator.func.value.value.id == "pytest"
                    and decorator.func.value.attr == "mark"
                    and decorator.func.attr == "parametrize"
                ):
                    return True
        return False


# ============================================================================
# Phase 2: Test Case Slicing
# ============================================================================


# ============================================================================
# Phase 3: Rank Refinement
# ============================================================================


def rank_refinement(
    original_scores: dict[str, float],
    purified_spectra: list[dict[str, bool]],
    technique: str = "combined",
) -> dict[str, float]:
    """
    Refine rankings based on purified test spectra.

    Args:
        original_scores: dictionary mapping statements to suspiciousness scores
        purified_spectra: list of spectra (dicts mapping statements to coverage bools)
        technique: "combined", "ratio_only", or "original_only"

    Returns:
        dictionary mapping statements to refined scores
    """
    if not original_scores:
        return {}

    # Remove duplicate spectra
    unique_spectra = []
    seen = set()
    for spectrum in purified_spectra:
        # Convert to frozen set for hashing
        spectrum_key = frozenset(
            (k, v) for k, v in spectrum.items() if k in original_scores
        )
        if spectrum_key not in seen:
            seen.add(spectrum_key)
            unique_spectra.append(spectrum)

    # Calculate ratio for each statement
    ratios = {}
    num_tests = len(unique_spectra)

    for stmt in original_scores:
        if num_tests == 0:
            ratios[stmt] = 0.0
        else:
            covered = sum(1 for spec in unique_spectra if spec.get(stmt, False))
            ratios[stmt] = covered / num_tests

    # Normalize original scores to [0, 1]
    scores = list(original_scores.values())
    min_score = min(scores) if scores else 0
    max_score = max(scores) if scores else 1
    score_range = max_score - min_score

    normalized = {}
    for stmt, score in original_scores.items():
        if score_range == 0:
            normalized[stmt] = 0.5
        else:
            normalized[stmt] = (score - min_score) / score_range

    # Compute final scores based on technique
    refined = {}
    for stmt in original_scores:
        if technique == "ratio_only":
            refined[stmt] = ratios[stmt]
        elif technique == "original_only":
            refined[stmt] = normalized[stmt]
        else:  # combined
            # score(s) = norm(s) × (1 + ratio(s)) / 2
            refined[stmt] = normalized[stmt] * (1 + ratios[stmt]) / 2

    return refined


# ============================================================================
# Complete Pipeline
# ============================================================================


def _resolve_test_file_path(test_base: Path, test_file_rel: str) -> Path:
    """
    Resolve the actual test file path, handling overlapping paths.

    Examples:
        test_base='tmp/cookiecutter_2/tests', test_file_rel='tests/test_hooks.py'
        -> 'tmp/cookiecutter_2/tests/test_hooks.py'

        test_base='tmp/cookiecutter_2/tests', test_file_rel='test_hooks.py'
        -> 'tmp/cookiecutter_2/tests/test_hooks.py'

        test_base='tmp/cookiecutter_2', test_file_rel='tests/test_hooks.py'
        -> 'tmp/cookiecutter_2/tests/test_hooks.py'

        test_base='tmp/cookiecutter_2/tests/t', test_file_rel='t/test_hooks.py'
        -> 'tmp/cookiecutter_2/tests/t/test_hooks.py'

    Args:
        test_base: Base directory for tests
        test_file_rel: Relative test file path from test identifier

    Returns:
        Resolved absolute path to test file
    """
    test_base = Path(test_base)
    test_file_rel = Path(test_file_rel)

    # Try direct concatenation first
    candidate = test_base / test_file_rel
    if candidate.exists():
        return candidate

    # Handle overlapping paths by finding common suffix/prefix
    # Convert to parts for comparison
    base_parts = test_base.parts
    rel_parts = test_file_rel.parts

    # Check if test_file_rel starts with any suffix of test_base
    # e.g., test_base='tmp/cookiecutter_2/tests', test_file_rel='tests/test_hooks.py'
    # Should match on 'tests' and use 'test_hooks.py'
    for i in range(len(base_parts)):
        base_suffix = base_parts[i:]

        # Check if rel_parts starts with this suffix
        if len(rel_parts) > len(base_suffix):
            if rel_parts[: len(base_suffix)] == base_suffix:
                # Found overlap, use the non-overlapping part
                remaining_parts = rel_parts[len(base_suffix) :]
                candidate = test_base / Path(*remaining_parts)
                if candidate.exists():
                    return candidate

    # If no overlap found, just concatenate
    return test_base / test_file_rel


def _build_sliced_code(
    original_code: str, relevant_lines: Set[int], test_name: str
) -> str:
    """
    Build sliced code from original code and relevant lines.

    This function uses AST-based filtering to preserve syntactic correctness
    while removing irrelevant statements.

    Args:
        original_code: Original test code
        relevant_lines: Set of relevant line numbers (from slicer)
        test_name: Name of the test function

    Returns:
        Sliced code as a string
    """
    tree = ast.parse(original_code)

    # Use StatementFilter to remove irrelevant statements
    filtered_tree = StatementFilter(relevant_lines, test_name).visit(tree)

    # Unparse and return
    return ast.unparse(filtered_tree)


class StatementFilter(ast.NodeTransformer):
    """
    Filter AST to keep only relevant statements based on line numbers.

    This ensures the sliced code remains syntactically valid by:
    - Keeping function/class definitions that contain relevant statements
    - Keeping import statements (they're usually needed)
    - Removing statements not in the relevant set
    """

    def __init__(self, relevant_lines: Set[int], test_name: str):
        self.relevant_lines = relevant_lines
        self.test_name = test_name
        self.in_target_test = False

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Optional[ast.FunctionDef]:
        """Visit function definitions."""
        if node.name == self.test_name:
            # This is our test function, filter its body
            self.in_target_test = True
            node.body = self._filter_statements(node.body)
            self.in_target_test = False
            return node
        elif not self.in_target_test:
            # Keep helper functions/fixtures if they're in relevant lines
            if self._has_relevant_lines(node):
                return node
            return None
        return node

    def visit_AsyncFunctionDef(
        self, node: ast.AsyncFunctionDef
    ) -> Optional[ast.AsyncFunctionDef]:
        """Visit async function definitions."""
        if node.name == self.test_name:
            # This is our test function, filter its body
            self.in_target_test = True
            node.body = self._filter_statements(node.body)
            self.in_target_test = False
            return node
        elif not self.in_target_test:
            # Keep helper functions if they're in relevant lines
            if self._has_relevant_lines(node):
                return node
            return None
        return node

    def visit_ClassDef(self, node: ast.ClassDef) -> Optional[ast.ClassDef]:
        """Visit class definitions - keep if it has relevant content."""
        if self._has_relevant_lines(node):
            return self.generic_visit(node)
        return None

    def visit_Import(self, node: ast.Import) -> ast.Import:
        """Always keep import statements."""
        return node

    def visit_ImportFrom(self, node: ast.ImportFrom) -> ast.ImportFrom:
        """Always keep import statements."""
        return node

    def _filter_statements(self, stmts: List[ast.stmt]) -> List[ast.stmt]:
        """Filter a list of statements to keep only relevant ones."""
        filtered = []
        for stmt in stmts:
            if self._is_relevant(stmt):
                # For compound statements (if, for, while, etc.),
                # recursively filter their bodies
                if isinstance(stmt, (ast.If, ast.While, ast.For, ast.AsyncFor)):
                    stmt.body = self._filter_statements(stmt.body)
                    if hasattr(stmt, "orelse") and stmt.orelse:
                        stmt.orelse = self._filter_statements(stmt.orelse)
                elif isinstance(stmt, ast.With):
                    stmt.body = self._filter_statements(stmt.body)
                elif isinstance(stmt, ast.Try):
                    stmt.body = self._filter_statements(stmt.body)
                    stmt.handlers = [self._filter_handler(h) for h in stmt.handlers]
                    if hasattr(stmt, "orelse") and stmt.orelse:
                        stmt.orelse = self._filter_statements(stmt.orelse)
                    if hasattr(stmt, "finalbody") and stmt.finalbody:
                        stmt.finalbody = self._filter_statements(stmt.finalbody)

                filtered.append(stmt)

        # If no statements remain, add a pass statement to keep syntax valid
        if not filtered:
            filtered.append(ast.Pass())

        return filtered

    def _filter_handler(self, handler: ast.ExceptHandler) -> ast.ExceptHandler:
        """Filter exception handler body."""
        handler.body = self._filter_statements(handler.body)
        return handler

    def _is_relevant(self, node: ast.AST) -> bool:
        """Check if a node is relevant based on its line number."""
        if not hasattr(node, "lineno"):
            return True  # Keep nodes without line numbers (e.g., arguments)

        # Check if this node's line is in the relevant set
        if node.lineno in self.relevant_lines:
            return True

        # For compound statements, check if any child lines are relevant
        if isinstance(
            node, (ast.If, ast.While, ast.For, ast.AsyncFor, ast.With, ast.Try)
        ):
            return self._has_relevant_lines(node)

        return False

    def _has_relevant_lines(self, node: ast.AST) -> bool:
        """Check if a node or any of its children have relevant lines."""
        for child in ast.walk(node):
            if hasattr(child, "lineno") and child.lineno in self.relevant_lines:
                return True
        return False


def purify_tests(
    src_dir: Path,
    dst_dir: Path,
    failing_tests: List[str],
    enable_slicing: bool = False,
    test_base: Optional[Path] = None,
    venv_python: str = "python",
    venv: Optional[dict] = None,
) -> Dict[str, List[Path]]:
    """
    Purify failing tests.

    Args:
        src_dir: Source directory containing tests
        dst_dir: Destination directory for purified tests
        failing_tests: List of failing test identifiers (e.g., "test_file.py::test_name")
        enable_slicing: Whether to enable dynamic slicing
        test_base: Base directory for tests (defaults to src_dir if None)
        venv_python: Path to virtual environment Python (defaults to sys.executable)
        venv: Environment variables for subprocesses (defaults to os.environ)

    Returns:
        Dictionary mapping test identifiers to lists of purified test files
    """
    venv = venv or os.environ.copy()

    # If test_base is not provided, use src_dir
    if test_base is None:
        test_base = src_dir

    # Create destination directory
    dst_dir.mkdir(parents=True, exist_ok=True)

    result = {}

    for test_id in failing_tests:
        # Parse test identifier
        # Format can be:
        #   - file::test_function (2 parts - module-level function)
        #   - file::TestClass::test_method (3 parts - class method)
        #   - file::test_function[param] (2 parts with parameters)
        #   - file::TestClass::test_method[param] (3 parts with parameters)

        # Extract parameter suffix if present (e.g., [1-hello])
        param_suffix = None
        test_id_base = test_id
        if "[" in test_id and test_id.endswith("]"):
            bracket_pos = test_id.rfind("[")
            param_suffix = test_id[bracket_pos + 1 : -1]  # Extract content between [ ]
            test_id_base = test_id[:bracket_pos]  # Remove parameter part

        parts = test_id_base.split("::")
        if len(parts) < 2:
            continue

        test_file_rel = parts[0]

        # Determine if this is a class method or module-level function
        if len(parts) == 3:
            # Class method: file::class::method
            class_name = parts[1]
            test_name = parts[2]
        elif len(parts) == 2:
            # Module-level function: file::function
            class_name = None
            test_name = parts[1]
        else:
            # Unknown format, skip
            continue

        # Resolve the actual test file path
        # Handle overlapping paths between test_base and test_file_rel
        test_file = _resolve_test_file_path(test_base, test_file_rel)

        if not test_file.exists():
            continue

        # Read the test file
        with open(test_file) as f:
            source = f.read()
            tree = ast.parse(source)

        # Find the test function (handles both module-level and class methods)
        finder = FunctionFinder(target_test=test_name)
        finder.visit(tree)

        if test_name not in finder.test_functions:
            continue

        test_func = finder.test_functions[test_name]

        # Check if the test is in the expected class (if class_name is specified)
        if class_name:
            # Verify the test function is inside the expected class
            parent_class = getattr(test_func, "_parent_class", None)
            if parent_class is None or parent_class.name != class_name:
                continue

        # Check if test is parameterized
        param_info = getattr(test_func, "_parametrize_info", None)
        param_values_dict = {}

        if param_info and param_suffix:
            # Parse parameter values from suffix
            # Format can be: "1-hello" for two parameters, or just "1" for one parameter
            param_values_list = param_suffix.split("-")

            # Try to match parameter values
            if len(param_values_list) == len(param_info.param_names):
                for i, param_name in enumerate(param_info.param_names):
                    value_str = param_values_list[i]
                    # Try to convert to appropriate type
                    try:
                        # Try int first
                        param_values_dict[param_name] = int(value_str)
                    except ValueError:
                        # Keep as string
                        param_values_dict[param_name] = value_str

        # Find all assertions
        assertion_finder = AssertionFinder()
        assertion_finder.visit(test_func)

        if not assertion_finder.assertions:
            continue

        # Phase 1: Atomization - Create wrapped versions and check which fail
        failing_assertion_lines = _find_failing_assertions(
            test_file, assertion_finder.assertions, src_dir, venv_python, venv
        )

        # Phase 2: Create single-assertion tests
        purified_files = []

        for assertion_line, _ in assertion_finder.assertions:
            # Only process assertions that actually fail (if we could determine this)
            if (
                failing_assertion_lines
                and assertion_line not in failing_assertion_lines
            ):
                continue

            # Extract single assertion test
            extractor = SingleAssertionExtractor(test_name, assertion_line, class_name)
            single_tree = extractor.visit(ast.parse(source))
            single_code = ast.unparse(single_tree)

            # Apply slicing if enabled
            if enable_slicing:
                # Write temporary file for slicing
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".py", delete=False
                ) as tmp:
                    tmp.write(single_code)
                    tmp_path = Path(tmp.name)

                try:
                    # Find the assertion line in the new file
                    # (it will be different after unparsing)
                    new_tree = ast.parse(single_code)
                    new_finder = FunctionFinder(target_test=test_name)
                    new_finder.visit(new_tree)

                    if test_name in new_finder.test_functions:
                        new_func = new_finder.test_functions[test_name]
                        new_assertion_finder = AssertionFinder()
                        new_assertion_finder.visit(new_func)

                        if new_assertion_finder.assertions:
                            # Should be only one assertion now
                            new_assertion_line = new_assertion_finder.assertions[0][0]

                            # Use PytestSlicer to perform dynamic slicing
                            LOGGER.info(
                                f"Slicing {test_name} at assertion line {new_assertion_line}"
                            )
                            slicer = PytestSlicer(
                                tmp_path, python_executable=venv_python, env=venv
                            )

                            # Build test pattern for pytest
                            test_pattern = f"{tmp_path}::{test_name}"

                            # Perform slicing
                            slice_results = slicer.slice_test(
                                test_pattern=test_pattern,
                                target_line=new_assertion_line,
                            )

                            # Extract sliced code from results
                            if new_assertion_line in slice_results.get("slices", {}):
                                relevant_lines = set(
                                    slice_results["slices"][new_assertion_line][
                                        "relevant_lines"
                                    ]
                                )
                                sliced_code = _build_sliced_code(
                                    single_code, relevant_lines, test_name
                                )
                            else:
                                LOGGER.warning(
                                    f"No slice found for line {new_assertion_line}, "
                                    "keeping original code"
                                )
                                sliced_code = single_code
                        else:
                            sliced_code = single_code
                    else:
                        sliced_code = single_code
                except Exception as e:
                    LOGGER.error(f"Error during slicing: {e}")
                    sliced_code = single_code
                finally:
                    tmp_path.unlink()
            else:
                sliced_code = single_code

            # Apply parameter replacement if test is parameterized
            if param_info and param_values_dict:
                # De-parameterize the test by replacing parameters with concrete values
                param_tree = ast.parse(sliced_code)
                replacer = ParameterReplacer(
                    test_name, param_info.param_names, param_values_dict
                )
                param_tree = replacer.visit(param_tree)
                sliced_code = ast.unparse(param_tree)

            # Create purified test file
            # Include parameter suffix in filename if present
            if param_suffix:
                purified_name = (
                    f"{test_file.stem}_{test_name}_{param_suffix}"
                    f"_assertion_{assertion_line}{test_file.suffix}"
                )
            else:
                purified_name = (
                    f"{test_file.stem}_{test_name}_assertion_{assertion_line}"
                    f"{test_file.suffix}"
                )
            purified_path = dst_dir / purified_name
            purified_path.write_text(sliced_code)
            purified_files.append(purified_path)

        # Copy the original test file to destination and disable the original test
        dst_test_file = dst_dir / test_file_rel
        dst_test_file.parent.mkdir(parents=True, exist_ok=True)

        # Rename the original test function to disable it
        disabler = TestDisabler(test_name, class_name=class_name)
        disabled_tree = disabler.visit(tree)
        dst_test_file.write_text(ast.unparse(disabled_tree))

        result[test_id] = purified_files

    return result


def _find_failing_assertions(
    test_file: Path,
    assertions: list[tuple[int, ast.AST]],
    src_dir: Path,
    venv_python: str = "python",
    venv: Optional[dict] = None,
) -> set[int]:
    """
    Find which assertions actually fail by wrapping others in try-except.
    Returns set of line numbers for failing assertions.
    """
    failing_lines = set()
    venv = venv or os.environ.copy()

    with open(test_file) as f:
        source = f.read()

    for assertion_line, _ in assertions:
        # Create atomized version (wrap other assertions)
        atomizer = AssertionAtomizer(assertion_line)
        atomized_tree = atomizer.visit(ast.parse(source))

        # Write to temp file and run
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tmp:
            tmp.write(ast.unparse(atomized_tree))
            tmp_path = Path(tmp.name)

        try:
            # Run the test with pytest
            result = subprocess.run(
                [venv_python, "-m", "pytest", str(tmp_path), "-v", "--tb=short"],
                capture_output=True,
                text=True,
                cwd=src_dir,
                env=venv,
            )

            # If test fails, this assertion is failing
            if result.returncode != 0:
                failing_lines.add(assertion_line)

        finally:
            tmp_path.unlink()

    # If we couldn't determine any failing assertions, assume all fail
    if not failing_lines:
        failing_lines = {line for line, _ in assertions}

    return failing_lines


class TestDisabler(ast.NodeTransformer):
    """Rename a test function to disable it (handles both module-level and class methods)."""

    def __init__(self, test_name: str, class_name: Optional[str] = None):
        self.test_name = test_name
        self.class_name = class_name
        self.in_target_class = False

    def visit_ClassDef(self, node: ast.ClassDef):
        """Visit class definitions."""
        if self.class_name and node.name == self.class_name:
            self.in_target_class = True
            node = self.generic_visit(node)
            self.in_target_class = False
            return node
        return self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef):
        """Rename the test function."""
        # If we're looking for a class method, only rename inside the target class
        if self.class_name:
            if self.in_target_class and node.name == self.test_name:
                node.name = f"original_{node.name}_disabled"
        # If no class specified, rename module-level functions
        elif node.name == self.test_name:
            node.name = f"original_{node.name}_disabled"
        return node


# ============================================================================
# Complete Pipeline
# ============================================================================
