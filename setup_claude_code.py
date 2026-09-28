"""Non-interactive setup helper for Kiro Gateway for Claude Code.

Copies ``.env.example`` to ``.env`` (if missing), generates a random
``PROXY_API_KEY``, auto-detects Kiro credentials, applies Claude Code
presets, and prints the exact exports needed to launch Claude Code.

Usage:
    python setup_claude_code.py            # full setup incl. pip install
    python setup_claude_code.py --no-install  # skip pip install

This script never overwrites existing values in ``.env`` — it only fills
in missing or placeholder entries.
"""

import json
import secrets
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
ENV_PATH = REPO_ROOT / ".env"
ENV_EXAMPLE_PATH = REPO_ROOT / ".env.example"
PLACEHOLDER_KEY = "my-super-secret-password-123"


def run_pip_install() -> None:
    """Install Python dependencies from requirements.txt.

    Raises:
        RuntimeError: If pip install exits with a non-zero status.
    """
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
        cwd=REPO_ROOT,
    )
    if result.returncode != 0:
        raise RuntimeError("pip install -r requirements.txt failed")


def read_env_lines(path: Path) -> list[str]:
    """Read a dotenv file preserving comments and formatting.

    Args:
        path: Path to the dotenv file.

    Returns:
        List of raw lines (without trailing newlines).
    """
    return path.read_text(encoding="utf-8").splitlines()


def get_env_value(lines: list[str], name: str) -> str | None:
    """Get the current value of a variable in dotenv lines.

    Args:
        lines: Raw dotenv lines.
        name: Variable name to look up.

    Returns:
        The unquoted value, or None if the variable is absent/commented.
    """
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        if key.strip() == name:
            return value.strip().strip("\"'")
    return None


def set_env_value(lines: list[str], name: str, value: str) -> list[str]:
    """Set a variable in dotenv lines, preserving everything else.

    Replaces the first active occurrence, uncomments nothing, and appends
    the variable at the end if it is absent.

    Args:
        lines: Raw dotenv lines.
        name: Variable name to set.
        value: New value (will be double-quoted).

    Returns:
        Updated list of dotenv lines.
    """
    updated = list(lines)
    for i, line in enumerate(updated):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, _ = stripped.partition("=")
        if key.strip() == name:
            updated[i] = f'{name}="{value}"'
            return updated
    updated.append(f'{name}="{value}"')
    return updated


def detect_kiro_credentials() -> tuple[str, str] | None:
    """Auto-detect Kiro credentials on this machine.

    Checks (in order): Kiro IDE token file, any SSO cache file containing
    a refreshToken, then the kiro-cli / amazon-q SQLite databases.

    Returns:
        Tuple of (env_var_name, path) for the first hit, or None.
    """
    home = Path.home()

    ide_token = home / ".aws" / "sso" / "cache" / "kiro-auth-token.json"
    if ide_token.is_file():
        return ("KIRO_CREDS_FILE", ide_token.as_posix())

    cache_dir = home / ".aws" / "sso" / "cache"
    if cache_dir.is_dir():
        candidates: list[Path] = []
        for child in cache_dir.glob("*.json"):
            try:
                data = json.loads(child.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(data, dict) and data.get("refreshToken"):
                candidates.append(child)
        if candidates:
            newest = max(candidates, key=lambda p: p.stat().st_mtime)
            return ("KIRO_CREDS_FILE", newest.as_posix())

    for db_name in ("kiro-cli", "amazon-q"):
        db_path = home / ".local" / "share" / db_name / "data.sqlite3"
        if db_path.is_file():
            try:
                with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
                    conn.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchone()
            except sqlite3.Error:
                continue
            return ("KIRO_CLI_DB_FILE", db_path.as_posix())

    return None


def ensure_env() -> dict[str, str]:
    """Create ``.env`` if needed and fill missing Claude Code values.

    Returns:
        Dict of the effective settings the script ensured.

    Raises:
        FileNotFoundError: If ``.env.example`` does not exist and no ``.env`` exists.
    """
    if not ENV_PATH.is_file():
        if not ENV_EXAMPLE_PATH.is_file():
            raise FileNotFoundError("Neither .env nor .env.example exists")
        ENV_PATH.write_text(
            ENV_EXAMPLE_PATH.read_text(encoding="utf-8"), encoding="utf-8"
        )
        print("Created .env from .env.example")

    lines = read_env_lines(ENV_PATH)
    ensured: dict[str, str] = {}

    api_key = get_env_value(lines, "PROXY_API_KEY")
    if not api_key or api_key == PLACEHOLDER_KEY:
        api_key = f"kiro-{secrets.token_urlsafe(32)}"
        lines = set_env_value(lines, "PROXY_API_KEY", api_key)
        print("Generated new PROXY_API_KEY")
    ensured["PROXY_API_KEY"] = api_key

    creds_file = get_env_value(lines, "KIRO_CREDS_FILE")
    cli_db = get_env_value(lines, "KIRO_CLI_DB_FILE")
    if not creds_file and not cli_db:
        found = detect_kiro_credentials()
        if found:
            var_name, path = found
            lines = set_env_value(lines, var_name, path)
            ensured[var_name] = path
            print(f"Detected Kiro credentials: {var_name}={path}")
        else:
            print(
                "WARNING: no Kiro credentials found. Log in to Kiro IDE "
                "or kiro-cli, then re-run this script."
            )

    if get_env_value(lines, "AUTO_TRIM_PAYLOAD") != "true":
        lines = set_env_value(lines, "AUTO_TRIM_PAYLOAD", "true")
    ensured["AUTO_TRIM_PAYLOAD"] = "true"

    if not get_env_value(lines, "LOG_LEVEL"):
        lines = set_env_value(lines, "LOG_LEVEL", "INFO")
    ensured["LOG_LEVEL"] = get_env_value(lines, "LOG_LEVEL") or "INFO"

    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return ensured


def print_next_steps(api_key: str) -> None:
    """Print the exact commands to verify the gateway and launch Claude Code.

    Args:
        api_key: Effective PROXY_API_KEY value.
    """
    print("\nNext steps:")
    print("  1. Start the gateway:  python main.py")
    print(
        "  2. Verify models:       "
        f'curl http://localhost:8000/v1/models -H "x-api-key: {api_key}"'
    )
    print("  3. Launch Claude Code (Linux/macOS):")
    print('     export ANTHROPIC_BASE_URL="http://localhost:8000"')
    print(f'     export ANTHROPIC_API_KEY="{api_key}"')
    print('     export ANTHROPIC_MODEL="claude-sonnet-4-5"   # pick from /v1/models')
    print("     claude")
    print("See README.md for Windows PowerShell and settings.json variants.")


def main() -> int:
    """Run the Claude Code setup flow.

    Returns:
        Process exit code (0 on success, 1 on failure).
    """
    if sys.version_info < (3, 10):
        print(f"ERROR: Python 3.10+ required, found {sys.version.split()[0]}")
        return 1

    if "--no-install" not in sys.argv:
        try:
            run_pip_install()
        except RuntimeError as exc:
            print(f"ERROR: {exc}")
            return 1

    try:
        ensured = ensure_env()
    except (FileNotFoundError, OSError) as exc:
        print(f"ERROR: {exc}")
        return 1

    print_next_steps(ensured["PROXY_API_KEY"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
