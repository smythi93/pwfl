#!/usr/bin/env python
"""
Simple test to verify TCP integration is working.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))


def test_imports():
    """Test that all required modules can be imported."""
    from pwfl.purification import get_tcp_events, purify_and_collect_events
    from tcp import purify_tests
    from pwfl.events import create_config, sflkit_instrument

    # If we got here, all imports succeeded
    assert True


def test_cli():
    """Test that the CLI recognizes the tcp command."""
    from pwfl import get_parser

    parser = get_parser()

    # Test parsing tcp command
    args = parser.parse_args(["tcp", "-p", "test_project", "-i", "1"])

    assert args.command == "tcp", f"Expected 'tcp' command, got '{args.command}'"
    assert args.project_name == "test_project"
    assert args.bug_id == 1
    assert hasattr(args, "enable_slicing")
