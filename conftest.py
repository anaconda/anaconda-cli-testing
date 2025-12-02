# Central test configuration and fixtures for Anaconda Hub CLI + Playwright

import os
import socket
import subprocess
import time
from pathlib import Path
import pytest
from dotenv import load_dotenv
from playwright.sync_api import APIRequestContext
from src.common.conda_helper import ensure_conda_installed
from src.common.cli_utils import capture  # you can still use this in other tests
import urllib.parse
import re
import logging

logger = logging.getLogger(__name__)

# ─── 1) Load environment variables ──────────────────────────────
load_dotenv(dotenv_path=Path(__file__).parent / ".env")

# ─── 2) Read and validate required settings ─────────────────────
apiBase     = os.getenv("ANACONDA_API_BASE")   # API host
uiBase      = os.getenv("ANACONDA_UI_BASE")    # UI host
hubEmail    = os.getenv("HUB_EMAIL")           # login email
hubPassword = os.getenv("HUB_PASSWORD")        # login password

requiredKeys = ["ANACONDA_API_BASE", "ANACONDA_UI_BASE", "HUB_EMAIL", "HUB_PASSWORD"]
missing      = [k for k in requiredKeys if not os.getenv(k)]
if missing:
    pytest.exit(f"Missing env vars: {', '.join(missing)}", 1)

# ─── 3) Ensure Conda installed and on PATH ─────────────────────
@pytest.fixture(scope="session")
def ensureConda():
    """
    Session-wide autouse: verify Conda is installed via conda_helper
    and prepend its bin to PATH.
    """
    info, code = ensure_conda_installed()
    assert code == 0, f"Could not install conda: {info.decode()}"

    import platform
    if platform.system() == "Windows":
        condaBin = Path.home() / "miniconda3" / "Scripts"
    else:
        condaBin = Path.home() / "miniconda3" / "bin"
    os.environ["PATH"] = str(condaBin) + os.pathsep + os.environ.get("PATH", "")

# ─── 4) Playwright API context fixture ─────────────────────────
@pytest.fixture(scope="session")
def api_request_context(playwright) -> APIRequestContext:
    """Provide a Playwright API context pointed at ANACONDA_API_BASE."""
    return playwright.request.new_context(
        base_url=apiBase,
        extra_http_headers={"Content-Type": "application/json"},
    )

# ─── 5) URLs fixture ─────────────────────────────────────────────
@pytest.fixture(scope="session")
def urls():
    """Return API and UI base URLs from environment."""
    return {"api": apiBase, "ui": uiBase}

# ─── 6) Credentials fixture ─────────────────────────────────────
@pytest.fixture(scope="session")
def credentials():
    """Return login credentials from environment."""
    return {"email": hubEmail, "password": hubPassword}


# ─── 7) free_port fixture with retry logic ─────────────────────
@pytest.fixture
def free_port():
    """
    Grab an ephemeral port for the CLI OAuth callback with retry logic.
    """
    max_attempts = 10
    for attempt in range(max_attempts):
        try:
            sock = socket.socket()
            sock.bind(("", 0))
            port = sock.getsockname()[1]
            sock.close()
            
            test_sock = socket.socket()
            try:
                test_sock.bind(("", port))
                test_sock.close()
                return port
            except OSError:
                continue
        except OSError:
            if attempt == max_attempts - 1:
                raise
            time.sleep(0.1)
    
    raise RuntimeError("Could not find a free port after multiple attempts")


