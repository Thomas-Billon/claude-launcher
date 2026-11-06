"""
Claude Code sessions opened by the launcher, kept in ~/.claude-accounts/sessions_state.json for every account, so that
the sessions left open at the previous close can be restored (see session_restore.py).

An entry is registered before `claude` starts and removed when it exits normally. A closed tab or window, or a
shutdown, kills the launcher with it: the entry stays. The SessionStart hook (session_hook.py) records in the entry the
id of the current conversation, the entry being found through the ENTRY_VARIABLE environment variable of `claude`.

Several launchers write the file at the same time: every change is made under a lock.
"""

import msvcrt
import os
import secrets
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from launcher import processes
from launcher.json_store import load_json, save_json
from launcher.paths import SESSIONS_STATE_FILE

# INFO: Set for `claude`, and inherited by the hooks it runs
ENTRY_VARIABLE = "CLAUDE_LAUNCHER_SESSION"
LOCK_RETRY_SECONDS = 0.02


@dataclass(frozen=True)
class SessionEntry:
    entry_id: str
    account_id: str
    folder: Path
    # INFO: Path of the worktree where `claude` runs, None in the folder itself
    worktree: Path | None
    # INFO: None until the SessionStart hook records it
    session_id: str | None
    launcher_pid: int
    launcher_started_at: float


def load_state():
    return load_json(SESSIONS_STATE_FILE)


@contextmanager
def lock_state():
    """Holds the lock on the state file, so that a launcher or a hook running in parallel waits for the change in progress."""
    SESSIONS_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

    with SESSIONS_STATE_FILE.with_name("sessions_state.lock").open("a+b") as lock_file:
        while True:
            try:
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                time.sleep(LOCK_RETRY_SECONDS)

        try:
            yield
        finally:
            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)


def save_state(state):
    save_json(SESSIONS_STATE_FILE, state)


def get_entries(state):
    return state.setdefault("sessions", {})


def describe_current_launcher():
    return {"launcher_pid": os.getpid(), "launcher_started_at": processes.read_start_time(os.getpid())}


def load_entries():
    return [
        SessionEntry(
            entry_id,
            entry["account_id"],
            Path(entry["folder"]),
            Path(entry["worktree"]) if entry["worktree"] else None,
            entry["session_id"],
            entry["launcher_pid"],
            entry["launcher_started_at"],
        )
        for entry_id, entry in get_entries(load_state()).items()
    ]


def register_session(account, folder, worktree):
    """Adds an entry for the session about to start in the folder or the worktree (None for the folder), launched by
    the current process. Returns its entry id."""
    entry_id = secrets.token_hex(4)

    with lock_state():
        state = load_state()
        entries = get_entries(state)

        while entry_id in entries:
            entry_id = secrets.token_hex(4)

        entries[entry_id] = {
            "account_id": account.account_id,
            "folder": str(folder),
            "worktree": str(worktree.path) if worktree else None,
            "session_id": None,
            **describe_current_launcher(),
        }
        save_state(state)

    return entry_id


def claim_sessions(entry_ids):
    """Makes the current process the launcher of the entries, which are then neither offered nor forgotten by another
    launcher while it runs."""
    with lock_state():
        state = load_state()
        entries = get_entries(state)

        for entry_id in entry_ids:
            if entry_id in entries:
                entries[entry_id].update(describe_current_launcher())

        save_state(state)


def record_session_id(entry_id, session_id):
    """Records the id of the current session of the entry, ignored when the entry no longer exists."""
    with lock_state():
        state = load_state()
        entries = get_entries(state)

        if entry_id in entries:
            entries[entry_id]["session_id"] = session_id
            save_state(state)


def unregister_session(entry_id):
    forget_sessions([entry_id])


def forget_sessions(entry_ids):
    with lock_state():
        state = load_state()
        entries = get_entries(state)

        for entry_id in entry_ids:
            entries.pop(entry_id, None)

        save_state(state)
