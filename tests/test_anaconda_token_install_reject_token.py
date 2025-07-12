# This test verifies that cancelling token reissue aborts the installation process.

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
    free_port
):
    """
    This test verifies that answering 'n' to token reissue prompt aborts installation:
    1. Run anaconda token install --org us-conversion
    2. Handle OAuth login when prompted
    3. Respond 'n' to reissue token prompt
    4. Verify process aborts and token is NOT installed
    """
    logger.info("Starting anaconda token install cancel test...")

    _, _, clean_home = cli_runner()
    env = os.environ.copy()
    env["HOME"] = str(clean_home)
    env["PATH"] = f"{Path.home()}/miniconda3/bin:{env.get('PATH', '')}"
    env["BROWSER"] = str(pw_open_script)
    env["ANACONDA_OAUTH_CALLBACK_PORT"] = str(free_port)

    token_proc = subprocess.Popen(
        ["anaconda", "token", "install", "--org", "us-conversion"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        bufsize=0
    )

    state = {"oauth": False, "reissue": False, "success": False}
    start_time = time.time()

    while time.time() - start_time < 120:
        if token_proc.stdout:
            line = token_proc.stdout.readline().strip()
            if line:
                logger.info(f"[STDOUT] {line}")

                if not state["oauth"] and "https://auth.anaconda.com" in line:
                    oauth_url = re.search(r'https://[^\s]+', line).group(0)
                    logger.info(f"Found OAuth URL: {oauth_url}")
                    page.goto(oauth_url)
                    page.wait_for_load_state("networkidle")
                    url_state = urllib.parse.parse_qs(
                        urllib.parse.urlparse(oauth_url).query
                    ).get("state", [""])[0]

                    if url_state:
                        res = api_request_context.post(f"/api/auth/login/password/{url_state}", data=credentials)
                        if res.ok and res.json().get("redirect"):
                            page.goto(res.json()["redirect"])
                            page.wait_for_load_state("networkidle")
                            state["oauth"] = True
                            logger.info("OAuth login completed")
                            time.sleep(5)

                prompt_keywords = ["[y/n]", "(y/n)", "reissuing", "revoke", "proceed", "do you want to"]
                if any(kw in line.lower() for kw in prompt_keywords):
                    logger.info(f"Found prompt: {line}")
                    if not state["reissue"]:
                        if token_proc.poll() is None:
                            try:
                                token_proc.stdin.write("n\n")
                                token_proc.stdin.flush()
                                state["reissue"] = True
                                logger.info("Answered 'n' to cancel token reissue")
                            except BrokenPipeError:
                                logger.warning("❗ BrokenPipeError while writing 'n'")
                                break
                        else:
                            logger.warning("❗ CLI process exited before answering 'n'")
                            break

                if "success!" in line.lower() and "token has been installed" in line.lower():
                    state["success"] = True
                    logger.warning("Token was installed despite cancellation!")

        if token_proc.poll() is not None:
            break

        time.sleep(0.1)

    if token_proc.poll() is None:
        token_proc.terminate()
        token_proc.wait(timeout=5)

    logger.info("\n" + "="*60)
    logger.info(f"Results: Exit code: {token_proc.returncode}, OAuth: {state['oauth']}, Reissue: {state['reissue']}, Success: {state['success']}")

    assert state["oauth"], "Should handle OAuth login"
    assert state["reissue"], "Should have answered the reissue prompt"
    assert not state["success"], "❌ Token should NOT be installed after cancellation"
    assert token_proc.returncode != 0, "❌ Should exit with non-zero code when cancelled"

    logger.info("\n✅ Test passed - Token installation was properly cancelled!")