# ─── 8) pw_open_script fixture with simple approach ───────────
@pytest.fixture
def pw_open_script(tmp_path):
    """
    Create a simple wrapper that the CLI will call instead of a real browser.
    Just echoes the URL so we can capture it in the test.
    """
    import platform
    is_windows = platform.system() == "Windows"
    
    if is_windows:
        # Windows: create a batch file
        script = tmp_path / "pw-open.bat"
        oauth_url_file = tmp_path / "oauth_url_output.txt"
        # Write URL to file to avoid command line truncation, also echo for compatibility
        # Convert path to Windows format for batch file
        oauth_file_path = str(oauth_url_file).replace('/', '\\')
        script.write_text(
            "@echo off\n"
            "REM Called by `anaconda auth login` with the OAuth URL\n"
            "REM Capture all arguments using %* to handle long URLs\n"
            "setlocal enabledelayedexpansion\n"
            "set URL=%*\n"
            f"REM Write full URL to file: {oauth_file_path}\n"
            f"echo !URL! > \"{oauth_file_path}\"\n"
            "echo [BROWSER-STUB-URL]!URL!\n"
            "timeout /t 1 /nobreak >nul\n"
        )
        # Store file path in environment variable for tests to find
        import os
        os.environ['OAUTH_URL_FILE'] = str(oauth_url_file)
    else:
        # Linux/Mac: create a bash script
        script = tmp_path / "pw-open.sh"
        script.write_text(
            "#!/usr/bin/env bash\n"
            "# Called by `anaconda auth login` with the OAuth URL as $1\n"
            "echo \"[BROWSER-STUB] Would open: $1\"\n"
            "sleep 0.5\n"
        )
        script.chmod(0o755)
    
    return script


