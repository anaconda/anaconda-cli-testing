# This test verifies that the Anaconda Auth package is installed.

import pytest
from src.common.cli_utils import capture
from src.common.defaults   import (
    PACKAGE_NAME,
    CLI_SUBCOMMAND,
    ANACONDA_AUTH_VERSION,
    INSTALL_TIMEOUT,
    LIST_TIMEOUT,
    MAX_RETRIES,
)

@pytest.mark.integration
def test_verify_anaconda_auth_installed_and_version(ensureConda):
    """
    1) `conda list PACKAGE_NAME`; if missing, install it.
    2) Assert `conda list PACKAGE_NAME` now succeeds.
    3) Run `CLI_SUBCOMMAND --version` and assert it contains _ANACONDA_AUTH_VERSION.
    """
    # 1) List & maybe install
    out, code = capture(f"conda list {PACKAGE_NAME}", timeout=LIST_TIMEOUT)
    text = out.decode().lower()
    if code != 0 or PACKAGE_NAME not in text:
        for attempt in range(1, MAX_RETRIES+1):
            out_i, code_i = capture(
                f"conda install {PACKAGE_NAME} -y",
                timeout=INSTALL_TIMEOUT,
            )
            if code_i == 0:
                break
            if attempt == MAX_RETRIES:
                pytest.fail(f"Could not install {PACKAGE_NAME} after {MAX_RETRIES} tries:\n{out_i.decode()}")
    # 2) Verify listing
    out2, code2 = capture(f"conda list {PACKAGE_NAME}", timeout=LIST_TIMEOUT)
    assert code2 == 0, f"`conda list {PACKAGE_NAME}` failed: exit {code2}"
    assert PACKAGE_NAME in out2.decode().lower()

    # 3) Version check via sub-command
    version_out, version_code = capture(f"{CLI_SUBCOMMAND} --version")
    assert version_code == 0, f"`{CLI_SUBCOMMAND} --version` failed (exit {version_code})"
    version_text = version_out.decode().strip()
    assert ANACONDA_AUTH_VERSION in version_text, (
        f"Expected version '{ANACONDA_AUTH_VERSION}' in output of "
        f"`{CLI_SUBCOMMAND} --version`, but got:\n{version_text}"
    )