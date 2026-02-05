import ast
import hashlib
import os
import re
import shutil
import string
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Set
from tcp.logger import LOGGER
from tcp.slicer import PytestSlicer


def safe_name(s: str):
    s = s.encode("ascii", "ignore")
    if len(s) > 255:
        return hashlib.md5(s).hexdigest()
    s = s.decode("ascii")
    for c in string.punctuation:
        if c in s:
            s = s.replace(c, "_")
    s = s.replace(" ", "_")
    return s


class AtomizedTest:

    def __init__(
        self,
        code: str,
        assertion_line: Optional[int],
        test_name: str,
        class_name: Optional[str] = None,
        failing_line: Optional[int] = None,
    ):
        self.code = code
        self.assertion_line = assertion_line
        if failing_line is not None:
            self.failing_line = failing_line
        elif assertion_line is not None:
            self.failing_line = assertion_line
        else:
            self.failing_line = None
        self.test_name = test_name
        self.class_name = class_name


class ParameterizeInfo:

    def __init__(self, param_names: list[str], param_values: list):
        self.param_names = param_names
        self.param_values = param_values


class ParameterizeFinder(ast.NodeVisitor):

    def __init__(self):
        self.parametrize_info: Optional[ParameterizeInfo] = None

    @staticmethod
    def extract_parametrize_info(decorator: ast.expr) -> Optional[ParameterizeInfo]:
        if not isinstance(decorator, ast.Call):
            return None
        if isinstance(decorator.func, ast.Attribute):
            if (
                isinstance(decorator.func.value, ast.Attribute)
                and isinstance(decorator.func.value.value, ast.Name)
                and (decorator.func.value.value.id == "pytest")
                and (decorator.func.value.attr == "mark")
                and (decorator.func.attr == "parametrize")
            ):
                if len(decorator.args) >= 2:
                    param_names_node = decorator.args[0]
                    if isinstance(param_names_node, ast.Constant):
                        param_names_str = param_names_node.value
                        param_names = [
                            name.strip() for name in param_names_str.split(",")
                        ]
                    else:
                        return None
                    return ParameterizeInfo(param_names, [])
        return None


class AssertionFinder(ast.NodeVisitor):

    def __init__(self):
        self.assertions: list[tuple[int, ast.AST]] = []

    def visit_Assert(self, node: ast.Assert):
        self.assertions.append((node.lineno, node))
        self.generic_visit(node)

    def visit_Expr(self, node: ast.Expr):
        if isinstance(node.value, ast.Call):
            func_name = self._get_func_name(node.value.func)
            if func_name and "assert" in func_name.lower():
                self.assertions.append((node.lineno, node))
        self.generic_visit(node)

    @staticmethod
    def _get_func_name(node):
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return node.attr
        return None


class FunctionFinder(ast.NodeVisitor):

    def __init__(
        self, target_test: Optional[str] = None, target_class: Optional[str] = None
    ):
        # Store functions with composite key (class_name, function_name)
        # class_name is None for module-level functions
        self.test_functions: dict[tuple[Optional[str], str], ast.FunctionDef] = {}
        self.test_classes: dict[str, ast.ClassDef] = {}
        self.target_test = target_test
        self.target_class = target_class
        self.current_class = None

    def visit_ClassDef(self, node: ast.ClassDef):
        old_class = self.current_class
        self.current_class = node
        self.test_classes[node.name] = node
        self.generic_visit(node)
        self.current_class = old_class

    def visit_FunctionDef(self, node: ast.FunctionDef):
        if node.name.startswith("test_"):
            # Check if this matches our target criteria
            if self.target_test is not None and node.name != self.target_test:
                self.generic_visit(node)
                return

            current_class_name = self.current_class.name if self.current_class else None

            # If we have a target class, only collect from that class
            if (
                self.target_class is not None
                and current_class_name != self.target_class
            ):
                self.generic_visit(node)
                return

            # Store with composite key
            key = (current_class_name, node.name)
            self.test_functions[key] = node

            if self.current_class is not None:
                node._parent_class = self.current_class

            param_info = None
            for decorator in node.decorator_list:
                param_info = ParameterizeFinder.extract_parametrize_info(decorator)
                if param_info:
                    break
            node._parametrize_info = param_info
        self.generic_visit(node)


