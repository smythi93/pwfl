#!/usr/bin/env python3
"""
Test that purification with slicing produces the correct output.
"""

from pathlib import Path
import tempfile
from tcp.purification import purify_tests

test_code = """
def test_three_calculations():
    a = 1
    b = 2
    sum_result = a + b
    x = 10
    y = 20
    product = x * y
    p = 100
    q = 50
    diff = p - q
    assert sum_result == 3
    assert product == 200
    assert diff == 50
"""

expected_test_0 = """
def test_three_calculations():
    a = 1
    b = 2
    sum_result = a + b
    assert sum_result == 3
"""

expected_test_1 = """
def test_three_calculations():
    x = 10
    y = 20
    product = x * y
    assert product == 200
"""

expected_test_2 = """
def test_three_calculations():
    p = 100
    q = 50
    diff = p - q
    assert diff == 50
"""


def test_purification_with_slicing():

    def normalize(code):
        """Normalize code for comparison."""
        lines = []
        for line in code.split("\n"):
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                lines.append(stripped)
        return "\n".join(lines)

    with tempfile.TemporaryDirectory() as tmpdir:
        src_dir = Path(tmpdir) / "src"
        dst_dir = Path(tmpdir) / "dst"
        src_dir.mkdir()

        test_file = src_dir / "test.py"
        test_file.write_text(test_code)

        result = purify_tests(
            src_dir=src_dir,
            dst_dir=dst_dir,
            failing_tests=["test.py::test_three_calculations"],
            enable_slicing=True,
        )

        purified_files = sorted(result["test.py::test_three_calculations"])

        expected = [expected_test_0, expected_test_1, expected_test_2]

        for idx, pf in enumerate(purified_files):
            actual = pf.read_text()
            expected_code = expected[idx]

            actual_norm = normalize(actual)
            expected_norm = normalize(expected_code)

            assert expected_norm == actual_norm
