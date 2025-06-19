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
    pytest.exit(f"❌ Missing env vars: {', '.join(missing)}", 1)

# ─── 3) Ensure Conda installed and on PATH ─────────────────────
@pytest.fixture(scope="session")
def ensureConda():
    """
    Session-wide autouse: verify Conda is installed via conda_helper
    and prepend its bin to PATH.
    """
    info, code = ensure_conda_installed()
    assert code == 0, f"❌ Could not install conda: {info.decode()}"

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