class AssertionAtomizer(ast.NodeTransformer):

    def __init__(self, target_assertion_line: int):
        self.target_assertion_line = target_assertion_line
        self.in_target_function = False
        self.in_class = False

    def visit_ClassDef(self, node: ast.ClassDef):
        self.in_class = True
        node = self.generic_visit(node)
        self.in_class = False
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef):
        if node.name.startswith("test_"):
            self.in_target_function = True
            node = self.generic_visit(node)
            self.in_target_function = False
            return node
        elif self.in_class:
            return self.generic_visit(node)
        return node

    def visit_Assert(self, node: ast.Assert):
        if self.in_target_function and node.lineno != self.target_assertion_line:
            try_node = ast.Try(
                body=[node],
                handlers=[ast.ExceptHandler(type=None, name=None, body=[ast.Pass()])],
                orelse=[],
                finalbody=[],
            )
            return ast.copy_location(try_node, node)
        return node

    def visit_Expr(self, node: ast.Expr):
        if self.in_target_function and isinstance(node.value, ast.Call):
            func_name = self._get_func_name(node.value.func)
            if func_name and "assert" in func_name.lower():
                if node.lineno != self.target_assertion_line:
                    try_node = ast.Try(
                        body=[node],
                        handlers=[
                            ast.ExceptHandler(type=None, name=None, body=[ast.Pass()])
                        ],
                        orelse=[],
                        finalbody=[],
                    )
                    return ast.copy_location(try_node, node)
        return node

    @staticmethod
    def _get_func_name(node):
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return node.attr
        return None


class SingleAssertionExtractor(ast.NodeTransformer):

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
        old_class_name = self.current_class_name
        self.current_class_name = node.name
        self.generic_visit(node)
        self.current_class_name = old_class_name
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef):
        if node.name.startswith("test_"):
            if (
                self.target_class_name
                and self.current_class_name != self.target_class_name
            ):
                return None
            if node.name == self.target_test_name:
                self.in_target_function = True
                self.found_target = False
                new_body = []
                for stmt in node.body:
                    if self.found_target:
                        break
                    new_stmt = self.visit(stmt)
                    if new_stmt is not None:
                        new_body.append(new_stmt)
                node.body = new_body if new_body else [ast.Pass()]
                self.in_target_function = False
                return node
            else:
                return None
        return node

    def visit_Assert(self, node: ast.Assert):
        if self.in_target_function:
            if node.lineno == self.target_assertion_line:
                self.found_target = True
                return node
            else:
                return None
        return node

    def visit_Expr(self, node: ast.Expr):
        if self.in_target_function and isinstance(node.value, ast.Call):
            func_name = self._get_func_name(node.value.func)
            if func_name and "assert" in func_name.lower():
                if node.lineno == self.target_assertion_line:
                    self.found_target = True
                    return node
                else:
                    return None
        return self.generic_visit(node) if self.in_target_function else node

    @staticmethod
    def _get_func_name(node):
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return node.attr
        return None


def rank_refinement(
    original_scores: dict[str, float],
    purified_spectra: list[dict[str, bool]],
    technique: str = "combined",
) -> dict[str, float]:
    if not original_scores:
        return {}
    unique_spectra = []
    seen = set()
    for spectrum in purified_spectra:
        spectrum_key = frozenset(
            ((k, v) for k, v in spectrum.items() if k in original_scores)
        )
        if spectrum_key not in seen:
            seen.add(spectrum_key)
            unique_spectra.append(spectrum)
    ratios = {}
    num_tests = len(unique_spectra)
    for stmt in original_scores:
        if num_tests == 0:
            ratios[stmt] = 0.0
        else:
            covered = sum((1 for spec in unique_spectra if spec.get(stmt, False)))
            ratios[stmt] = covered / num_tests
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
    refined = {}
    for stmt in original_scores:
        if technique == "ratio_only":
            refined[stmt] = ratios[stmt]
        elif technique == "original_only":
            refined[stmt] = normalized[stmt]
        else:
            refined[stmt] = normalized[stmt] * (1 + ratios[stmt]) / 2
    return refined


