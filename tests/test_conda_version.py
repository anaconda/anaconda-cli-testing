# In this test, we will verify the `conda info` command

# tests/test_conda_version.py

import re
import pytest
from src.common.cli_utils import capture

@pytest.mark.integration
def test_conda_info_reports_version_and_active_env(ensureConda):
    """
    Ensure `conda info` prints:
      - a semantic version line like 'conda version : X.Y.Z'
      - the 'active environment' section
    """
    # Run `conda info`
    out_bytes, exit_code = capture("conda info")
    assert exit_code == 0, f"`conda info` failed: exit code {exit_code}"

    output = out_bytes.decode()

    # Locate and validate the version line
    for line in output.splitlines():
        stripped = line.strip()  # remove leading/trailing spaces
        if stripped.lower().startswith("conda version"):
            # After the colon, expect X.Y.Z
            version_part = stripped.split(":", 1)[1].strip()
            segments = version_part.split(".")
            assert len(segments) == 3 and all(seg.isdigit() for seg in segments), (
                f"Invalid version format, expected X.Y.Z, got '{version_part}'"
            )
            break
    else:
        pytest.fail("Did not find any line starting with 'conda version'")

    # Check for the active environment section
    assert "active environment" in output.lower(), (
        "Output is missing an 'active environment' section"
    )