# src/common/defaults.py
# ─── Constants for anaconda‐auth testing ───────────────────────────────
PACKAGE_NAME              = "anaconda-auth"     # the conda package name
CLI_SUBCOMMAND            = "anaconda auth"     # what you actually run on the CLI
ANACONDA_AUTH_VERSION     = "0.11.0"             # what we expect for --version/-V
CONDA_VERSION             = "25.5.1"            # conda version to test against

# ─── Conda Installation ──────────────────────────────────────────────
LINUX_INSTALLER_URL       = "https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh"
WINDOWS_INSTALLER_URL     = "https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe"

# ─── Version flags to verify ──────────────────────────────────────────
VERSION_FLAGS        = ["--version", "-V"]

# ─── Timeouts (in milliseconds for playwright, seconds for subprocess) ─
PAGE_LOAD_TIMEOUT    = 30_000   # timeout for page.goto / expect (increased for Windows)
NETWORK_IDLE_TIMEOUT = 30_000   # timeout for networkidle waits (increased for Windows)
OAUTH_CAPTURE_TIMEOUT= 15       # seconds to capture the CLI's oauth URL
CLI_COMPLETION_TIME  = 20       # seconds to wait for CLI to exit

# ─── Expected UI text ─────────────────────────────────────────────────
EXPECTED_TEXT = {
    "welcome": "Welcome Back",
    "success": "Success! You are now logged in."
}

# ─── URL‐fragments to look for ────────────────────────────────────────
URL_PATTERNS = {
    "oauth":   "/api/auth/oauth2/authorize",
    "success": "/local-login-success",
}

# ─── Timeouts for conda commands (in seconds) ────────────────────────
INSTALL_TIMEOUT      = 300
LIST_TIMEOUT         = 30

# ─── Retry policy ────────────────────────────────────────────────────
MAX_RETRIES          = 3

# ─── Conda configuration constants ───────────────────────────────────
DEFAULT_CHANNEL      = "defaults"
EXPECTED_CHANNEL     = "pkgs/main"
SEARCH_PACKAGE       = "flask"
SEARCH_HEADER_PREFIX = "# name"

# ─── Token install test constants ────────────────────────────────────
TOKEN_INSTALL_ORG           = "us-conversion"
TOKEN_INSTALL_TIMEOUT       = 120  # seconds
OAUTH_URL_CONTINUATION_TIMEOUT = 5  # seconds to wait for URL continuation
OAUTH_URL_CONTINUATION_MAX_LINES = 3  # max lines to read for URL continuation
PROMPT_KEYWORDS             = ["[y/n]", "(y/n)", "reissuing", "revoke", "proceed", "do you want to", "prepared to set"]
REISSUE_KEYWORDS            = ["reissuing", "revoke", "existing token"]
CONDARC_KEYWORDS            = ["condarc", "channel", "prepared to set"]
SUCCESS_MESSAGE_KEYWORDS    = ["success!", "token has been installed"]
TOKEN_INSTALLED_KEYWORD     = "token has been installed"
OAUTH_URL_FILE_ENV_VAR      = "OAUTH_URL_FILE"
OAUTH_URL_OUTPUT_FILENAME   = "oauth_url_output.txt"