def _resolve_test_file_path(test_base: Path, test_file_rel: str) -> Path:
    test_base = Path(test_base)
    if test_base.is_file():
        test_base = test_base.parent
    test_file_rel = Path(test_file_rel)
    candidate = test_base / test_file_rel
    if candidate.exists():
        return candidate
    base_parts = test_base.parts
    rel_parts = test_file_rel.parts
    best_candidate = None
    for i in range(len(base_parts)):
        base_suffix = base_parts[i:]
        if len(rel_parts) > len(base_suffix):
            if rel_parts[: len(base_suffix)] == base_suffix:
                remaining_parts = rel_parts[len(base_suffix) :]
                candidate = test_base / Path(*remaining_parts)
                best_candidate = candidate
                if candidate.exists():
                    return candidate
    if best_candidate:
        return best_candidate
    return test_base / test_file_rel


def _remove_other_test_functions(
    original_code: str, test_name: str, class_name: Optional[str] = None
) -> str:
    tree = ast.parse(original_code)
    filtered_tree = TestFunctionFilter(test_name, class_name).visit(tree)
    return ast.unparse(filtered_tree)


def _build_sliced_code(
    original_code: str,
    relevant_lines: Set[int],
    test_name: str,
    class_name: Optional[str] = None,
) -> str:
    tree = ast.parse(original_code)
    filtered_tree = StatementFilter(relevant_lines, test_name, class_name).visit(tree)
    return ast.unparse(filtered_tree)


class TestFunctionFilter(ast.NodeTransformer):

    def __init__(self, test_name: str, class_name: Optional[str] = None):
        self.test_name = test_name
        self.class_name = class_name
        self.in_target_class = False

    def visit_ClassDef(self, node) -> Optional[ast.ClassDef]:
        node = self.generic_visit(node)
        if hasattr(node, "body") and (not node.body):
            node.body = [ast.Pass()]
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Optional[ast.FunctionDef]:
        if node.name == self.test_name:
            return node
        elif node.name.startswith("test_"):
            return None
        return node

    def visit_AsyncFunctionDef(
        self, node: ast.AsyncFunctionDef
    ) -> Optional[ast.AsyncFunctionDef]:
        if node.name == self.test_name:
            return node
        elif node.name.startswith("test_"):
            return None
        return node


