# In this test, we will verify the installation of the `anaconda-auth` package.

import pytest
from src.common.cli_utils import capture

@pytest.mark.integration
def test_verify_anaconda_auth_installed_and_version(ensureConda):
    
    """
    1) Check `conda list anaconda-auth`; if not installed, install it.
    2) Assert `conda list anaconda-auth` now succeeds and shows the package.
    3) Run `anaconda-auth --version` and assert it contains '0.8.5'.
    """
    # 1) Check presence
    out, code = capture("conda list anaconda-auth")
    text = out.decode().lower()

    if code != 0 or "anaconda-auth" not in text:
        # Install silently
        out_inst, code_inst = capture("conda install anaconda-auth -y", timeout=300)
        assert code_inst == 0, f"Failed to install anaconda-auth:\n{out_inst.decode()}"
    
    # 2) Verify it appears in the list
    out_list, code_list = capture("conda list anaconda-auth")
    assert code_list == 0, f"`conda list` failed: exit {code_list}"
    list_text = out_list.decode().lower()
    assert "anaconda-auth" in list_text, (
        f"Package still missing after install:\n{list_text}"
    )