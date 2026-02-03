from __future__ import annotations
import ast
import json
import os
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Set, List, Tuple, Optional, Any
from tcp.logger import LOGGER


@dataclass
class Variable:
    name: str
    scope: str

    def __hash__(self):
        return hash((self.name, self.scope))

    def __eq__(self, other):
        return (
            isinstance(other, Variable)
            and self.name == other.name
            and (self.scope == other.scope)
        )


@dataclass
class Statement:
    line: int
    code: str
    defines: Set[Variable] = field(default_factory=set)
    uses: Set[Variable] = field(default_factory=set)
    control_deps: Set[int] = field(default_factory=set)

    def __hash__(self):
        return hash(self.line)


@dataclass
class DependencyGraph:
    statements: Dict[int, Statement] = field(default_factory=dict)
    data_deps: Dict[int, Set[int]] = field(default_factory=lambda: defaultdict(set))
    control_deps: Dict[int, Set[int]] = field(default_factory=lambda: defaultdict(set))
    executed_lines: Set[int] = field(default_factory=set)

    def add_statement(self, stmt: Statement):
        self.statements[stmt.line] = stmt

    def add_data_dependency(self, from_line: int, to_line: int):
        self.data_deps[from_line].add(to_line)

    def add_control_dependency(self, from_line: int, to_line: int):
        self.control_deps[from_line].add(to_line)

    def get_dependencies(self, line: int) -> Set[int]:
        return self.data_deps[line] | self.control_deps[line]

    def backward_slice(self, target_line: int) -> Set[int]:
        relevant = {target_line}
        worklist = [target_line]
        while worklist:
            line = worklist.pop()
            deps = self.get_dependencies(line)
            for dep in deps:
                if dep not in relevant and dep in self.executed_lines:
                    relevant.add(dep)
                    worklist.append(dep)
        return relevant

    def to_dict(self) -> dict:
        return {
            "statements": {
                line: {
                    "code": stmt.code,
                    "defines": [
                        {"name": v.name, "scope": v.scope} for v in stmt.defines
                    ],
                    "uses": [{"name": v.name, "scope": v.scope} for v in stmt.uses],
                }
                for line, stmt in self.statements.items()
            },
            "data_dependencies": {k: list(v) for k, v in self.data_deps.items()},
            "control_dependencies": {k: list(v) for k, v in self.control_deps.items()},
            "executed_lines": list(self.executed_lines),
        }


class VariableTracker(ast.NodeVisitor):

    def __init__(self):
        self.current_scope = "global"
        self.events = []

    def visit_FunctionDef(self, node):
        old_scope = self.current_scope
        self.current_scope = node.name
        self.generic_visit(node)
        self.current_scope = old_scope

    def visit_AsyncFunctionDef(self, node):
        old_scope = self.current_scope
        self.current_scope = node.name
        self.generic_visit(node)
        self.current_scope = old_scope

    def visit_Attribute(self, node):
        if isinstance(node.ctx, ast.Store):
            self.events.append(
                (node.lineno, "def", ast.unparse(node), self.current_scope)
            )
        elif isinstance(node.ctx, ast.Load):
            self.events.append(
                (node.lineno, "use", ast.unparse(node), self.current_scope)
            )
        self.generic_visit(node)

    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Store):
            self.events.append((node.lineno, "def", node.id, self.current_scope))
        elif isinstance(node.ctx, ast.Load):
            self.events.append((node.lineno, "use", node.id, self.current_scope))


class FutureImportsFinder(ast.NodeVisitor):
    def __init__(self):
        super().__init__()
        self.has_future_import = False
        self.future_line = 0

    def visit_ImportFrom(self, node):
        if node.module == "__future__":
            self.has_future_import = True
            self.future_line = node.lineno
        self.generic_visit(node)

    def visit_Import(self, node):
        for alias in node.names:
            if alias.name == "__future__":
                self.has_future_import = True
                self.future_line = node.lineno
        self.generic_visit(node)


class CoverageInstrumenter(ast.NodeTransformer):
    def __init__(self, has_future_import=False, future_lineno=0):
        super().__init__()
        self.has_future_import = has_future_import
        self.future_lineno = future_lineno
        self.added_import_os = False

    def visit(self, node):
        if isinstance(node, ast.stmt) and hasattr(node, "lineno") and node.lineno:
            if self.has_future_import and node.lineno <= self.future_lineno:
                return self.generic_visit(node)
            tracker = []
            if not self.added_import_os:
                import_os = ast.Import(names=[ast.alias(name="os", asname=None)])
                self.added_import_os = True
                tracker.append(import_os)
            tracker.append(
                ast.Expr(
                    value=ast.Call(
                        func=ast.Attribute(
                            value=ast.Attribute(
                                value=ast.Name(id="os", ctx=ast.Load()),
                                attr="pcov_lines",
                                ctx=ast.Load(),
                            ),
                            attr="add",
                            ctx=ast.Load(),
                        ),
                        args=[ast.Constant(value=node.lineno)],
                        keywords=[],
                    )
                )
            )
            visited = self.generic_visit(node)
            if isinstance(visited, list):
                return [tracker] + visited
            else:
                return [tracker, visited]
        return self.generic_visit(node)