class StatementFilter(ast.NodeTransformer):

    def __init__(
        self, relevant_lines: Set[int], test_name: str, class_name: Optional[str] = None
    ):
        self.relevant_lines = relevant_lines
        self.test_name = test_name
        self.class_name = class_name
        self.in_target_test = False

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Optional[ast.FunctionDef]:
        if node.name == self.test_name:
            self.in_target_test = True
            node.body = self._filter_statements(node.body)
            self.in_target_test = False
            return node
        elif not self.in_target_test and node.name.startswith("test_"):
            return None
        return node

    def visit_AsyncFunctionDef(
        self, node: ast.AsyncFunctionDef
    ) -> Optional[ast.AsyncFunctionDef]:
        if node.name == self.test_name:
            self.in_target_test = True
            node.body = self._filter_statements(node.body)
            self.in_target_test = False
            return node
        elif not self.in_target_test and node.name.startswith("test_"):
            return None
        return node

    def visit(self, node: ast.AST) -> ast.AST:
        node = super().visit(node)
        if hasattr(node, "body") and (not node.body):
            node.body = [ast.Pass()]
        return node

    def visit_Import(self, node: ast.Import) -> ast.Import:
        return node

    def visit_ImportFrom(self, node: ast.ImportFrom) -> ast.ImportFrom:
        return node

    def _filter_statements(self, stmts: List[ast.stmt]) -> List[ast.stmt]:
        filtered = []
        for stmt in stmts:
            if self._is_relevant(stmt):
                if isinstance(stmt, (ast.If, ast.While, ast.For, ast.AsyncFor)):
                    stmt.body = self._filter_statements(stmt.body)
                    if not stmt.body:
                        stmt.body = [ast.Pass()]
                    if hasattr(stmt, "orelse") and stmt.orelse:
                        stmt.orelse = self._filter_statements(stmt.orelse)
                elif isinstance(stmt, ast.With):
                    stmt.body = self._filter_statements(stmt.body)
                    if not stmt.body:
                        stmt.body = [ast.Pass()]
                elif isinstance(stmt, ast.Try):
                    stmt.body = self._filter_statements(stmt.body)
                    if not stmt.body:
                        stmt.body = [ast.Pass()]
                    stmt.handlers = [self._filter_handler(h) for h in stmt.handlers]
                    if hasattr(stmt, "orelse") and stmt.orelse:
                        stmt.orelse = self._filter_statements(stmt.orelse)
                    if hasattr(stmt, "finalbody") and stmt.finalbody:
                        stmt.finalbody = self._filter_statements(stmt.finalbody)
                filtered.append(stmt)
        if not filtered:
            filtered.append(ast.Pass())
        return filtered

    def _filter_handler(self, handler: ast.ExceptHandler) -> ast.ExceptHandler:
        handler.body = self._filter_statements(handler.body)
        return handler

    def _is_relevant(self, node: ast.AST) -> bool:
        if not hasattr(node, "lineno"):
            return True
        if node.lineno in self.relevant_lines:
            return True
        if isinstance(
            node, (ast.If, ast.While, ast.For, ast.AsyncFor, ast.With, ast.Try)
        ):
            return self._has_relevant_lines(node)
        return False

    def _has_relevant_lines(self, node: ast.AST) -> bool:
        if self.in_target_test:
            for child in ast.walk(node):
                if hasattr(child, "lineno") and child.lineno in self.relevant_lines:
                    return True
            return False
        return True


def _install_and_verify_packages(venv_python: str, venv: dict[str, str]):
    if venv_python is None:
        venv_python = "python"
    result = subprocess.run(
        [venv_python, "-c", "import sys; print(sys.executable)"],
        capture_output=True,
        text=True,
        env=venv,
    )
    if result.returncode != 0:
        LOGGER.error(
            f"Failed to get python executable in virtual environment: {result.stderr}"
        )
        raise RuntimeError("Failed to get python executable in virtual environment")
    venv_python = result.stdout.strip()
    result = subprocess.run(
        [venv_python, "-m", "pytest", "--help"],
        capture_output=True,
        text=True,
        env=venv,
    )
    if result.returncode != 0:
        LOGGER.info("pytest not found in virtual environment, installing...")
        install_result = subprocess.run(
            [
                venv_python,
                "-m",
                "pip",
                "install",
                "pytest",
                "--upgrade-strategy",
                "only-if-needed",
            ],
            capture_output=True,
            text=True,
            env=venv,
        )
        if install_result.returncode != 0:
            LOGGER.error(f"Failed to install pytest: {install_result.stderr}")
            raise RuntimeError(
                "Failed to install required packages in virtual environment"
            )
        LOGGER.info("Successfully installed pytest")
        return venv_python
    return venv_python


