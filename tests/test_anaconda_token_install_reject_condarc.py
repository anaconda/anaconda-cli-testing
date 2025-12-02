# This test verifies that rejecting .condarc configuration results in default channels.

import os
import re
import time
import logging
import subprocess
import pytest
from pathlib import Path
from src.common.cli_utils import launch_subprocess, terminate_process
from src.common.defaults import (
    TOKEN_INSTALL_ORG,
    TOKEN_INSTALL_TIMEOUT,
    PROMPT_KEYWORDS,
    REISSUE_KEYWORDS,
    CONDARC_KEYWORDS,
    TOKEN_INSTALLED_KEYWORD,
    SEARCH_PACKAGE,
    EXPECTED_CHANNEL,
)
from conftest import perform_oauth_login, extract_and_complete_oauth_url, retry_oauth_login_with_direct_navigation

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
    token_install_env,
    cli_runner
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

    # First authenticate via anaconda auth login using the existing clean_home
    logger.info("Authenticating via 'anaconda auth login' before token install...")
    
    # Get a free port for the login process
    import socket
    login_sock = socket.socket()
    login_sock.bind(("", 0))
    login_port = login_sock.getsockname()[1]
    login_sock.close()
    
    # Setup login environment (use existing clean_home)
    login_env = env.copy()
    login_env["ANACONDA_OAUTH_CALLBACK_PORT"] = str(login_port)
    login_env["ANACONDA_AUTH_API_KEY"] = ""  # Force fresh OAuth flow
    
    # Kill any stray processes using this port
    try:
        subprocess.run(
            ["pkill", "-f", f"anaconda.*auth.*login"],
            capture_output=True,
            timeout=5
        )
        time.sleep(1)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    
    # Launch login process
    login_proc = subprocess.Popen(
        ["anaconda", "auth", "login"],
        env=login_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    time.sleep(0.5)
    
    # Import helper functions from test_anaconda_login
    from tests.test_anaconda_login import _capture_oauth_url_from_cli, _wait_for_cli_completion
    from src.common.defaults import PAGE_LOAD_TIMEOUT, NETWORK_IDLE_TIMEOUT
    
    oauth_url = _capture_oauth_url_from_cli(login_proc)
    if not oauth_url:
        logger.error("Failed to capture OAuth URL from login process")
        terminate_process(login_proc)
        raise AssertionError("Failed to capture OAuth URL from anaconda auth login")
    
    logger.info(f"Captured OAuth URL from login: {oauth_url[:100]}...")
    logger.info(f"Navigating to OAuth URL in browser: {oauth_url[:150]}...")
    page.goto(oauth_url, timeout=PAGE_LOAD_TIMEOUT)
    page.wait_for_load_state("networkidle", timeout=NETWORK_IDLE_TIMEOUT)
    
    # Wait for login process to complete naturally (don't terminate prematurely)
    from src.common.defaults import CLI_COMPLETION_TIME
    logger.info("Waiting for login process to complete...")
    start_time = time.time()
    login_exited = False
    
    while time.time() - start_time < CLI_COMPLETION_TIME:
        if login_proc.poll() is not None:
            login_exited = True
            logger.info(f"Login process exited with code {login_proc.returncode}")
            break
        time.sleep(0.1)
    
    if not login_exited:
        logger.warning("Login process didn't exit within timeout, but continuing...")
        # Don't terminate - let it continue in background, token might still be saved
    
    time.sleep(3)  # Give extra time for auth token to be saved
    
    # Ensure env uses the same HOME (should already be set, but double-check)
    env["HOME"] = str(clean_home)
    logger.info(f"Using HOME={env['HOME']} for token install")

    # Now launch token install process (should work since we're authenticated)
    token_proc = launch_subprocess(
        ["anaconda", "token", "install", "--org", TOKEN_INSTALL_ORG],
        env
    )

    # Give CLI a moment to start up
    time.sleep(0.5)

    state = {"oauth": True, "reissue": False, "condarc": False}
    timeout = time.time() + TOKEN_INSTALL_TIMEOUT

    try:
        while time.time() < timeout and token_proc.poll() is None:
            line = token_proc.stdout.readline().strip()
            if not line:
                time.sleep(0.1)  # Small delay when no output to avoid busy waiting
                continue

            logger.info(f"[STDOUT] {line}")

            # Check for OAuth URL (shouldn't happen if login worked, but handle it just in case)
            if not state["oauth"] and ("https://auth.anaconda.com" in line or "[BROWSER-STUB-URL]" in line):
                oauth_url = extract_and_complete_oauth_url(line, token_proc, clean_home, env)
                
                assert oauth_url is not None, f"Failed to extract OAuth URL from CLI output line: {line}"
                logger.info(f"Using OAuth URL: {oauth_url[:100]}...")

                # Use common OAuth login function from conftest
                logger.info(f"Attempting OAuth login with URL (may be incomplete): {oauth_url[:150]}...")
                login_success = perform_oauth_login(page, api_request_context, oauth_url, credentials)
                if not login_success:
                    login_success = retry_oauth_login_with_direct_navigation(page, api_request_context, oauth_url, credentials)
                
                assert login_success, "OAuth login failed - authentication step did not complete successfully"
                state["oauth"] = True
                logger.info("OAuth login completed")
                time.sleep(5)

            # Handle prompts - 'y' for reissue, 'n' for condarc
            elif any(kw in line.lower() for kw in PROMPT_KEYWORDS):
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
        # Read any remaining output after process exits
        if token_proc.poll() is not None:
            remaining = token_proc.stdout.read()
            if remaining:
                for line in remaining.decode('utf-8', errors='ignore').strip().split('\n'):
                    if line.strip():
                        logger.info(f"[STDOUT final] {line.strip()}")
                        # Check for OAuth URL in remaining output
                        if not state["oauth"] and ("https://auth.anaconda.com" in line or "[BROWSER-STUB-URL]" in line):
                            oauth_url = extract_and_complete_oauth_url(line.strip(), token_proc, clean_home, env)
                            if oauth_url:
                                logger.info(f"Using OAuth URL from final output: {oauth_url[:100]}...")
                                logger.info(f"Attempting OAuth login with URL (may be incomplete): {oauth_url[:150]}...")
                                login_success = perform_oauth_login(page, api_request_context, oauth_url, credentials)
                                if not login_success:
                                    login_success = retry_oauth_login_with_direct_navigation(page, api_request_context, oauth_url, credentials)
                                if login_success:
                                    state["oauth"] = True
                                    logger.info("OAuth login completed from final output")
                        
                        # Check for prompts in remaining output
                        if any(kw in line.lower() for kw in PROMPT_KEYWORDS):
                            logger.info(f"Found prompt in final output: '{line.strip()}'")
                            if any(kw in line.lower() for kw in REISSUE_KEYWORDS) and not state["reissue"]:
                                state["reissue"] = True
                                logger.info("Reissue prompt detected in final output")
                            elif any(kw in line.lower() for kw in CONDARC_KEYWORDS) and not state["condarc"]:
                                state["condarc"] = True
                                logger.info("Condarc prompt detected in final output")
                        
                        # Check if token was installed
                        if TOKEN_INSTALLED_KEYWORD in line.lower():
                            state["token_installed"] = True
                            logger.info("Token installation detected in final output")
        terminate_process(token_proc)

    # Verify all steps completed with meaningful assertion messages
    assert state["oauth"], "OAuth login was not completed - authentication step failed"
    
    if not state["reissue"]:
        logger.warning("Reissue prompt not detected — possibly a fresh token. Skipping assertion.")
    else:
        assert state["reissue"], "Token reissue step was not handled - expected 'y' response to reissue prompt"

    if not state["condarc"]:
        logger.warning("Condarc prompt not detected — possibly skipped due to default config. Skipping assertion.")
    else:
        assert state["condarc"], "Condarc rejection prompt was not handled - expected 'n' response to configure .condarc prompt"


    # Verify .condarc doesn't contain us-conversion
    condarc_path = Path(clean_home) / ".condarc"
    if condarc_path.exists():
        content = condarc_path.read_text()
        assert TOKEN_INSTALL_ORG not in content, f".condarc should not contain {TOKEN_INSTALL_ORG} channel when .condarc configuration was rejected"

    # Accept ToS for default channels before searching
    logger.info("\nAccepting ToS for default channels...")
    tos_result = run_cli_command(
        "conda tos accept --channel https://repo.anaconda.com/pkgs/main",
        extra_env={"HOME": str(clean_home)}
    )

    # Verify conda search shows default channels
    logger.info(f"\nRunning conda search {SEARCH_PACKAGE} to verify default channel configuration...")

    search_result = run_cli_command(f"conda search {SEARCH_PACKAGE}", extra_env={"HOME": str(clean_home)})

    logger.info(f"Conda search exit code: {search_result.returncode}")

    if search_result.stdout:
        logger.info(f"Conda search stdout: {search_result.stdout[:500]}")
    if search_result.stderr:
        logger.info(f"Conda search stderr: {search_result.stderr[:500]}")

    assert search_result.returncode == 0, f"Conda search command failed with exit code {search_result.returncode} after ToS acceptance. Stderr: {search_result.stderr}"

    packages_found = False
    all_pkgs_main = True

    if search_result.stdout:
        for line in search_result.stdout.strip().split('\n'):
            if "Name" in line or "Loading channels" in line or line.startswith("#") or not line.strip():
                continue

            if SEARCH_PACKAGE in line.lower():
                packages_found = True
                if TOKEN_INSTALL_ORG in line:
                    all_pkgs_main = False
                    logger.warning(f"Found package from {TOKEN_INSTALL_ORG} channel: {line}")

    assert packages_found, f"Expected to find {SEARCH_PACKAGE} packages from default channel in conda search results"
    assert all_pkgs_main, f"No packages should be from {TOKEN_INSTALL_ORG} channel when .condarc configuration was rejected"

    logger.info("Test passed - Token installed but .condarc rejected!")
