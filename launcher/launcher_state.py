"""
State the launcher keeps per account in ~/.claude-accounts/launcher_state.json:
its name, its default folder and its favorite folders.

Accounts are keyed by their id, the name of their directory (see accounts.py).
"""

import os
from pathlib import Path

from launcher.json_store import load_json, save_json
from launcher.paths import STATE_FILE


def load_state():
    return load_json(STATE_FILE)


def save_state(state):
    save_json(STATE_FILE, state)


def get_account_state(state, account):
    return state.setdefault("accounts", {}).setdefault(account.account_id, {})


def load_names():
    """Returns the name of each account, keyed by account id."""
    return {account_id: account_state.get("name") for account_id, account_state in load_state().get("accounts", {}).items()}


def save_name(account, name):
    state = load_state()
    get_account_state(state, account)["name"] = name
    save_state(state)


def load_default_dir(account):
    default_dir = get_account_state(load_state(), account).get("default_dir")

    return Path(default_dir) if default_dir else None


def save_default_dir(account, default_dir):
    state = load_state()
    get_account_state(state, account)["default_dir"] = str(default_dir)
    save_state(state)


def load_favorites(account):
    """Returns the favorite folders of the account, sorted by folder name then full path."""
    favorites = get_account_state(load_state(), account).get("favorites", [])

    return sorted((Path(folder) for folder in favorites), key=lambda folder: (folder.name.casefold(), str(folder).casefold()))


def toggle_favorite(account, folder):
    """Adds the folder to the favorites of the account or removes it, returns True when it is now a favorite."""
    state = load_state()
    account_state = get_account_state(state, account)
    favorites = account_state.get("favorites", [])
    remaining = [favorite for favorite in favorites if os.path.normcase(favorite) != os.path.normcase(folder)]
    is_favorite = len(remaining) == len(favorites)

    if is_favorite:
        remaining.append(str(folder))

    account_state["favorites"] = remaining
    save_state(state)

    return is_favorite


def forget_account(account):
    state = load_state()
    state.get("accounts", {}).pop(account.account_id, None)
    save_state(state)