def purify_tests(
    src_dir: Path,
    dst_dir: Path,
    failing_tests: List[str],
    enable_slicing: bool = False,
    test_base: Optional[Path] = None,
    venv_python: str = None,
    venv: Optional[dict] = None,
) -> Dict[str, List[tuple[Path, Optional[str]]]]:
    if venv is None:
        venv_python = sys.executable
    venv = venv or os.environ.copy()
    venv_python = _install_and_verify_packages(venv_python, venv)
    if test_base is None:
        test_base = src_dir
    shutil.rmtree(dst_dir, ignore_errors=True)
    dst_dir.mkdir(parents=True, exist_ok=True)
    result = {}
    deactivate_tests: dict[str, tuple[ast.AST, list[tuple[Optional[str], str]]]] = {}
    successfully_purified: dict[str, set[tuple[Optional[str], str]]] = {}
    for test_id in failing_tests:
        param_suffix = None
        test_id_base = test_id
        if "[" in test_id and test_id.endswith("]"):
            bracket_pos = test_id.rfind("[")
            param_suffix = test_id[bracket_pos + 1 : -1]
            test_id_base = test_id[:bracket_pos]
        parts = test_id_base.split("::")
        if len(parts) < 2:
            continue
        test_file_rel = parts[0]
        if len(parts) == 3:
            class_name = parts[1]
            test_name = parts[2]
            test_pattern = f"{class_name}::{test_name}"
        elif len(parts) == 2:
            class_name = None
            test_name = parts[1]
            test_pattern = test_name
        else:
            continue
        if param_suffix is not None:
            test_pattern += f"[{param_suffix}]"
        test_file = _resolve_test_file_path(test_base, test_file_rel)
        if not test_file.exists():
            continue
        try:
            test_file_rel_to_base = test_file.relative_to(test_base)
        except ValueError:
            test_file_rel_to_base = Path(test_file_rel)
        with open(test_file) as f:
            source = f.read()
            tree = ast.parse(source)
        test_file_key = str(test_file_rel_to_base)
        if test_file_key not in deactivate_tests:
            deactivate_tests[test_file_key] = (tree, [(class_name, test_name)])
        else:
            deactivate_tests[test_file_key][1].append((class_name, test_name))
        finder = FunctionFinder(target_test=test_name, target_class=class_name)
        finder.visit(tree)
        # Use composite key to look up the test function
        test_func_key = (class_name, test_name)
        if test_func_key not in finder.test_functions:
            continue
        test_func = finder.test_functions[test_func_key]
        param_info = getattr(test_func, "_parametrize_info", None)
        param_values_dict = {}
        if param_info and param_suffix:
            param_values_list = param_suffix.split("-")
            if len(param_values_list) == len(param_info.param_names):
                for i, param_name in enumerate(param_info.param_names):
                    value_str = param_values_list[i]
                    try:
                        param_values_dict[param_name] = int(value_str)
                    except ValueError:
                        param_values_dict[param_name] = value_str
        assertion_finder = AssertionFinder()
        assertion_finder.visit(test_func)
        if not assertion_finder.assertions:
            atomized_tests = _find_failing_line_for_test_without_assertions(
                test_file,
                test_pattern,
                src_dir,
                venv_python,
                venv,
            )
        else:
            atomized_tests = _find_failing_assertions(
                test_file,
                assertion_finder.assertions,
                test_pattern,
                src_dir,
                venv_python,
                venv,
            )
        purified_files = []
        for assertion_line, atomized_test in atomized_tests.items():
            code = atomized_test.code
            if enable_slicing:
                import uuid

                tmp_filename = f"tmp_slice_{uuid.uuid4().hex[:8]}_{test_file.name}"
                tmp_path = (test_file.parent / tmp_filename).resolve()
                tmp_path.write_text(code)
                try:
                    slice_target_line = atomized_test.failing_line
                    LOGGER.info(
                        f"Slicing {test_name} at line {slice_target_line} (assertion at line {assertion_line})"
                    )
                    slicer = PytestSlicer(
                        tmp_path,
                        python_executable=venv_python,
                        env=venv,
                        base_dir=src_dir,
                    )
                    slice_results = slicer.slice_test(
                        test_pattern=test_pattern, target_line=slice_target_line
                    )
                    if slice_target_line in slice_results.get("slices", {}):
                        relevant_lines = set(
                            slice_results["slices"][slice_target_line]["relevant_lines"]
                        )
                        sliced_code = _build_sliced_code(
                            code, relevant_lines, test_name, class_name
                        )
                        if not _test_code_fails(
                            sliced_code,
                            test_file,
                            test_pattern,
                            src_dir,
                            venv_python,
                            venv,
                        ):
                            LOGGER.warning(
                                f"Sliced code for line {slice_target_line} does not fail, removing other test functions but keeping atomized code"
                            )
                            sliced_code = _remove_other_test_functions(
                                code, test_name, class_name
                            )
                            if not _test_code_fails(
                                sliced_code,
                                test_file,
                                test_pattern,
                                src_dir,
                                venv_python,
                                venv,
                            ):
                                LOGGER.error(
                                    f"Purified code for test {test_id} does not fail after removing other test functions"
                                )
                                sliced_code = code
                    else:
                        LOGGER.warning(
                            f"No slice found for line {slice_target_line}, removing other test functions but keeping atomized code"
                        )
                        sliced_code = _remove_other_test_functions(
                            code, test_name, class_name
                        )
                        if not _test_code_fails(
                            sliced_code,
                            test_file,
                            test_pattern,
                            src_dir,
                            venv_python,
                            venv,
                        ):
                            LOGGER.error(
                                f"Purified code for test {test_id} does not fail after removing other test functions"
                            )
                            sliced_code = code
                except Exception as e:
                    LOGGER.error(f"Error during slicing: {e}")
                    sliced_code = _remove_other_test_functions(
                        code, test_name, class_name
                    )
                    if not _test_code_fails(
                        sliced_code,
                        test_file,
                        test_pattern,
                        src_dir,
                        venv_python,
                        venv,
                    ):
                        LOGGER.error(
                            f"Purified code for test {test_id} does not fail after removing other test functions"
                        )
                        sliced_code = code
                finally:
                    tmp_path.unlink(missing_ok=True)
            else:
                sliced_code = _remove_other_test_functions(code, test_name, class_name)
                if not _test_code_fails(
                    sliced_code,
                    test_file,
                    test_pattern,
                    src_dir,
                    venv_python,
                    venv,
                ):
                    LOGGER.error(
                        f"Purified code for test {test_id} does not fail after removing other test functions"
                    )
                    sliced_code = code
            if param_suffix:
                purified_name = (
                    safe_name(
                        f"{test_file.stem}_{test_name}_{param_suffix}_assertion_{assertion_line}"
                    )
                    + f"{test_file.suffix}"
                )
            else:
                purified_name = (
                    safe_name(
                        f"{test_file.stem}_{test_name}_assertion_{assertion_line}"
                    )
                    + f"{test_file.suffix}"
                )
            test_subdir = Path(test_file_key).parent
            purified_path = dst_dir / test_subdir / purified_name
            purified_path.parent.mkdir(parents=True, exist_ok=True)
            purified_path.write_text(sliced_code)
            purified_files.append((purified_path, param_suffix))
        if purified_files:
            result[test_id] = purified_files
            if test_file_key not in successfully_purified:
                successfully_purified[test_file_key] = set()
            successfully_purified[test_file_key].add((class_name, test_name))
        else:
            dst_test_file = dst_dir / test_file_key
            result[test_id] = [(dst_test_file, param_suffix)]
    for test_file_rel, (tree, tests) in deactivate_tests.items():
        dst_test_file = dst_dir / test_file_rel
        dst_test_file.parent.mkdir(parents=True, exist_ok=True)
        tests_to_disable = []
        if test_file_rel in successfully_purified:
            purified_tests = successfully_purified[test_file_rel]
            tests_to_disable = [test for test in tests if test in purified_tests]
        if tests_to_disable:
            disabler = TestDisabler(tests_to_disable)
            disabled_tree = disabler.visit(tree)
            dst_test_file.write_text(ast.unparse(disabled_tree))
        else:
            dst_test_file.write_text(ast.unparse(tree))
    return result


