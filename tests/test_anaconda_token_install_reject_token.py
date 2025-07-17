# tests/test_anaconda_token_install_cancel_reissue.py

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
def test_anaconda_token_install_cancel_reissue(
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
    This test verifies that answering 'n' to token reissue prompt aborts installation:
    1. Run anaconda token install --org us-conversion
    2. Handle OAuth login when prompted
    3. Respond 'n' to reissue token prompt
    4. Verify process aborts and token is NOT installed
    """
    logger.info("Starting anaconda token install cancel test...")

    # Setup environment
    env, clean_home = token_install_env

    # Launch the CLI process
    token_proc = launch_subprocess(
        ["anaconda", "token", "install", "--org", "us-conversion"],
        env
    )

    oauth_completed = False
    cancelled = False
    token_installed = False
    timeout = time.time() + 120

    try:
        while time.time() < timeout and token_proc.poll() is None:
            line = token_proc.stdout.readline().strip()
            if not line:
                continue
                
            logger.info(f"[STDOUT] {line}")

            # Handle OAuth URL
            if not oauth_completed and "https://auth.anaconda.com" in line:
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
                        oauth_completed = True
                        logger.info("OAuth login completed")
                        time.sleep(5)

            # Answer 'n' to first prompt (reissue prompt)
            elif not cancelled and any(kw in line.lower() for kw in ["[y/n]", "(y/n)", "reissuing", "proceed"]):
                logger.info(f"Found prompt: {line}")
                try:
                    token_proc.stdin.write("n\n")
                    token_proc.stdin.flush()
                    cancelled = True
                    logger.info("Answered 'n' to cancel token reissue")
                except BrokenPipeError:
                    break

            # Check if token was installed (shouldn't happen)
            elif "success!" in line.lower() and "token has been installed" in line.lower():
                token_installed = True
                logger.warning("Token was installed despite cancellation!")

    finally:
        terminate_process(token_proc)

    logger.info(f"\nResults: Exit code: {token_proc.returncode}, OAuth: {oauth_completed}, "
                f"Cancelled: {cancelled}, Token installed: {token_installed}")

    # Verify expected behavior
    assert oauth_completed, "Should handle OAuth login"
    assert cancelled, "Should have answered 'n' to the reissue prompt"
    assert not token_installed, "Token should NOT be installed after cancellation"
    assert token_proc.returncode != 0, "Should exit with non-zero code when cancelled"

    logger.info("Test passed - Token installation was properly cancelled.")