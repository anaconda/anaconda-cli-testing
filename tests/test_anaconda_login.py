# This test verifies the anaconda auth login flow using API, browser, and CLI.

import re
import time
import pytest
from subprocess import TimeoutExpired
from playwright.sync_api import Page, Browser, expect

from src.common.defaults import (
    URL_PATTERNS,
    EXPECTED_TEXT,
    PAGE_LOAD_TIMEOUT,
    NETWORK_IDLE_TIMEOUT,
    OAUTH_CAPTURE_TIMEOUT,
    CLI_COMPLETION_TIME,
)

@pytest.mark.usefixtures("ensureConda")
def test_complete_anaconda_login_flow(
    api_request_context, page: Page, browser: Browser, 
    credentials, urls, cli_runner
):
    """End-to-end test for Anaconda login: API → Browser → CLI → Success verification."""
    
    # Step 1: API Authentication
    state = _perform_api_authentication(api_request_context, urls, credentials)
    
    # Step 2: Browser Login  
    _perform_browser_login(page, api_request_context, state, urls, credentials)
    
    # Step 3: CLI OAuth Flow
    oauth_url = _perform_cli_oauth_flow(cli_runner, page)
    
    # Step 4: Success Verification
    _verify_login_success(page, urls)
    
    print("✅ Complete end‐to‐end CLI+browser login flow completed successfully!")


def _perform_api_authentication(api_request_context, urls, credentials):
    """Step 1: Perform API authentication and return state."""
    print("▶ Step 1: Performing API authentication...")
    
    auth = api_request_context.post(f"/api/auth/authorize?return_to={urls['ui']}")
    assert auth.ok, f"Authorize failed: {auth.status}"
    
    state = auth.json().get("state")
    assert state, "No state returned from authorize"
    
    login = api_request_context.post(f"/api/auth/login/password/{state}", data=credentials)
    assert login.ok, f"Password login failed: {login.status}"
    
    print("✅ Step 1: API authentication completed.")
    return state


def _perform_browser_login(page, api_request_context, state, urls, credentials):
    """Step 2: Complete browser login using API state."""
    print("▶ Step 2: Performing browser login...")
    
    login = api_request_context.post(f"/api/auth/login/password/{state}", data=credentials)
    redirect_url = login.json().get("redirect")
    assert redirect_url, "No redirect URL returned"
    
    page.goto(redirect_url, timeout=PAGE_LOAD_TIMEOUT)
    expect(page.get_by_text(EXPECTED_TEXT["welcome"])).to_be_visible(timeout=PAGE_LOAD_TIMEOUT)
    
    assert page.url.startswith(urls['ui']), f"Expected to be on {urls['ui']}, got {page.url}"
    print("✅ Step 2: Browser login completed (Welcome Back shown).")


def _perform_cli_oauth_flow(cli_runner, page):
    """Step 3: Start CLI process and complete OAuth flow."""
    print("▶ Step 3: Starting CLI OAuth flow...")
    
    proc, port = cli_runner()
    print(f"    → CLI process PID: {proc.pid}, listening on port {port}")
    
    oauth_url = _capture_oauth_url_from_cli(proc)
    if not oauth_url:
        proc.terminate()
        proc.wait(timeout=5)
        pytest.fail("❌ Failed to capture OAuth URL from CLI")
    
    print("    → Navigating to OAuth URL in browser...")
    page.goto(oauth_url, timeout=PAGE_LOAD_TIMEOUT)
    page.wait_for_load_state("networkidle", timeout=NETWORK_IDLE_TIMEOUT)
    
    _wait_for_cli_completion(proc)
    print("✅ Step 3: CLI OAuth flow completed.")
    return oauth_url


def _capture_oauth_url_from_cli(proc):
    """Capture OAuth URL from CLI stdout."""
    oauth_url, start_time = None, time.time()
    
    while time.time() - start_time < OAUTH_CAPTURE_TIMEOUT:
        line = proc.stdout.readline()
        if not line:
            if proc.poll() is not None:
                break
            time.sleep(0.05)
            continue
        
        line = line.strip()
        print(f"[CLI stdout] {line}")
        
        matches = re.findall(r"https?://[^\s]+", line)
        for u in matches:
            if URL_PATTERNS["oauth"] in u:
                oauth_url = u
                print(f"🎯 Captured OAuth URL: {oauth_url}")
                break
        if oauth_url:
            break
    return oauth_url


def _wait_for_cli_completion(proc):
    """Wait for CLI process to exit gracefully."""
    print("    → Waiting for CLI to exit...")
    start_time, cli_exited = time.time(), False
    
    while time.time() - start_time < CLI_COMPLETION_TIME:
        if proc.poll() is not None:
            cli_exited = True
            print(f"    → CLI exited with code {proc.returncode}")
            break
        time.sleep(0.05)
    
    if not cli_exited:
        proc.terminate()
        proc.wait(timeout=5)
        print("   ⚠️ CLI never cleanly exited; killed it anyway.")


def _verify_login_success(page, urls):
    """Step 4: Verify successful login on success page."""
    print("▶ Step 4: Verifying login success...")
    
    success_url = f"{urls['ui']}{URL_PATTERNS['success']}"
    page.goto(success_url, timeout=PAGE_LOAD_TIMEOUT)
    page.wait_for_load_state("networkidle", timeout=NETWORK_IDLE_TIMEOUT)
    
    assert URL_PATTERNS["success"] in page.url, f"Expected '{URL_PATTERNS['success']}' in URL, got {page.url}"
    expect(page.get_by_text(EXPECTED_TEXT["success"])).to_be_visible(timeout=PAGE_LOAD_TIMEOUT)
    
    page.context.close()
    print("✅ Step 4: Success verification completed.")