def _extract_failing_line_from_junit_xml(
    junit_xml_path: Path, test_file_path: Path, assertions: list[tuple[int, ast.AST]]
) -> Optional[int]:
    try:
        tree = ET.parse(junit_xml_path)
        root = tree.getroot()
        for testcase in root.iter("testcase"):
            failure = testcase.find("failure")
            error = testcase.find("error")
            failure_elem = failure if failure is not None else error
            if failure_elem is None:
                continue
            message = failure_elem.get("message", "")
            traceback_text = failure_elem.text or ""
            test_filename = test_file_path.name
            full_text = message + "\n" + traceback_text
            test_file_lines = []
            for line in full_text.split("\n"):
                match = re.search(f"{re.escape(test_filename)}:(\\d+)", line)
                if match:
                    test_file_lines.append(int(match.group(1)))
            if test_file_lines:
                failing_line = test_file_lines[-1]
                return _map_to_assertion_start_line(failing_line, assertions)
            testcase_file = testcase.get("file")
            testcase_line = testcase.get("line")
            if testcase_file and testcase_line:
                if Path(testcase_file).name == test_filename:
                    return int(testcase_line)
        return None
    except (FileNotFoundError, ET.ParseError, KeyError, ValueError, AttributeError):
        return None


def _map_to_assertion_start_line(
    failing_line: int, assertions: list[tuple[int, ast.AST]]
) -> int:
    for assertion_start, assertion_node in assertions:
        if hasattr(assertion_node, "end_lineno") and assertion_node.end_lineno:
            assertion_end = assertion_node.end_lineno
        else:
            assertion_end = assertion_start
        if assertion_start <= failing_line <= assertion_end:
            return assertion_start
    return failing_line


