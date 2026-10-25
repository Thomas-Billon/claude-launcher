"""
State the launcher keeps per account in ~/.claude-accounts/launcher_state.json:
its name, its default folder, and the last launch time of the folders recently opened with it.

Accounts are keyed by their id, the name of their directory (see accounts.py).
"""

from datetime import datetime, timezone
from pathlib import Path

from launcher.json_store import load_json, save_json
from launcher.paths import STATE_FILE

# INFO: Also the number of recent folders listed on top of the folder menu
HISTORY_SIZE = 5


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


def load_history(account):
    """Returns the last launch time of each folder opened with this account, keyed by absolute path."""
    return get_account_state(load_state(), account).get("history", {})


def prune_history(history):
    """Returns the most recently launched folders that still exist, latest first, at most HISTORY_SIZE."""
    launched = sorted(history, key=history.get, reverse=True)
    kept = [folder for folder in launched if Path(folder).is_dir()][:HISTORY_SIZE]

    return {folder: history[folder] for folder in kept}


def record_launch(account, folder):
    state = load_state()
    account_state = get_account_state(state, account)
    history = {**account_state.get("history", {}), str(folder): datetime.now(timezone.utc).isoformat()}
    account_state["history"] = prune_history(history)
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
