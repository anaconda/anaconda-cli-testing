# This test verifies the package search functionality in conda, ensuring it uses the expected channel.

import os
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
def test_conda_config_and_search(isolated_conda_env, caplog, ensureConda):
    """Test conda configuration and package search functionality."""
    caplog.set_level("INFO")

    # Step 1: Ensure default channel only
    assert ensure_default_channel_only(), f"Failed to set '{DEFAULT_CHANNEL}' as only channel"

    # Step 2: Search and verify channel
    assert verify_package_search_channel(), f"Package not found in expected '{EXPECTED_CHANNEL}' channel"


def ensure_default_channel_only() -> bool:
    """Ensure only default channel is configured."""
    try:
        out, code = capture("conda config --show channels")
        if code == 0:
            channels = out.decode().strip().split('\n')
            if len(channels) == 1 and channels[0] == f"- {DEFAULT_CHANNEL}":
                return True
        
        # Reset to default channel only
        capture("conda config --remove-key channels")
        _, rc = capture(f"conda config --add channels {DEFAULT_CHANNEL}")
        return rc == 0
    except:
        return False


def verify_package_search_channel() -> bool:
    """Search for package and verify it uses expected channel."""
    try:
        out, code = capture(f"conda search {SEARCH_PACKAGE}")
        if code != 0:
            return False

        lines = out.decode().splitlines()
        
        # Find header line
        header_idx = next((i for i, line in enumerate(lines) 
                          if line.lower().startswith(SEARCH_HEADER_PREFIX)), -1)
        if header_idx == -1:
            pytest.skip(f"No search results found for '{SEARCH_PACKAGE}'")

        # Check all packages are from expected channel
        for line in lines[header_idx + 1:]:
            if line.strip():
                channel = line.split()[-1]
                if channel != EXPECTED_CHANNEL:
                    return False
        
        return True
    except:
        return False