"""
Restore of the Claude Code sessions left open at the previous close (see sessions_state.py).

A closed session is restorable when its account, folder, worktree and conversation still exist. A session whose
launcher still runs is left alone. The others are forgotten: silently without a conversation (closed before any
message), else shown once with the reason.

The first restored session is resumed in the current tab, the others open in Windows Terminal, as tabs of the window
or as new windows, as chosen at install (terminal_window key of config.json).
"""

import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from launcher import accounts, history, processes, sessions_state, worktrees
from launcher.accounts import Account
from launcher.json_store import load_json
from launcher.paths import CONFIG_FILE, LAUNCHER_SCRIPT
from launcher.terminal_ui import YELLOW, HeaderLine
from launcher.worktrees import Worktree

# INFO: wt window id of the most recently used window, for installs older than the terminal_window key
CURRENT_WINDOW = "0"
TERMINAL_PROFILE_NAME = "Claude Code"
RESTORE_SESSION_ARGUMENT = "--restore-session"

ACCOUNT_NOT_FOUND = "account not found"
FOLDER_NOT_FOUND = "folder not found"
WORKTREE_NOT_FOUND = "worktree not found"

LABEL_SEPARATOR = " · "


def format_label(account_name, folder, worktree_name):
    """Returns `account · project · worktree`, each part left out when missing."""
    parts = [account_name, folder.name or str(folder), worktree_name]

    return LABEL_SEPARATOR.join(part for part in parts if part)


@dataclass(frozen=True)
class RestorableSession:
    entry_id: str
    account: Account
    folder: Path
    worktree: Worktree | None
    session_id: str
    last_message_at: datetime

    @property
    def label(self):
        return format_label(self.account.display_name, self.folder, self.worktree.name if self.worktree else None)


@dataclass(frozen=True)
class RejectedSession:
    # INFO: Without the account when it no longer exists
    label: str
    reason: str


def find_worktree(entry):
    """Returns the worktree of the entry among those of its repo, or None when it no longer exists."""
    repo = worktrees.find_repo_root(entry.folder)

    if repo is None:
        return None

    return next((worktree for worktree in worktrees.load_worktrees(repo) if worktree.path == entry.worktree), None)


def find_last_message_date(account, entry, worktree):
    """Returns the date of the last message of the conversation of the entry, or None before any message."""
    if entry.session_id is None:
        return None

    conversation = history.get_conversation_file(account.config_dir, worktree.repo if worktree else entry.folder, entry.session_id)

    if not conversation.is_file():
        return None

    return datetime.fromtimestamp(conversation.stat().st_mtime)


def examine_entry(entry):
    """Returns the restorable session of the entry, a RejectedSession with the reason it cannot be restored, or None
    when it was closed before any message."""
    account = accounts.find_account(entry.account_id)
    account_name = account.display_name if account else None
    worktree_name = entry.worktree.name if entry.worktree else None
    rejected_label = format_label(account_name, entry.folder, worktree_name)

    if account is None:
        return RejectedSession(rejected_label, ACCOUNT_NOT_FOUND)

    if not entry.folder.is_dir():
        return RejectedSession(rejected_label, FOLDER_NOT_FOUND)

    worktree = find_worktree(entry) if entry.worktree else None

    if entry.worktree and worktree is None:
        return RejectedSession(rejected_label, WORKTREE_NOT_FOUND)

    last_message_at = find_last_message_date(account, entry, worktree)

    if last_message_at is None:
        return None

    return RestorableSession(entry.entry_id, account, entry.folder, worktree, entry.session_id, last_message_at)


def find_restorable_sessions():
    """Returns the restorable sessions, most recent message first, and the rejected ones. Rejected sessions and
    sessions without conversation are forgotten, restorable ones are kept until the user picks them."""
    restorable_sessions = []
    rejected_sessions = []
    forgotten_entry_ids = []

    for entry in sessions_state.load_entries():
        if processes.is_running(entry.launcher_pid, entry.launcher_started_at):
            continue

        session = examine_entry(entry)

        if isinstance(session, RestorableSession):
            restorable_sessions.append(session)

            continue

        if isinstance(session, RejectedSession):
            rejected_sessions.append(session)

        forgotten_entry_ids.append(entry.entry_id)

    if forgotten_entry_ids:
        sessions_state.forget_sessions(forgotten_entry_ids)

    restorable_sessions.sort(key=lambda session: session.last_message_at, reverse=True)

    return restorable_sessions, rejected_sessions


def load_restorable_session(entry_id):
    """Returns the session of the entry, even while another launcher runs it, or None when it cannot be restored."""
    entry = next((entry for entry in sessions_state.load_entries() if entry.entry_id == entry_id), None)
    session = examine_entry(entry) if entry else None

    return session if isinstance(session, RestorableSession) else None


def rejection_header_line(rejected_session):
    return HeaderLine("Restore", f"{rejected_session.label}  ({rejected_session.reason})", YELLOW)


def load_terminal_window():
    """Returns the wt window id restored sessions open in: claude-launcher, new, or the current window."""
    terminal_window = load_json(CONFIG_FILE).get("terminal_window")

    return terminal_window if isinstance(terminal_window, str) and terminal_window else CURRENT_WINDOW


def is_windows_terminal():
    return "WT_SESSION" in os.environ


def build_restore_tab_command(entry_id, window):
    return [
        "wt",
        "-w",
        window,
        "new-tab",
        "-p",
        TERMINAL_PROFILE_NAME,
        sys.executable,
        str(LAUNCHER_SCRIPT),
        RESTORE_SESSION_ARGUMENT,
        entry_id,
    ]


def open_in_new_tabs(sessions):
    """Opens each session in a new launcher tab (or window, as chosen at install), which resumes it without any menu."""
    window = load_terminal_window()

    for session in sessions:
        subprocess.Popen(build_restore_tab_command(session.entry_id, window))
