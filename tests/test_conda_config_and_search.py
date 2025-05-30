# In This test we will look for .condarc file, if there is any thing else than default channel will be removed
# and then we will search the packag in conda search and check if the channel is pkgs/main.

import os
import sys
from pathlib import Path

# ─── Make project root importable ─────────────────────────────────────────────
sys.path.insert(0, os.path.abspath(os.path.join(__file__, "..")))

import pytest
from src.common.cli_utils import capture

@pytest.mark.integration
def test_conda_config_and_search(tmp_path, caplog, monkeypatch,ensureConda):
    """
    1) Ensure `conda config --show-sources` only has the default channel.
       If it contains extra channels, remove them and reset to only 'defaults'.
    2) Run `conda search flask` and verify every listed line uses the 'pkgs/main' channel.
    """
    caplog.set_level("INFO")

    # 1a) Show current sources
    out, code = capture("conda config --show-sources")
    assert code == 0, f"`conda config --show-sources` failed (exit {code})"
    text = out.decode(errors="ignore")

    # If any channel other than 'defaults' is present, reset channels
    # We look for lines under 'channels:' that are not '- defaults'
    extra = [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith("- ") and line.strip() != "- defaults"
    ]
    if extra:
        caplog.info("Removing extra channels: %s", extra)
        # remove all channels
        _, rc = capture("conda config --remove-key channels")
        assert rc == 0, "Failed to remove existing channels"
        # add back only defaults
        _, rc2 = capture("conda config --add channels defaults")
        assert rc2 == 0, "Failed to add 'defaults' channel"

        # re-run show-sources to confirm
        out2, code2 = capture("conda config --show-sources")
        assert code2 == 0
        text2 = out2.decode(errors="ignore")
        assert "- defaults" in text2 and all(
            (line.strip() == "- defaults" or not line.strip().startswith("- "))
            for line in text2.splitlines()
            if line.strip().startswith("- ")
        ), f"Channels not reset correctly:\n{text2}"

    # 2) Search for flask and check channel column
    out_search, code_search = capture("conda search flask")
    assert code_search == 0, f"`conda search flask` failed (exit {code_search})"
    lines = out_search.decode(errors="ignore").splitlines()

    # skip header lines until the table starts (look for header marker '# Name')
    try:
        idx = next(i for i, l in enumerate(lines) if l.lower().startswith("# name"))
    except StopIteration:
        pytest.skip("No search results table found for 'conda search flask'")

    table = lines[idx + 1 :]
    assert table, "No package entries found for 'flask'"

    # Each non-empty data line should have 'pkgs/main' at the end (channel column)
    for line in table:
        if not line.strip():
            continue
        parts = line.split()
        channel = parts[-1]
        assert channel == "pkgs/main", f"Expected channel 'pkgs/main', got '{channel}' in line:\n{line}"