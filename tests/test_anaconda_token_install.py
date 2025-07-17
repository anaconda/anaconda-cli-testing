# This test verifies that 'anaconda token install' with organization flag:

import os
import re
import time
import urllib.parse
import logging
from pathlib import Path
import pytest
from src.common.cli_utils import launch_subprocess, terminate_process

logger = logging.getLogger(__name__)


@pytest.mark.integration
def test_anaconda_token_install_with_oauth(
    ensureConda,
    run_cli_command,
    api_request_context,
    credentials,
    urls,
    page,
    browser,
    cli_runner,
    pw_open_script,
    free_port,
    token_install_env
):
    """
    This test verifies that 'anaconda token install' command:
    1. Runs anaconda token install --org us-conversion
    2. Handles OAuth login when prompted
    3. Responds 'y' to reissue token prompt
    4. Responds 'y' to configure .condarc prompt
    5. Verifies conda search shows packages from repo/main channel
    """
    logger.info("Starting anaconda token install test...")

    # Setup environment
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

                # Perform OAuth login
                page.goto(oauth_url)
                page.wait_for_load_state("networkidle")
                url_state = urllib.parse.parse_qs(
                    urllib.parse.urlparse(oauth_url).query
                ).get("state", [""])[0]

                if url_state:
                    res = api_request_context.post(
                        f"/api/auth/login/password/{url_state}",
                        data=credentials
                    )
                    if res.ok and res.json().get("redirect"):
                        page.goto(res.json()["redirect"])
                        page.wait_for_load_state("networkidle")
                        state["oauth"] = True
                        logger.info("OAuth login completed")
                        time.sleep(5)

            # Handle prompts
            elif any(kw in line.lower() for kw in ["[y/n]", "(y/n)", "reissuing", "proceed"]):
                response_type = "reissue" if not state["reissue"] else "condarc"
                try:
                    token_proc.stdin.write("y\n")
                    token_proc.stdin.flush()
                    state[response_type] = True
                    logger.info(f"Answered 'y' to {response_type} prompt")
                except BrokenPipeError:
                    break

    finally:
        terminate_process(token_proc)

    # Verify all steps completed
    assert state["oauth"], "OAuth login was not completed"
    assert state["reissue"], "Token reissue step not handled"
    assert state["condarc"], "Condarc setup prompt not handled"

    # Verify conda search
    logger.info("\nRunning conda search flask to verify channel configuration...")
    search_proc = launch_subprocess(["conda", "search", "flask"], env)
    search_output, _ = search_proc.communicate(timeout=30)

    packages_found = False
    all_repo_main = True

    for line in search_output.strip().split('\n'):
        if "flask" in line.lower() and "Loading" not in line and "#" not in line:
            packages_found = True
            if "repo/main" not in line:
                all_repo_main = False
                logger.warning(f"Found package not from repo/main: {line}")

    assert packages_found, "Should find flask packages"
    assert all_repo_main, "All packages should be from repo/main channel"
    assert search_proc.returncode == 0, "Conda search should succeed"

    logger.info("Test passed - Token installed and conda search verified!")