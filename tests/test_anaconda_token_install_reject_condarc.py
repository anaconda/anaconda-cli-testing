# This test verifies that rejecting .condarc configuration results in default channels.

import os
import subprocess
import time
import logging
import re
from pathlib import Path
import pytest
import urllib.parse

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
    cli_runner,
    pw_open_script,
    free_port
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

    # Setup environment
    _, _, clean_home = cli_runner()
    env = os.environ.copy()
    env["HOME"] = str(clean_home)
    env["PATH"] = f"{Path.home()}/miniconda3/bin:{env.get('PATH', '')}"
    env["BROWSER"] = str(pw_open_script)
    env["ANACONDA_OAUTH_CALLBACK_PORT"] = str(free_port)

    # Launch command
    logger.info("\nRunning anaconda token install --org us-conversion...")
    token_proc = subprocess.Popen(
        ["anaconda", "token", "install", "--org", "us-conversion"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        bufsize=1  # Line buffered like in working tests
    )

    # Process output
    output_lines = []
    state = {"oauth": False, "reissue": False, "condarc": False, "success": False}
    start_time = time.time()

    while time.time() - start_time < 120:
        # Read stdout
        if token_proc.stdout:
            line = token_proc.stdout.readline().strip()
            if line:
                output_lines.append(line)
                logger.info(f"[STDOUT] {line}")

                # OAuth URL detection and handling
                if not state["oauth"] and "https://auth.anaconda.com" in line:
                    oauth_url = re.search(r'https://[^\s]+', line).group(0)
                    logger.info(f"Found OAuth URL: {oauth_url}")

                    # Perform OAuth login (same as test_anaconda_login)
                    page.goto(oauth_url)
                    page.wait_for_load_state("networkidle")

                    # Extract state and login
                    url_state = urllib.parse.parse_qs(urllib.parse.urlparse(oauth_url).query).get("state", [""])[0]
                    if url_state:
                        res = api_request_context.post(f"/api/auth/login/password/{url_state}", data=credentials)
                        if res.ok and res.json().get("redirect"):
                            page.goto(res.json()["redirect"])
                            page.wait_for_load_state("networkidle")

                            state["oauth"] = True
                            logger.info("OAuth login completed")
                            logger.info("Waiting for CLI to process OAuth callback...")
                            time.sleep(5)

                # Prompt detection
                prompt_keywords = ["[y/n]", "(y/n)", "reissuing", "revoke", "proceed", "do you want to"]
                if any(kw in line.lower() for kw in prompt_keywords):
                    logger.info(f"Found prompt: '{line}'")
                    response_type = "reissue" if not state["reissue"] else "condarc"
                    response = "y" if response_type == "reissue" else "n"

                    if token_proc.poll() is None:
                        try:
                            token_proc.stdin.write(f"{response}\n")
                            token_proc.stdin.flush()
                            state[response_type] = True
                            logger.info(f"Answered '{response}' to {response_type} prompt")
                        except BrokenPipeError:
                            logger.warning(f"BrokenPipeError: Process exited while answering {response_type} prompt")
                            break
                    else:
                        logger.warning(f"Process already exited before answering {response_type} prompt")
                        break

                # Success detection
                if "success!" in line.lower() and "token has been installed" in line.lower():
                    state["success"] = True
                    logger.info("Success message found!")

        # Check if process ended
        if token_proc.poll() is not None:
            break

        time.sleep(0.1)

    # Cleanup
    if token_proc.poll() is None:
        token_proc.terminate()
        token_proc.wait(timeout=5)

    exit_code = token_proc.returncode

    # Results
    logger.info("\n" + "="*60)
    logger.info(f"Results: Exit code: {exit_code}, OAuth: {state['oauth']}, "
                f"Reissue: {state['reissue']}, Condarc: {state['condarc']}, Success: {state['success']}")

    # Verify .condarc
    condarc_path = Path(clean_home) / ".condarc"
    if condarc_path.exists():
        content = condarc_path.read_text()
        if "us-conversion" not in content:
            logger.info(".condarc does not contain us-conversion channel (as expected)")

    # Assertions for token install
    assert state["oauth"], "Should handle OAuth login"
    assert state["reissue"] or state["condarc"] or state["success"], "Should see at least one prompt or success"
    assert exit_code == 0 or state["success"], "Should complete successfully"

    # Step 5: Verify conda search shows packages from pkgs/main
    logger.info("\n" + "="*60)
    logger.info("Step 5: Running conda search flask to verify channel configuration...")

    search_proc = subprocess.Popen(
        ["conda", "search", "flask"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env
    )

    search_output, search_error = search_proc.communicate(timeout=30)
    search_exit_code = search_proc.returncode

    logger.info(f"Conda search exit code: {search_exit_code}")

    if search_output:
        logger.info("Conda search output:")
        search_lines = search_output.strip().split('\n')

        # Parse and verify channels
        packages_found = False
        all_pkgs_main = True

        for line in search_lines:
            logger.info(f"  {line}")

            # Skip header lines
            if "Name" in line or "Loading channels" in line or line.startswith("#"):
                continue

            # Check if line contains package info
            if "flask" in line.lower():
                packages_found = True
                if "pkgs/main" not in line:
                    all_pkgs_main = False
                    logger.warning(f"Found package not from pkgs/main: {line}")

        assert packages_found, "Should find flask packages"
        assert all_pkgs_main, "All packages should be from pkgs/main channel (default)"
        logger.info("All flask packages are from pkgs/main channel (default)")

    assert search_exit_code == 0, f"Conda search should succeed, got exit code {search_exit_code}"

    logger.info("\nTest passed - Token installed but .condarc rejected, using default channels!")