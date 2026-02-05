"""
Test to verify that tests without assertions are properly handled.

Previously, tests without assertions were skipped with a continue statement.
Now they are processed to find the failing line and create an atomized test.
"""

import tempfile
from pathlib import Path
from tcp.purification import purify_tests


def test_purify_test_without_assertion():
    """Test that a failing test without assertions is properly purified."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create test file with a test that has no assertion
        test_dir = tmpdir / "tests"
        test_dir.mkdir()
        test_file = test_dir / "test_no_assertion.py"
        test_file.write_text("""def test_failing_without_assertion():
    '''This test has no assertion but fails by raising an exception'''
    x = 1
    y = 2
    z = x + y
    raise ValueError("This test fails without an assertion")
""")

        # Create output directory
        output_dir = tmpdir / "output"

        # Run purify_tests
        failing_tests = ["tests/test_no_assertion.py::test_failing_without_assertion"]

        result = purify_tests(
            src_dir=tmpdir,
            dst_dir=output_dir,
            failing_tests=failing_tests,
            enable_slicing=True,
            test_base=test_dir,
        )

        # Verify that the test was processed
        assert "tests/test_no_assertion.py::test_failing_without_assertion" in result

        # Verify that purified files were created
        purified_files = result[
            "tests/test_no_assertion.py::test_failing_without_assertion"
        ]
        assert len(purified_files) > 0

        # Verify that the purified file exists and contains the test
        purified_file, _ = purified_files[0]
        assert purified_file.exists()

        content = purified_file.read_text()
        assert "test_failing_without_assertion" in content
        assert "raise ValueError" in content
        assert "x = 1" not in content
        assert "y = 2" not in content
        assert "z = x + y" not in content


def test_purify_test_without_assertion_that_passes():
    """Test that a passing test without assertions is handled gracefully."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create test file with a test that has no assertion and passes
        test_dir = tmpdir / "tests"
        test_dir.mkdir()
        test_file = test_dir / "test_passing.py"
        test_file.write_text("""def test_passing_without_assertion():
    '''This test has no assertion and passes'''
    x = 1
    y = 2
    z = x + y
""")

        # Create output directory
        output_dir = tmpdir / "output"

        # Run purify_tests
        failing_tests = ["tests/test_passing.py::test_passing_without_assertion"]

        result = purify_tests(
            src_dir=tmpdir,
            dst_dir=output_dir,
            failing_tests=failing_tests,
            enable_slicing=False,
            test_base=test_dir,
        )

        # Verify that the test was processed (fallback to original file)
        assert "tests/test_passing.py::test_passing_without_assertion" in result

        # Verify that the file exists
        purified_files = result["tests/test_passing.py::test_passing_without_assertion"]
        assert len(purified_files) > 0

        purified_file, _ = purified_files[0]
        assert purified_file.exists()
