# In This test, we will verify the `anaconda auth --version` and `-V` commands

import pytest
from src.common.cli_utils import capture

@pytest.mark.integration
@pytest.mark.parametrize(
    "command",
    [
        "anaconda auth --version",
        "anaconda auth -V",
    ],
    ids=["longFlag", "shortFlag"]
)
def testAnacondaAuthReportsExactVersion(command, ensureConda):
    """Ensure `anaconda auth --version` and `-V` succeed and report version 0.8.5."""
    # Run the CLI command and capture its output and exit code
    outputBytes, exitCode = capture(command)
    # 1) Command must exit cleanly
    assert exitCode == 0, (
        f"{command!r} exited with code {exitCode}\n"
        f"stdout:\n{outputBytes.decode()}"
    )

    # 2) Output should include the exact version string
    outputText = outputBytes.decode().strip()
    assert "0.8.5" in outputText, (
        f"Expected version '0.8.5' in output of {command!r}, but got:\n{outputText}"
    )