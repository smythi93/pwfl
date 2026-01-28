#!/usr/bin/env python
"""
Test to verify purification handles parameterized tests correctly.
"""

import ast
import tempfile
from pathlib import Path

# Test code with parameterized test
TEST_CODE = '''
import pytest

OPTIONS = ['hello', 'world', 'foo', 'bar']

@pytest.mark.parametrize('user_choice, expected_value', enumerate(OPTIONS, 1))
def test_click_invocation(mocker, user_choice, expected_value):
    """Test with parameters."""
    result = process(user_choice)
    assert result == expected_value  # Line 9
    
    other = result * 2
    assert len(other) > 0  # Line 12

def process(value):
    return str(value)
'''


def test_parametrize_finder():
    """Test that ParameterizeFinder can detect parametrize decorator."""
    from tcp.purification import FunctionFinder

    tree = ast.parse(TEST_CODE)
    finder = FunctionFinder(target_test="test_click_invocation")
    finder.visit(tree)

    assert "test_click_invocation" in finder.test_functions
    test_func = finder.test_functions["test_click_invocation"]

    param_info = getattr(test_func, "_parametrize_info", None)

    assert param_info is not None, "Parametrize decorator not detected"
    assert param_info.param_names == ["user_choice", "expected_value"]


def test_parameter_id_parsing():
    """Test parsing parameter values from test ID."""
    # Simulate test ID parsing
    test_id = "test_file.py::test_click_invocation[1-hello]"

    # Extract parameter suffix
    if "[" in test_id and test_id.endswith("]"):
        bracket_pos = test_id.rfind("[")
        param_suffix = test_id[bracket_pos + 1 : -1]
        test_id_base = test_id[:bracket_pos]

        # Parse parameter values
        param_values = param_suffix.split("-")

        assert param_values == ["1", "hello"]


def test_parameter_replacer():
    """Test that ParameterReplacer removes decorator and replaces params."""
    from tcp.purification import ParameterReplacer

    tree = ast.parse(TEST_CODE)
    replacer = ParameterReplacer(
        "test_click_invocation",
        ["user_choice", "expected_value"],
        {"user_choice": 1, "expected_value": "hello"},
    )
    new_tree = replacer.visit(tree)
    new_code = ast.unparse(new_tree)

    # Verify decorator is removed
    assert "@pytest.mark.parametrize" not in new_code

    # Verify function signature changed
    assert "def test_click_invocation(mocker):" in new_code


def test_full_purify_parameterized():
    """Test full purify_tests with parameterized test."""
    from tcp.purification import purify_tests

    # Create temporary directories
    with tempfile.TemporaryDirectory() as tmpdir:
        src_dir = Path(tmpdir) / "src"
        dst_dir = Path(tmpdir) / "dst"
        src_dir.mkdir()
        dst_dir.mkdir()

        # Write test file
        test_file = src_dir / "test_click.py"
        test_file.write_text(TEST_CODE)

        # Test with parameterized identifier
        test_id = "test_click.py::test_click_invocation[1-hello]"

        result = purify_tests(
            src_dir=src_dir,
            dst_dir=dst_dir,
            failing_tests=[test_id],
            enable_slicing=False,
        )

        assert test_id in result, f"Test ID {test_id} not in result"
        purified_files = result[test_id]

        # Should have 2 purified files (one per assertion)
        assert len(purified_files) == 2, f"Expected 2 files, got {len(purified_files)}"

        # Check purified file names include parameter suffix
        for purified_file in purified_files:
            assert "test_click" in purified_file.name
            assert "test_click_invocation" in purified_file.name
            assert "1-hello" in purified_file.name  # Parameter suffix
            assert "assertion" in purified_file.name

            content = purified_file.read_text()
            # Should not have parametrize decorator
            assert "@pytest.mark.parametrize" not in content