# ─── 9) cli_runner fixture with clean HOME ─────────────────────
@pytest.fixture
def cli_runner(free_port, pw_open_script, tmp_path):
    """
    Launch `anaconda auth login` with:
     • BROWSER set to our pw-open.sh wrapper
     • ANACONDA_OAUTH_CALLBACK_PORT set to free_port
     • ANACONDA_AUTH_API_KEY blanked to force a fresh OAuth flow
     • HOME pointed at an empty tmp dir so there's no cached token
    Returns (process, port, clean_home).
    """
    def _run():
        clean_home = tmp_path / "clean_home"
        clean_home.mkdir()

        env = os.environ.copy()
        env["HOME"] = str(clean_home)
        env["BROWSER"] = str(pw_open_script)
        env["ANACONDA_OAUTH_CALLBACK_PORT"] = str(free_port)
        env["ANACONDA_AUTH_API_KEY"] = ""

        # kill any stray `anaconda auth login` using this port
        try:
            subprocess.run(
                ["pkill", "-f", f"anaconda.*auth.*login"],
                capture_output=True,
                timeout=5
            )
            time.sleep(1)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        proc = subprocess.Popen(
            ["anaconda", "auth", "login"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        return proc, free_port, str(clean_home)

    return _run


# ─── 10) run_cli_command fixture (supports extra_env) ──────────
@pytest.fixture
def run_cli_command():
    """
    Execute CLI commands with optional environment variable overrides.
    """
    def _run(command: str, timeout: int = 30, extra_env: dict = None):
        env = os.environ.copy()
        if extra_env:
            env.update(extra_env)
        
        return subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env
        )
    
    return _run


# ─── 11) token_install_env fixture for token install tests ─────
@pytest.fixture
def token_install_env(cli_runner, pw_open_script, free_port):
    """
    Setup environment for token install tests.
    Returns (env, clean_home) tuple.
    """
    _, _, clean_home = cli_runner()
    import platform
    is_windows = platform.system() == "Windows"
    if is_windows:
        conda_path = f"{Path.home()}/miniconda3/Scripts"
        path_sep = os.pathsep
    else:
        conda_path = f"{Path.home()}/miniconda3/bin"
        path_sep = ":"
    
    env = {
        **os.environ,
        "HOME": str(clean_home),
        "PATH": f"{conda_path}{path_sep}{os.environ.get('PATH', '')}",
        "BROWSER": str(pw_open_script),
        "ANACONDA_OAUTH_CALLBACK_PORT": str(free_port)
    }
    return env, clean_home


# ─── 12) isolated_conda_env fixture for isolated conda tests ───
@pytest.fixture
def isolated_conda_env(tmp_path, monkeypatch):
    """
    Provide an isolated conda environment with clean HOME.
    Useful for tests that need to run without interference from other conda configurations.
    """
    clean_home = tmp_path / "clean_home"
    clean_home.mkdir()
    monkeypatch.setenv("HOME", str(clean_home))
    
    # Accept ToS for default channels to avoid authentication issues
    for channel in ["https://repo.anaconda.com/pkgs/main", "https://repo.anaconda.com/pkgs/r"]:
        capture(f"conda tos accept --override-channels --channel {channel}")
    
    return clean_home


# ─── 13) Common OAuth helper functions ─────────────────────────
# These are helper functions (not fixtures) used across multiple tests

def extract_oauth_url_from_line(line: str) -> str | None:
    """
    Extract OAuth URL from a line of CLI output.
    Tries multiple patterns to handle different output formats.
    
    Args:
        line: Line of text that may contain an OAuth URL
        
    Returns:
        Extracted OAuth URL or None if not found
    """
    # Try new format first: [BROWSER-STUB-URL] followed by URL
    url_match = re.search(r'\[BROWSER-STUB-URL\](https://[^\s]+)', line)
    if not url_match:
        # Fallback: try old format "Would open: "
        url_match = re.search(r'Would open:\s*(https://[^\s\)\"]+)', line)
    if not url_match:
        # Fallback: look for URL starting with https://auth.anaconda.com
        url_match = re.search(r'https://auth\.anaconda\.com[^\s\)\"]+', line)
    if url_match:
        return url_match.group(1) if url_match.lastindex and url_match.lastindex >= 1 else url_match.group(0)
    else:
        # Last resort: extract from the line directly
        url_match = re.search(r'https://[^\s\)\"]+', line)
        return url_match.group(0) if url_match else None


def try_read_oauth_url_from_file(clean_home: str, env: dict) -> str | None:
    """
    Try to read the complete OAuth URL from a file written by the batch script.
    
    Args:
        clean_home: Path to clean home directory
        env: Environment dictionary
        
    Returns:
        Complete OAuth URL from file or None if not found
    """
    from src.common.defaults import (
        OAUTH_URL_FILE_ENV_VAR,
        OAUTH_URL_OUTPUT_FILENAME,
    )
    try:
        possible_files = []
        if os.environ.get(OAUTH_URL_FILE_ENV_VAR):
            possible_files.append(Path(os.environ[OAUTH_URL_FILE_ENV_VAR]))
        possible_files.extend([
            Path(clean_home).parent / OAUTH_URL_OUTPUT_FILENAME,
            Path(env.get("TMP", env.get("TEMP", ""))) / OAUTH_URL_OUTPUT_FILENAME 
            if env.get("TMP") or env.get("TEMP") else None,
        ])
        
        for file_path in possible_files:
            if file_path and file_path.exists():
                file_url = file_path.read_text().strip()
                if file_url and "state=" in file_url:
                    logger.info(f"Found complete URL in file: {file_url[:100]}...")
                    return file_url
    except Exception as e:
        logger.debug(f"Could not read URL from file: {e}")
    
    return None


def try_read_oauth_url_continuation(token_proc, current_url: str) -> str:
    """
    Try to read continuation lines to complete an incomplete OAuth URL.
    
    Args:
        token_proc: The subprocess object reading CLI output
        current_url: The incomplete URL that needs continuation
        
    Returns:
        Complete URL if continuation found, otherwise original URL
    """
    from src.common.defaults import (
        OAUTH_URL_CONTINUATION_TIMEOUT,
        OAUTH_URL_CONTINUATION_MAX_LINES,
    )
    if "state=" in current_url:
        return current_url
    
    logger.warning("URL appears incomplete, trying to read continuation lines...")
    start_time = time.time()
    
    for _ in range(OAUTH_URL_CONTINUATION_MAX_LINES):
        if time.time() - start_time > OAUTH_URL_CONTINUATION_TIMEOUT:
            break
        try:
            next_line = token_proc.stdout.readline().strip()
            if next_line:
                logger.info(f"[STDOUT continuation] {next_line}")
                if next_line.startswith("&") or "state=" in next_line:
                    return current_url + next_line
                url_cont_match = re.search(r'https://auth\.anaconda\.com[^\s]+', next_line)
                if url_cont_match:
                    return url_cont_match.group(0)
        except Exception as e:
            logger.debug(f"Error reading continuation: {e}")
            break
    
    return current_url


def extract_and_complete_oauth_url(line: str, token_proc, clean_home: str, env: dict) -> str | None:
    """
    Extract OAuth URL from line and try to complete it if incomplete.
    This function combines all the URL extraction and completion logic.
    
    Args:
        line: Line of CLI output that may contain OAuth URL
        token_proc: Subprocess object for reading continuation lines
        clean_home: Path to clean home directory
        env: Environment dictionary
        
    Returns:
        Complete OAuth URL or None if extraction failed
    """
    oauth_url = extract_oauth_url_from_line(line)
    if not oauth_url:
        return None
    
    # If URL seems incomplete, try reading from file first
    if "state=" not in oauth_url:
        file_url = try_read_oauth_url_from_file(clean_home, env)
        if file_url and len(file_url) > len(oauth_url):
            oauth_url = file_url
        else:
            # If still incomplete, try reading more lines
            oauth_url = try_read_oauth_url_continuation(token_proc, oauth_url)
    
    return oauth_url


def perform_oauth_login(page, api_request_context, oauth_url, credentials):
    """
    Handle OAuth authentication flow through browser and API.
    This common function is used by multiple tests to avoid code duplication.
    
    Args:
        page: Playwright page object
        api_request_context: Playwright API context
        oauth_url: The OAuth URL containing state parameter
        credentials: Dict with 'email' and 'password'
        
    Returns:
        bool: True if OAuth login completed successfully
    """
    from src.common.defaults import PAGE_LOAD_TIMEOUT, NETWORK_IDLE_TIMEOUT
    
    try:
        # Navigate to OAuth URL with timeout
        logger.info(f"Navigating to OAuth URL: {oauth_url[:100]}...")
        try:
            page.goto(oauth_url, timeout=PAGE_LOAD_TIMEOUT, wait_until="domcontentloaded")
        except Exception as e:
            logger.warning(f"Page goto failed or timed out: {e}, trying with load state...")
            page.goto(oauth_url, timeout=PAGE_LOAD_TIMEOUT)
        
        # Wait for network idle with a shorter timeout to avoid hanging
        try:
            page.wait_for_load_state("networkidle", timeout=min(NETWORK_IDLE_TIMEOUT, 10000))
        except Exception as e:
            logger.warning(f"Network idle wait timed out: {e}, continuing anyway...")
            # Continue even if networkidle times out - the page might still be usable
        
        # Get the actual URL after navigation (might have been redirected or completed)
        actual_url = page.url
        logger.info(f"Actual page URL after navigation: {actual_url[:100]}...")
        
        # Extract state from the actual URL (after redirects)
        url_state = urllib.parse.parse_qs(
            urllib.parse.urlparse(actual_url).query
        ).get("state", [""])[0]
        
        # If still no state, try the original URL
        if not url_state:
            url_state = urllib.parse.parse_qs(
                urllib.parse.urlparse(oauth_url).query
            ).get("state", [""])[0]
        
        # If still no state, try to extract from page content or URL path
        if not url_state:
            # Sometimes state is in the URL path (e.g., /authorize/{state}/...)
            path_parts = urllib.parse.urlparse(actual_url).path.split('/')
            for part in path_parts:
                if part and len(part) > 20:  # State is usually a UUID or long string
                    # Check if it looks like a state parameter (UUID format or similar)
                    if '-' in part or len(part) > 30:
                        url_state = part
                        logger.info(f"Extracted state from URL path: {url_state[:50]}...")
                        break
        
        # If still no state, try to extract from page content (might be in a form or link)
        if not url_state:
            try:
                # Look for state in page content - check for common patterns
                page_content = page.content()
                # Look for state in hidden inputs, links, or JavaScript
                state_match = re.search(r'state[=:]\s*["\']?([a-zA-Z0-9\-_]+)["\']?', page_content, re.IGNORECASE)
                if state_match:
                    url_state = state_match.group(1)
                    logger.info(f"Extracted state from page content: {url_state[:50]}...")
            except Exception as e:
                logger.debug(f"Could not extract state from page content: {e}")
        
        # If still no state, try to get it from the authorize endpoint directly
        if not url_state:
            # The URL might be an authorize endpoint - try to call it via API to get state
            try:
                # Parse the authorize URL to get client_id and other params
                parsed = urllib.parse.urlparse(oauth_url)
                query_params = urllib.parse.parse_qs(parsed.query)
                client_id = query_params.get('client_id', [None])[0]
                redirect_uri = query_params.get('redirect_uri', [None])[0]
                
                if client_id:
                    # Try to get authorize endpoint which should return state
                    # Use the UI base URL as return_to
                    from src.common.defaults import URL_PATTERNS
                    return_to = f"{parsed.scheme}://{parsed.netloc}"
                    if redirect_uri:
                        return_to = redirect_uri
                    
                    logger.info(f"Calling authorize API with client_id: {client_id[:50]}...")
                    auth_resp = api_request_context.get(f"/api/auth/authorize?return_to={return_to}")
                    if auth_resp.ok:
                        auth_data = auth_resp.json()
                        url_state = auth_data.get('state')
                        if url_state:
                            logger.info(f"Got state from authorize API: {url_state[:50]}...")
                        else:
                            logger.warning(f"Authorize API response: {auth_data}")
            except Exception as e:
                logger.debug(f"Could not get state from authorize API: {e}")
        
        if not url_state:
            logger.error(f"No state parameter found in OAuth URL. Original: {oauth_url[:100]}..., Actual: {actual_url[:100]}...")
            # Last resort: if the URL has client_id, try to get state from authorize endpoint
            parsed = urllib.parse.urlparse(oauth_url if oauth_url else actual_url)
            query_params = urllib.parse.parse_qs(parsed.query)
            client_id = query_params.get('client_id', [None])[0]
            
            if client_id:
                logger.warning("URL has client_id but no state - trying to get state from authorize API...")
                try:
                    # Get the UI base from environment or use the parsed URL
                    ui_base = os.getenv("ANACONDA_UI_BASE", f"{parsed.scheme}://{parsed.netloc}")
                    auth_resp = api_request_context.get(f"/api/auth/authorize?return_to={ui_base}")
                    if auth_resp.ok:
                        auth_data = auth_resp.json()
                        url_state = auth_data.get('state')
                        if url_state:
                            logger.info(f"Successfully got state from authorize API: {url_state[:50]}...")
                        else:
                            logger.error(f"Authorize API did not return state. Response: {auth_data}")
                            return False
                    else:
                        logger.error(f"Authorize API call failed: {auth_resp.status}")
                        return False
                except Exception as e:
                    logger.error(f"Failed to get state from authorize API: {e}")
                    return False
            else:
                logger.error("No client_id found in URL either")
                return False
        
        logger.info(f"Performing API login with state: {url_state}")
        # Perform API login
        res = api_request_context.post(
            f"/api/auth/login/password/{url_state}",
            data=credentials
        )
        
        if res.ok and res.json().get("redirect"):
            redirect_url = res.json()["redirect"]
            logger.info(f"Following redirect to: {redirect_url}")
            # Follow redirect to complete OAuth flow
            page.goto(redirect_url, timeout=PAGE_LOAD_TIMEOUT)
            page.wait_for_load_state("networkidle", timeout=NETWORK_IDLE_TIMEOUT)
            logger.info("OAuth login completed successfully")
            return True
        else:
            logger.error(f"OAuth API login failed with status: {res.status}, response: {res.text if hasattr(res, 'text') else 'N/A'}")
            return False
            
    except Exception as e:
        logger.error(f"OAuth login error: {e}", exc_info=True)
        return False


def retry_oauth_login_with_direct_navigation(page, api_request_context, oauth_url, credentials):
    """
    Retry OAuth login using direct navigation approach when initial login fails.
    This is a fallback mechanism that navigates directly to the OAuth URL,
    waits for redirects, and retries login with the actual URL.
    
    This common function is used by multiple tests to avoid code duplication.
    
    Args:
        page: Playwright page object
        api_request_context: Playwright API context
        oauth_url: The OAuth URL to navigate to
        credentials: Dict with 'email' and 'password'
        
    Returns:
        bool: True if OAuth login completed successfully after retry, False otherwise
    """
    logger.warning("OAuth login failed, trying direct navigation approach...")
    try:
        page.goto(oauth_url, timeout=30000, wait_until="domcontentloaded")
        time.sleep(2)
        actual_url = page.url
        logger.info(f"Page redirected to: {actual_url[:150]}...")
        # Try login with actual_url if it looks valid, otherwise try with original oauth_url
        if "state=" in actual_url or any(len(part) > 30 for part in actual_url.split('/') if part):
            login_result = perform_oauth_login(page, api_request_context, actual_url, credentials)
            if login_result:
                return True
        # If actual_url didn't work or wasn't valid, try with original oauth_url one more time
        logger.info("Retrying with original OAuth URL...")
        return perform_oauth_login(page, api_request_context, oauth_url, credentials)
    except Exception as e:
        logger.error(f"Direct navigation also failed: {e}")
    
    return False