"""
Claude accounts, each isolated in its own Claude Code config directory.

Every account lives in ~/.claude-accounts/<id>/ and Claude Code is pointed at it
through the CLAUDE_CONFIG_DIR environment variable. Credentials are only ever
handled by Claude Code itself, which asks for a login when launched with a logged
out account (and `claude auth logout` on deletion): this module never reads them
and stores no email address. Each account has the name typed when adding it
(see launcher_state.py), and the email of the profile Claude Code keeps in its
directory (.claude.json).

~/.claude stays the shared base (fed by the shared skills repo, if any): each
account directory links its skills and plugins through junctions, imports its
CLAUDE.md, and receives its settings.json through `claude --settings`.
"""

import json
import os
import secrets
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from launcher import launcher_state
from launcher.paths import ACCOUNTS_DIR, SHARED_CONFIG_DIR, SHARED_SETTINGS_FILE
from launcher.terminal_ui import GREEN, HeaderLine

SHARED_DIRECTORIES = ("skills", "plugins")
CLAUDE_MD_IMPORT = "@~/.claude/CLAUDE.md\n"
LOGOUT_TIMEOUT_SECONDS = 30


@dataclass
class Account:
    account_id: str
    config_dir: Path
    logged_in: bool = False
    email: str | None = None
    name: str | None = None

    @property
    def display_name(self):
        # INFO: Accounts added before names existed fall back to their email
        return self.name or self.email or f"Unknown account {self.account_id}"

    @property
    def label(self):
        return self.display_name if self.logged_in else f"{self.display_name} (logged out)"

    @property
    def secondary_label(self):
        return self.email if self.name else None


def account_header_line(account):
    return HeaderLine("Account", account.label, GREEN)


def find_claude_executable():
    return shutil.which("claude")


def build_environment(account):
    return {**os.environ, "CLAUDE_CONFIG_DIR": str(account.config_dir)}


def build_launch_command(claude_arguments=()):
    command = [find_claude_executable()]

    if SHARED_SETTINGS_FILE.is_file():
        command.extend(["--settings", str(SHARED_SETTINGS_FILE)])

    return command + list(claude_arguments)


def read_account(config_dir, name=None):
    try:
        profile = json.loads((config_dir / ".claude.json").read_text(encoding="utf-8"))
        email = profile.get("oauthAccount", {}).get("emailAddress")
    except (OSError, json.JSONDecodeError, AttributeError):
        email = None

    # INFO: Only the presence of the credentials file is checked, its content is never read
    logged_in = email is not None and (config_dir / ".credentials.json").is_file()

    return Account(config_dir.name, config_dir, logged_in, email, name)


def load_accounts():
    if not ACCOUNTS_DIR.is_dir():
        return []

    names = launcher_state.load_names()
    accounts = [read_account(entry, names.get(entry.name)) for entry in ACCOUNTS_DIR.iterdir() if entry.is_dir()]

    return sorted(accounts, key=lambda account: account.label.casefold())


def find_accounts(query):
    """Returns the accounts whose name, email or id is the query, ignoring case."""
    query = query.casefold()

    return [
        account
        for account in load_accounts()
        if query in (value.casefold() for value in (account.name, account.email, account.account_id) if value)
    ]


def find_duplicate(account):
    """Returns another account logged in with the same email, once Claude Code has logged this one in."""
    account_list = load_accounts()
    email = next((other.email for other in account_list if other.account_id == account.account_id), None)

    if email is None:
        return None

    return next((other for other in account_list if other.account_id != account.account_id and other.email == email), None)


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


def create_account(name):
    ACCOUNTS_DIR.mkdir(parents=True, exist_ok=True)

    while True:
        account_id = secrets.token_hex(4)
        config_dir = ACCOUNTS_DIR / account_id

        if not config_dir.exists():
            break

    prepare_account_dir(config_dir)
    account = Account(account_id, config_dir, name=name)
    launcher_state.save_name(account, name)

    return account


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


def delete_account(account):
    config_dir = account.config_dir.resolve()

    # INFO: Safety net, nothing outside ~/.claude-accounts must ever be deleted
    if config_dir.parent != ACCOUNTS_DIR.resolve():
        raise ValueError(f"Refusing to delete {config_dir}: not an account directory")

    if account.logged_in:
        log_out(account)

    # INFO: Junctions are removed first so that deleting the account can never reach the shared ~/.claude content
    for entry in config_dir.iterdir():
        if os.path.isjunction(entry):
            os.rmdir(entry)

    shutil.rmtree(config_dir)
    launcher_state.forget_account(account)
