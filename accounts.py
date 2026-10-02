"""
Claude accounts, each isolated in its own Claude Code config directory.

Every account lives in ~/.claude-accounts/<id>/ and Claude Code is pointed at it
through the CLAUDE_CONFIG_DIR environment variable. Credentials are only ever
handled by Claude Code itself (`claude auth login/status/logout`): this module
never reads them and stores no email address. Labels come from the profile
Claude Code keeps in each account directory (.claude.json), which is read
instantly, unlike `claude auth status` which is only used to confirm a login.

~/.claude stays the shared base maintained by the claude-skills repo: each
account directory links its skills and plugins through junctions, imports its
CLAUDE.md, and receives its settings.json through `claude --settings`.
"""

import json
import os
import secrets
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ACCOUNTS_DIR = Path.home() / ".claude-accounts"
SHARED_CONFIG_DIR = Path.home() / ".claude"
STATE_FILE = ACCOUNTS_DIR / "launcher_state.json"
SHARED_DIRECTORIES = ("skills", "plugins")
SHARED_SETTINGS_FILE = SHARED_CONFIG_DIR / "settings.json"
CLAUDE_MD_IMPORT = "@~/.claude/CLAUDE.md\n"
STATUS_TIMEOUT_SECONDS = 15
LOGOUT_TIMEOUT_SECONDS = 30


@dataclass
class Account:
    account_id: str
    config_dir: Path
    logged_in: bool = False
    email: str | None = None

    @property
    def label(self):
        name = self.email or f"Unknown account {self.account_id}"

        return name if self.logged_in else f"{name} (logged out)"


def find_claude_executable():
    return shutil.which("claude")


def build_environment(account):
    return {**os.environ, "CLAUDE_CONFIG_DIR": str(account.config_dir)}


def fetch_status(account):
    try:
        result = subprocess.run(
            [find_claude_executable(), "auth", "status", "--json"],
            env=build_environment(account),
            capture_output=True,
            text=True,
            errors="replace",
            timeout=STATUS_TIMEOUT_SECONDS,
        )
        status = json.loads(result.stdout)
    except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError):
        # INFO: A failed status check says nothing about the login, so the account directory is read instead
        return read_account(account.config_dir)

    return Account(account.account_id, account.config_dir, bool(status.get("loggedIn")), status.get("email"))


def read_account(config_dir):
    try:
        profile = json.loads((config_dir / ".claude.json").read_text(encoding="utf-8"))
        email = profile.get("oauthAccount", {}).get("emailAddress")
    except (OSError, json.JSONDecodeError, AttributeError):
        email = None

    # INFO: Only the presence of the credentials file is checked, its content is never read
    logged_in = email is not None and (config_dir / ".credentials.json").is_file()

    return Account(config_dir.name, config_dir, logged_in, email)


def load_accounts():
    if not ACCOUNTS_DIR.is_dir():
        return []

    accounts = [read_account(entry) for entry in ACCOUNTS_DIR.iterdir() if entry.is_dir()]

    return sorted(accounts, key=lambda account: account.label.casefold())


def prepare_account_dir(config_dir):
    """Creates the account directory and its links to the shared base, returns the names that could not be linked."""
    config_dir.mkdir(parents=True, exist_ok=True)
    failed_links = []

    for name in SHARED_DIRECTORIES:
        source = SHARED_CONFIG_DIR / name
        link = config_dir / name

        if not source.is_dir() or os.path.lexists(link):
            continue

        # INFO: Junctions need no admin rights, unlike directory symlinks
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(source)], capture_output=True)

        if result.returncode != 0:
            failed_links.append(name)

    claude_md = config_dir / "CLAUDE.md"

    if not claude_md.exists():
        claude_md.write_text(CLAUDE_MD_IMPORT, encoding="utf-8")

    return failed_links


def create_account():
    ACCOUNTS_DIR.mkdir(parents=True, exist_ok=True)

    while True:
        account_id = secrets.token_hex(4)
        config_dir = ACCOUNTS_DIR / account_id

        if not config_dir.exists():
            break

    prepare_account_dir(config_dir)

    return Account(account_id, config_dir)


def login(account):
    # INFO: Interactive on purpose: Claude Code opens the browser and may prompt in this console
    try:
        return subprocess.run([find_claude_executable(), "auth", "login"], env=build_environment(account)).returncode
    except KeyboardInterrupt:
        return 1


def log_out(account):
    try:
        subprocess.run(
            [find_claude_executable(), "auth", "logout"],
            env=build_environment(account),
            capture_output=True,
            timeout=LOGOUT_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError):
        pass


def delete_account(account, logout=True):
    config_dir = account.config_dir.resolve()

    # INFO: Safety net, nothing outside ~/.claude-accounts must ever be deleted
    if config_dir.parent != ACCOUNTS_DIR.resolve():
        raise ValueError(f"Refusing to delete {config_dir}: not an account directory")

    if logout and account.logged_in:
        log_out(account)

    # INFO: Junctions are removed first so that deleting the account can never reach the shared ~/.claude content
    for entry in config_dir.iterdir():
        if os.path.isjunction(entry):
            os.rmdir(entry)

    shutil.rmtree(config_dir)
    forget_account(account)


def build_launch_command():
    command = [find_claude_executable()]

    if SHARED_SETTINGS_FILE.is_file():
        command.extend(["--settings", str(SHARED_SETTINGS_FILE)])

    return command


def load_state():
    try:
        with STATE_FILE.open("r", encoding="utf-8") as state_file:
            return json.load(state_file)
    except (json.JSONDecodeError, OSError):
        return {}


def save_state(state):
    ACCOUNTS_DIR.mkdir(parents=True, exist_ok=True)

    with STATE_FILE.open("w", encoding="utf-8") as state_file:
        json.dump(state, state_file, indent=2)


def get_account_state(state, account):
    return state.setdefault("accounts", {}).setdefault(account.account_id, {})


def load_default_dir(account):
    default_dir = get_account_state(load_state(), account).get("default_dir")

    return Path(default_dir) if default_dir else None


def save_default_dir(account, default_dir):
    state = load_state()
    get_account_state(state, account)["default_dir"] = str(default_dir)
    save_state(state)


def load_history(account):
    """Returns the last launch time of each folder opened with this account, keyed by absolute path."""
    return get_account_state(load_state(), account).get("history", {})


def record_launch(account, folder):
    state = load_state()
    get_account_state(state, account).setdefault("history", {})[str(folder)] = datetime.now(timezone.utc).isoformat()
    save_state(state)


def remove_from_history(account, folder):
    state = load_state()
    get_account_state(state, account).get("history", {}).pop(str(folder), None)
    save_state(state)


def clear_history(account):
    state = load_state()
    get_account_state(state, account).pop("history", None)
    save_state(state)


def forget_account(account):
    state = load_state()
    state.get("accounts", {}).pop(account.account_id, None)
    save_state(state)
