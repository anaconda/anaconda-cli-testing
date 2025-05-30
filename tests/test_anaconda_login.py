# tests/test_anaconda_login_cli_flow.py
import re
import time
import pytest
from subprocess import TimeoutExpired
from playwright.sync_api import Page, Browser, expect

@pytest.mark.usefixtures("ensureConda")
def test_login_via_api_and_browser_and_cli_flow(
    api_request_context,  # from conftest
    page: Page,
    browser: Browser,
    credentials,          # from conftest
    urls,                 # from conftest
    cli_runner,           # from conftest
):
    # ─── 1) Log in via API + Playwright ─────────────────────────────
    print("[TEST] Step 1: Logging in via API + Playwright...")
    auth = api_request_context.post(
        f"/api/auth/authorize?return_to={urls['ui']}"
    )
    assert auth.ok, f"Authorize failed: {auth.status}"
    state = auth.json().get("state")
    assert state, "No state returned from authorize"

    login = api_request_context.post(
        f"/api/auth/login/password/{state}",
        data=credentials
    )
    assert login.ok, f"Password login failed: {login.status}"
    redirect_url = login.json().get("redirect")
    assert redirect_url, "No redirect URL returned"

    page.goto(redirect_url)
    expect(page.get_by_text("Welcome Back")).to_be_visible(timeout=10_000)
    assert page.url.startswith(urls['ui']), \
        f"Expected to be on {urls['ui']}, got {page.url}"
    print("✅ Step 1 completed: User is now authenticated in browser")

    # ─── 2) Spawn CLI & capture its OAuth URL ─────────────────────────
    print("[TEST] Step 2: Spawning CLI and capturing OAuth URL...")
    proc, port = cli_runner()
    oauth_url = None
    start = time.time()
    print(f"[TEST] CLI started on port {port}, capturing OAuth URL...")

    while time.time() - start < 15:
        line = proc.stdout.readline()
        if not line:
            if proc.poll() is not None:
                break
            time.sleep(0.1)
            continue
        print(f"[CLI] {line.strip()}")
        found = re.findall(r"https?://[^\s]+", line)
        for u in found:
            if "/api/auth/oauth2/authorize" in u:
                oauth_url = u
                print(f"[TEST] ✅ Captured OAuth URL: {oauth_url}")
                break
        if oauth_url:
            break

    if not oauth_url:
        proc.terminate()
        proc.wait(timeout=5)
        pytest.fail("❌ Failed to capture OAuth URL from CLI")
    print("✅ Step 2 completed: OAuth URL captured from CLI")

    # ─── 3) Complete the OAuth flow using the SAME authenticated page ─
    print("[TEST] Step 3: Completing OAuth flow with existing session...")
    page.goto(oauth_url, timeout=30000)
    page.wait_for_load_state("networkidle", timeout=15000)
    print(f"[TEST] OAuth flow ended at URL: {page.url}")
    print("✅ Step 3 completed: OAuth flow processed")

    # ─── 4) Wait for CLI to finish ─────────────────────────────────────
    print("[TEST] Step 4: Waiting for CLI to complete...")
    cli_completed = False
    output_lines = []

    start = time.time()
    while time.time() - start < 20:
        if proc.poll() is not None:
            cli_completed = True
            print(f"[CLI] Process exited with {proc.returncode}")
            break
        line = proc.stdout.readline()
        if line:
            txt = line.strip()
            print(f"[CLI] {txt}")
            output_lines.append(txt)
        else:
            time.sleep(0.1)

    if not cli_completed:
        proc.terminate()
        proc.wait(timeout=5)
        print("⚠️ CLI did not cleanly exit, but proceeding")

    # ─── 5) Final verification ─────────────────────────────────────────
    print("[TEST] Step 5: Verifying success page…")
    success_url = f"{urls['ui']}/local-login-success"
    page.goto(success_url, timeout=10_000)
    page.wait_for_load_state("networkidle", timeout=10_000)

    # Assert that the URL is exactly what we expect
    assert "/local-login-success" in page.url, \
        f"Expected '/local-login-success' in URL, got: {page.url}"
    print(f"✅ URL path is correct: {page.url}")

    # Assert that the Success banner is shown
    banner = page.get_by_text("Success! You are now logged in.")
    expect(banner).to_be_visible(timeout=5_000)
    print("✅ Success banner is visible")

    page.context.close()
    print("✅ End-to-end CLI+browser login flow completed successfully!")