def _test_code_fails(
    code: str,
    test_file: Path,
    test_pattern: str,
    src_dir: Path,
    venv_python: str,
    venv: dict,
) -> bool:
    import uuid

    tmp_filename = f"tmp_test_{uuid.uuid4().hex[:8]}_{test_file.name}"
    tmp_path = (test_file.parent / tmp_filename).resolve()
    tmp_path.write_text(code)

    try:
        test_selector = f"{tmp_path}::{test_pattern}"
        result = subprocess.run(
            [venv_python, "-m", "pytest", test_selector, "-q"],
            capture_output=True,
            text=True,
            cwd=src_dir,
            env=venv,
        )
        return result.returncode != 0
    finally:
        tmp_path.unlink(missing_ok=True)


def _find_failing_line_for_test_without_assertions(
    test_file: Path,
    test_pattern: str,
    src_dir: Path,
    venv_python: str = "python",
    venv: Optional[dict] = None,
) -> dict[int, AtomizedTest]:
    """
    Find the failing line for a test that has no assertions.
    Returns a dict with a single entry using a dummy key (0) since there's no assertion line.
    """
    atomized_tests = {}
    venv = venv or os.environ.copy()

    with open(test_file) as f:
        source = f.read()

    import uuid

    junit_xml_filename = f"tmp_report_{uuid.uuid4().hex[:8]}.xml"
    junit_xml_path = (test_file.parent / junit_xml_filename).resolve()

    try:
        test_selector = f"{test_file.resolve()}::{test_pattern}"
        result = subprocess.run(
            [
                venv_python,
                "-m",
                "pytest",
                test_selector,
                "-q",
                f"--junitxml={junit_xml_path}",
            ],
            capture_output=True,
            text=True,
            cwd=src_dir,
            env=venv,
        )

        if result.returncode != 0:
            # Test failed, extract the failing line
            actual_failing_line = _extract_failing_line_from_junit_xml(
                junit_xml_path, test_file, []
            )

            if actual_failing_line:
                if "::" in test_pattern:
                    parts = test_pattern.split("::")
                    if len(parts) == 2:
                        class_name, test_name = (parts[0], parts[1])
                    else:
                        class_name, test_name = (None, parts[0])
                else:
                    class_name, test_name = (None, test_pattern)

                atomized_test = AtomizedTest(
                    code=source,
                    assertion_line=None,  # No assertion in this test
                    test_name=test_name,
                    class_name=class_name,
                    failing_line=actual_failing_line,
                )
                # Use the failing line as the key since there's no assertion line
                atomized_tests[actual_failing_line] = atomized_test
    finally:
        junit_xml_path.unlink(missing_ok=True)

    return atomized_tests


