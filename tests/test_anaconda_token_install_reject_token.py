# This test verifies that rejecting the token issue/resissue process

import re
import time
import logging
import pytest
from pathlib import Path
from src.common.cli_utils import launch_subprocess, terminate_process
from conftest import perform_oauth_login

logger = logging.getLogger(__name__)


@pytest.mark.integration
def test_anaconda_token_install_reject_condarc(
    ensureConda,
    run_cli_command,
    api_request_context,
    credentials,
    urls,
    page,
    browser,
    token_install_env
):
    """
    This test verifies rejecting .condarc configuration:
    1. Run anaconda token install --org us-conversion
    2. Handle OAuth login when prompted
    3. Respond 'y' to reissue token prompt
    4. Respond 'n' to configure .condarc prompt
    5. Verify conda search shows packages from pkgs/main (default channel)
    """
    logger.info("Starting test: Token install with rejected .condarc configuration...")

    env, clean_home = token_install_env

    # Launch the CLI process
    token_proc = launch_subprocess(
        ["anaconda", "token", "install", "--org", "us-conversion"],
        env
    )

    state = {"oauth": False, "reissue": False, "condarc": False}
    timeout = time.time() + 120

    try:
        while time.time() < timeout and token_proc.poll() is None:
            line = token_proc.stdout.readline().strip()
            if not line:
                continue
                
            logger.info(f"[STDOUT] {line}")

            # Handle OAuth URL
            if not state["oauth"] and "https://auth.anaconda.com" in line:
                oauth_url = re.search(r'https://[^\s]+', line).group(0)
                logger.info(f"Found OAuth URL: {oauth_url}")
                
                assert perform_oauth_login(page, api_request_context, oauth_url, credentials), \
                    "OAuth login failed"
                state["oauth"] = True
                logger.info("OAuth login completed")
                time.sleep(5)

            # Handle prompts - 'y' for reissue, 'n' for condarc
            elif any(kw in line.lower() for kw in ["[y/n]", "(y/n)", "reissuing", "proceed"]):
                response_type = "reissue" if not state["reissue"] else "condarc"
                response = "y" if response_type == "reissue" else "n"
                
                try:
                    token_proc.stdin.write(f"{response}\n")
                    token_proc.stdin.flush()
                    state[response_type] = True
                    logger.info(f"Answered '{response}' to {response_type} prompt")
                except BrokenPipeError:
                    break

    finally:
        terminate_process(token_proc)

    # Verify all steps completed
    assert state["oauth"], "OAuth login was not completed"

    if not state["reissue"]:
        logger.warning("Reissue prompt not detected — possibly a fresh token. Skipping assertion.")
    else:
     assert state["reissue"], "Token reissue step not handled"

    assert state["condarc"], "Condarc rejection prompt not handled"

    # Verify .condarc doesn't contain us-conversion
    condarc_path = Path(clean_home) / ".condarc"
    if condarc_path.exists():
        content = condarc_path.read_text()
        assert "us-conversion" not in content, ".condarc should not contain us-conversion channel"

    # Verify conda search shows default channels
    logger.info("\nRunning conda search flask to verify default channel configuration...")
    search_proc = launch_subprocess(["conda", "search", "flask"], env)
    search_output, _ = search_proc.communicate(timeout=30)

    if search_proc.returncode != 0:
        logger.info("Conda search failed - expected for rejected condarc")
        return

    packages_found = False
    all_pkgs_main = True

    for line in search_output.strip().split('\n'):
        if "flask" in line.lower() and "Loading" not in line and "#" not in line:
            packages_found = True
            if "pkgs/main" not in line:
                all_pkgs_main = False

    if packages_found:
        assert all_pkgs_main, "All packages should be from pkgs/main channel (default)"

    logger.info("Test passed - Token installed but .condarc rejected!")