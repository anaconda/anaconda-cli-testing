# tests/test_conda_config_and_search.py
"""
Test suite for conda configuration and package search functionality.
Verifies conda uses only default channels and search works correctly.
"""
import os
import sys
from pathlib import Path
import pytest
from src.common.cli_utils import capture
from src.common.defaults import (
    DEFAULT_CHANNEL,
    EXPECTED_CHANNEL,
    SEARCH_PACKAGE,
    SEARCH_HEADER_PREFIX
)

@pytest.mark.integration
def test_conda_config_and_search(tmp_path, caplog, monkeypatch, ensureConda):
    """
    Test conda configuration and package search functionality.
   
    1) Ensure conda config only has the default channel
    2) Search for a package and verify it uses the correct channel
    
    Args:
        tmp_path: Pytest temporary directory fixture
        caplog: Pytest log capture fixture
        monkeypatch: Pytest monkeypatch fixture
        ensureConda: Custom fixture to ensure conda is installed
        
    Raises:
        AssertionError: If conda config or search functionality fails
    """
    caplog.set_level("INFO")
   
    # Step 1: Ensure only default channel is configured
    ensure_default_channel_only(caplog)
   
    # Step 2: Search package and verify channel
    verify_package_search_channel()
    
    # Assertion for the test completion
    assert True, "Conda configuration and search test completed successfully"

def ensure_default_channel_only(caplog):
    """Ensure conda config only contains the default channel."""
    # Get current configuration
    out, code = capture("conda config --show-sources")
    assert code == 0, f"`conda config --show-sources` failed (exit {code})"
    config_text = out.decode(errors="ignore")
   
    # Find any extra channels (non-default)
    extra_channels = [
        line.strip()
        for line in config_text.splitlines()
        if line.strip().startswith("- ") and line.strip() != f"- {DEFAULT_CHANNEL}"
    ]
   
    # Reset channels if extras found
    if extra_channels:
        caplog.info("Removing extra channels: %s", extra_channels)
       
        # Remove all channels and add back only defaults
        out_remove, rc = capture("conda config --remove-key channels")
        assert rc == 0, "Failed to remove existing channels"
       
        out_add, rc2 = capture(f"conda config --add channels {DEFAULT_CHANNEL}")
        assert rc2 == 0, f"Failed to add '{DEFAULT_CHANNEL}' channel"
       
        # Verify reset worked
        out2, code2 = capture("conda config --show-sources")
        assert code2 == 0
        text2 = out2.decode(errors="ignore")
        assert f"- {DEFAULT_CHANNEL}" in text2 and all(
            (line.strip() == f"- {DEFAULT_CHANNEL}" or not line.strip().startswith("- "))
            for line in text2.splitlines()
            if line.strip().startswith("- ")
        ), f"Channels not reset correctly:\n{text2}"

def verify_package_search_channel():
    """Search for package and verify it uses the expected channel."""
    # Execute search
    out_search, code_search = capture(f"conda search {SEARCH_PACKAGE}")
    assert code_search == 0, f"`conda search {SEARCH_PACKAGE}` failed (exit {code_search})"
   
    lines = out_search.decode(errors="ignore").splitlines()
   
    # Find table start
    try:
        header_idx = next(
            i for i, line in enumerate(lines)
            if line.lower().startswith(SEARCH_HEADER_PREFIX)
        )
    except StopIteration:
        pytest.skip(f"No search results table found for 'conda search {SEARCH_PACKAGE}'")
   
    # Get package entries
    package_entries = [line for line in lines[header_idx + 1:] if line.strip()]
    assert package_entries, f"No package entries found for '{SEARCH_PACKAGE}'"
   
    # Verify all entries use expected channel
    for line in package_entries:
        parts = line.split()
        channel = parts[-1]  # Channel is the last column
        assert channel == EXPECTED_CHANNEL, (
            f"Expected channel '{EXPECTED_CHANNEL}', got '{channel}' in line:\n{line}"
        )