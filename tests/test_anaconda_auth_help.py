# In this test we will verify the anaconda auth help command and its expected output.

import pytest
from src.common.cli_utils import capture

@pytest.mark.integration
def testAnacondaAuthHelpContainsExpectedSections():
    """
    Ensure `anaconda auth --help` shows:
      • A usage header
      • Options: --version, -V (or -v), and --help
      • Commands: api-key, login, logout, whoami
    """
    # Run the help command and capture its output
    outputBytes, exitCode = capture("anaconda auth --help")
    assert exitCode == 0, f"`anaconda auth --help` failed: exit code {exitCode}"

    helpText = outputBytes.decode().lower()

    # 1) Usage header
    assert "usage: anaconda auth" in helpText, "Missing usage header"

    # 2) Options block
    assert "--version" in helpText, "Missing `--version` option"
    assert "-v" in helpText or "-V" in helpText, "Missing short version flag"
    assert "--help" in helpText, "Missing `--help` option"

    # 3) Commands block
    for command in ("api-key", "login", "logout", "whoami"):
        assert command in helpText, f"Missing command `{command}`"