# This test verifies the pacakage search functionality in conda, ensuring it uses the expected channel.

import os
import sys
import logging
from pathlib import Path
import pytest
from src.common.cli_utils import capture
from src.common.defaults import (
    DEFAULT_CHANNEL,
    EXPECTED_CHANNEL,
    SEARCH_PACKAGE,
    SEARCH_HEADER_PREFIX
)

logger = logging.getLogger(__name__)

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
    config_success = ensure_default_channel_only(caplog)
   
    # Step 2: Search package and verify channel
    search_success = verify_package_search_channel()
   
    # Assert both steps completed successfully with meaningful error messages
    assert config_success, f"Step 1 failed: conda configuration could not be set to use only '{DEFAULT_CHANNEL}' channel"
    assert search_success, f"Step 2 failed: package search verification failed - packages not found in expected '{EXPECTED_CHANNEL}' channel"

def ensure_default_channel_only(caplog) -> bool:
    """
    Ensure conda config only contains the default channel.
    
    Returns:
        bool: True if configuration was successful, False otherwise
    """
    try:
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
            logger.info("Removing extra channels: %s", extra_channels)
           
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
        
        return True
        
    except AssertionError:
        return False

def verify_package_search_channel() -> bool:
    """
    Search for package and verify it uses the expected channel.
    
    Returns:
        bool: True if search verification was successful, False otherwise
    """
    try:
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
        
        return True
        
    except (AssertionError, pytest.skip.Exception):
        return False