class DynamicTracer:

    def __init__(
        self,
        test_file: Path,
        python_executable: str = None,
        env: Optional[Dict[str, str]] = None,
        base_dir: Optional[Path] = None,
    ):
        self.test_file = test_file
        self.base_dir = base_dir or test_file.parent
        self.graph = DependencyGraph()
        self.python_executable = python_executable or sys.executable
        self.env = env
        self.var_definitions: Dict[Variable, int] = {}

    def trace_execution(self, test_pattern: Optional[str] = None) -> DependencyGraph:
        LOGGER.info(f"Analyzing test file: {self.test_file}")
        with open(self.test_file) as f:
            source_code = f.read()
            tree = ast.parse(source_code)
        LOGGER.debug("Extracting variable definitions and uses (static analysis)")
        tracker = VariableTracker()
        tracker.visit(tree)
        variable_events = tracker.events
        LOGGER.debug(f"Found {len(variable_events)} variable events")
        import uuid

        future_finder = FutureImportsFinder()
        future_finder.visit(tree)
        instrumenter = CoverageInstrumenter(
            has_future_import=future_finder.has_future_import,
            future_lineno=future_finder.future_line,
        )
        instrumented_tree = instrumenter.visit(tree)
        with open(self.test_file, "w") as f:
            f.write(ast.unparse(instrumented_tree))

        coverage_filename = f"tmp_coverage_{uuid.uuid4().hex[:8]}"
        coverage_data_file = (self.test_file.parent / coverage_filename).resolve()
        try:
            test_file_abs = self.test_file.resolve()
            tcpcov_py = Path(__file__).parent.absolute() / "pcov.py"
            cmd = [
                self.python_executable,
                str(tcpcov_py),
                f"--src={self.test_file.name}",
                "-m",
                "pytest",
                (
                    f"{test_file_abs}::{test_pattern}"
                    if test_pattern
                    else str(test_file_abs)
                ),
                "-q",
            ]
            env = (self.env or os.environ).copy()
            env["TCP_COVERAGE_FILE"] = str(coverage_data_file)
            try:
                LOGGER.debug(f"Running coverage: {test_pattern or 'all tests'}")
                LOGGER.debug(f"Working directory: {self.base_dir}")
                LOGGER.debug(f"Test file: {test_file_abs}")
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    env=env,
                    cwd=self.base_dir,
                )
                LOGGER.debug(f"Coverage collection completed (rc={result.returncode})")
                if result.returncode != 0:
                    LOGGER.debug(f"stderr: {result.stderr}")
            except subprocess.TimeoutExpired:
                LOGGER.error("Coverage collection timed out")
                raise
            except Exception as e:
                LOGGER.error(f"Coverage collection failed: {e}")
                raise
            try:
                executed_lines = self._parse_coverage_data(coverage_data_file)
                LOGGER.debug(f"Captured {len(executed_lines)} executed lines")
                trace_data = {"executed_lines": sorted(executed_lines)}
                self._build_graph_from_trace(trace_data, variable_events, source_code)
            except Exception as e:
                LOGGER.error(f"Failed to parse coverage data: {e}")
                raise
        finally:
            coverage_data_file.unlink(missing_ok=True)
            with open(self.test_file, "w") as f:
                f.write(source_code)
        LOGGER.debug("Adding control dependencies (static analysis)")
        self._add_control_dependencies()
        LOGGER.info(
            f"Dependency graph built: {len(self.graph.statements)} statements, {len(self.graph.executed_lines)} executed lines"
        )
        return self.graph

    def _parse_coverage_data(self, coverage_file: Path) -> Set[int]:
        if not coverage_file.exists():
            LOGGER.warning(f"Coverage file not found: {coverage_file}")
            return set()
        try:
            with open(coverage_file) as f:
                data = json.load(f)
            for file in data:
                if Path(file).name == self.test_file.name:
                    return set(data[file])
            LOGGER.warning("Coverage data for test file not found in coverage file")
            return set()
        except Exception as e:
            LOGGER.error(f"Failed to parse coverage data: {e}")
            return set()

    def _build_graph_from_trace(
        self, trace_data: Dict, variable_events: List[Tuple], source_code: str
    ):
        source_lines = source_code.splitlines()
        for line in trace_data["executed_lines"]:
            self.graph.executed_lines.add(line)
        var_events_by_line = defaultdict(list)
        for line, event_type, var_name, scope in variable_events:
            var_events_by_line[line].append((event_type, var_name, scope))
        for line in trace_data["executed_lines"]:
            if 0 <= line - 1 < len(source_lines):
                code = source_lines[line - 1].strip()
                stmt = Statement(line=line, code=code)
                if line in var_events_by_line:
                    for event_type, var_name, scope in var_events_by_line[line]:
                        var = Variable(var_name, scope)
                        if event_type == "def":
                            stmt.defines.add(var)
                            self.var_definitions[var] = line
                        elif event_type == "use":
                            stmt.uses.add(var)
                            if var in self.var_definitions:
                                def_line = self.var_definitions[var]
                                self.graph.add_data_dependency(line, def_line)
                self.graph.add_statement(stmt)

    def _add_control_dependencies(self):
        with open(self.test_file) as f:
            tree = ast.parse(f.read())
        visitor = ControlFlowVisitor(self.graph)
        visitor.visit(tree)


