"""
Files and folders used by the launcher, in its repo and in the user's home directory.
"""

from pathlib import Path

LAUNCHER_REPO = Path(__file__).resolve().parent.parent
# INFO: Written by install.ps1, not versioned since the skills repo path varies per machine
CONFIG_FILE = LAUNCHER_REPO / "config.json"

ACCOUNTS_DIR = Path.home() / ".claude-accounts"
STATE_FILE = ACCOUNTS_DIR / "launcher_state.json"

# INFO: Shared base of all accounts, which no account logs into
SHARED_CONFIG_DIR = Path.home() / ".claude"
SHARED_SETTINGS_FILE = SHARED_CONFIG_DIR / "settings.json"