def _find_failing_assertions(
    test_file: Path,
    assertions: list[tuple[int, ast.AST]],
    test_pattern: str,
    src_dir: Path,
    venv_python: str = "python",
    venv: Optional[dict] = None,
) -> dict[int, AtomizedTest]:
    atomized_tests = {}
    venv = venv or os.environ.copy()
    with open(test_file) as f:
        source = f.read()
    for assertion_line, _ in assertions:
        atomizer = AssertionAtomizer(assertion_line)
        atomized_tree = atomizer.visit(ast.parse(source))
        atomized_code = ast.unparse(atomized_tree)
        import uuid

        tmp_filename = f"tmp_atomized_{uuid.uuid4().hex[:8]}_{test_file.name}"
        tmp_path = (test_file.parent / tmp_filename).resolve()
        tmp_path.write_text(atomized_code)
        junit_xml_filename = f"tmp_report_{uuid.uuid4().hex[:8]}.xml"
        junit_xml_path = (test_file.parent / junit_xml_filename).resolve()
        try:
            test_selector = f"{tmp_path}::{test_pattern}"
            result = subprocess.run(
                [
                    venv_python,
                    "-m",
                    "pytest",
                    test_selector,
                    "-q",
                    f"--junitxml={junit_xml_path}",
                ],
                capture_output=True,
                text=True,
                cwd=src_dir,
                env=venv,
            )
            if result.returncode != 0:
                actual_failing_line = _extract_failing_line_from_junit_xml(
                    junit_xml_path, tmp_path, assertions
                )
                if actual_failing_line:
                    if "::" in test_pattern:
                        parts = test_pattern.split("::")
                        if len(parts) == 2:
                            class_name, test_name = (parts[0], parts[1])
                        else:
                            class_name, test_name = (None, parts[0])
                    else:
                        class_name, test_name = (None, test_pattern)
                    atomized_test = AtomizedTest(
                        code=atomized_code,
                        assertion_line=assertion_line,
                        test_name=test_name,
                        class_name=class_name,
                        failing_line=actual_failing_line,
                    )
                    atomized_tests[assertion_line] = atomized_test
        finally:
            tmp_path.unlink(missing_ok=True)
            junit_xml_path.unlink(missing_ok=True)
    if not atomized_tests:
        for assertion_line, _ in assertions:
            atomizer = AssertionAtomizer(assertion_line)
            atomized_tree = atomizer.visit(ast.parse(source))
            atomized_code = ast.unparse(atomized_tree)
            if "::" in test_pattern:
                parts = test_pattern.split("::")
                if len(parts) == 2:
                    class_name, test_name = (parts[0], parts[1])
                else:
                    class_name, test_name = (None, parts[0])
            else:
                class_name, test_name = (None, test_pattern)
            atomized_test = AtomizedTest(
                code=atomized_code,
                assertion_line=assertion_line,
                test_name=test_name,
                class_name=class_name,
            )
            atomized_tests[assertion_line] = atomized_test
    return atomized_tests


class TestDisabler(ast.NodeTransformer):

    def __init__(self, tests: list[tuple[Optional[str], str]]):
        self.tests = tests
        self.current_class = None

    def visit_ClassDef(self, node: ast.ClassDef):
        old_name = self.current_class
        self.current_class = node.name
        node = self.generic_visit(node)
        self.current_class = old_name
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef):
        for class_name, test_name in self.tests:
            if node.name == test_name:
                if class_name is None or class_name == self.current_class:
                    node.name = f"disabled_{node.name}"
                    break
        return node