class ControlFlowVisitor(ast.NodeVisitor):

    def __init__(self, graph: DependencyGraph):
        self.graph = graph
        self.control_stack: List[int] = []

    def visit_If(self, node: ast.If):
        if isinstance(node, ast.AST) and hasattr(node, "lineno"):
            control_line = node.lineno
            self.control_stack.append(control_line)
            for stmt in ast.walk(node):
                if (
                    isinstance(stmt, ast.AST)
                    and hasattr(stmt, "lineno")
                    and (stmt.lineno != control_line)
                ):
                    self.graph.add_control_dependency(stmt.lineno, control_line)
            self.generic_visit(node)
            self.control_stack.pop()

    def visit_For(self, node: ast.For):
        if isinstance(node, ast.AST) and hasattr(node, "lineno"):
            control_line = node.lineno
            self.control_stack.append(control_line)
            for stmt in ast.walk(node):
                if (
                    isinstance(stmt, ast.AST)
                    and hasattr(stmt, "lineno")
                    and (stmt.lineno != control_line)
                ):
                    self.graph.add_control_dependency(stmt.lineno, control_line)
            self.generic_visit(node)
            self.control_stack.pop()

    def visit_While(self, node: ast.While):
        if isinstance(node, ast.AST) and hasattr(node, "lineno"):
            control_line = node.lineno
            self.control_stack.append(control_line)
            for stmt in ast.walk(node):
                if (
                    isinstance(stmt, ast.AST)
                    and hasattr(stmt, "lineno")
                    and (stmt.lineno != control_line)
                ):
                    self.graph.add_control_dependency(stmt.lineno, control_line)
            self.generic_visit(node)
            self.control_stack.pop()

    def visit_With(self, node: ast.With):
        if isinstance(node, ast.AST) and hasattr(node, "lineno"):
            control_line = node.lineno
            self.control_stack.append(control_line)
            for stmt in ast.walk(node):
                if (
                    isinstance(stmt, ast.AST)
                    and hasattr(stmt, "lineno")
                    and (stmt.lineno != control_line)
                ):
                    self.graph.add_control_dependency(stmt.lineno, control_line)
            self.generic_visit(node)
            self.control_stack.pop()


class PytestSlicer:

    def __init__(
        self,
        test_file: Path,
        python_executable: str = None,
        env: Optional[Dict[str, str]] = None,
        base_dir: Optional[Path] = None,
    ):
        self.test_file = test_file
        self.base_dir = base_dir or test_file.parent
        self.tracer = DynamicTracer(test_file, python_executable, env, base_dir)

    def slice_test(
        self, test_pattern: Optional[str] = None, target_line: Optional[int] = None
    ) -> Dict[str, Any]:
        LOGGER.info(
            f"Slicing test: {self.test_file}{('::' + test_pattern if test_pattern else '')}"
        )
        graph = self.tracer.trace_execution(test_pattern)
        if target_line is None:
            target_lines = self._find_assertions(graph)
        else:
            target_lines = [target_line]
        results = {
            "test_file": str(self.test_file),
            "test_pattern": test_pattern,
            "graph": graph.to_dict(),
            "slices": {},
        }
        for line in target_lines:
            if line in graph.executed_lines:
                relevant_lines = graph.backward_slice(line)
                results["slices"][line] = {
                    "target": line,
                    "code": (
                        graph.statements[line].code if line in graph.statements else ""
                    ),
                    "relevant_lines": sorted(relevant_lines),
                    "sliced_code": self._extract_sliced_code(relevant_lines),
                }
        return results

    def _find_assertions(self, graph: DependencyGraph) -> List[int]:
        assertions = []
        for line, stmt in graph.statements.items():
            if "assert" in stmt.code.lower():
                assertions.append(line)
        return assertions

    def _extract_sliced_code(self, relevant_lines: Set[int]) -> str:
        with open(self.test_file) as f:
            source_lines = f.readlines()
        sliced = []
        for i, line in enumerate(source_lines, 1):
            if i in relevant_lines:
                sliced.append(f"{i:4d}: {line.rstrip()}")
        return "\n".join(sliced)
