import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from launcher import processes, sessions_state
from launcher.accounts import Account
from launcher.worktrees import Worktree

# INFO: Start time no process has, so that an entry with the current process id counts as closed
CLOSED_LAUNCHER_STARTED_AT = 0.0


class SessionsStateTestCase(unittest.TestCase):
    def setUp(self):
        temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(temp_dir.cleanup)
        self.root = Path(temp_dir.name).resolve()
        self.sessions_state_file = self.root / "sessions_state.json"
        state_patch = patch("launcher.sessions_state.SESSIONS_STATE_FILE", self.sessions_state_file)
        state_patch.start()
        self.addCleanup(state_patch.stop)

    def read_sessions(self):
        if not self.sessions_state_file.exists():
            return {}

        return json.loads(self.sessions_state_file.read_text(encoding="utf-8")).get("sessions", {})

    def write_entry(self, entry_id, account_id, folder, worktree=None, session_id=None, is_running=False):
        """Writes an entry as a previous launcher did, closed unless is_running."""
        sessions = self.read_sessions()
        started_at = processes.read_start_time(os.getpid()) if is_running else CLOSED_LAUNCHER_STARTED_AT
        sessions[entry_id] = {
            "account_id": account_id,
            "folder": str(folder),
            "worktree": str(worktree) if worktree is not None else None,
            "session_id": session_id,
            "launcher_pid": os.getpid(),
            "launcher_started_at": started_at,
        }
        self.sessions_state_file.write_text(json.dumps({"sessions": sessions}), encoding="utf-8")


class RegisterTest(SessionsStateTestCase):
    def setUp(self):
        super().setUp()
        self.account = Account("a1b2c3d4", self.root / "a1b2c3d4", name="Perso")
        self.folder = self.root / "repo"
        self.worktree = Worktree("export-pdf", self.root / "worktrees" / "export-pdf", self.folder, "dev")

    def test_entry_holds_the_account_folder_and_launcher(self):
        entry_id = sessions_state.register_session(self.account, self.folder, None)

        self.assertEqual(
            self.read_sessions()[entry_id],
            {
                "account_id": "a1b2c3d4",
                "folder": str(self.folder),
                "worktree": None,
                "session_id": None,
                "launcher_pid": os.getpid(),
                "launcher_started_at": processes.read_start_time(os.getpid()),
            },
        )

    def test_entry_holds_the_worktree_path(self):
        entry_id = sessions_state.register_session(self.account, self.folder, self.worktree)

        self.assertEqual(self.read_sessions()[entry_id]["worktree"], str(self.worktree.path))

    def test_each_session_has_its_own_entry(self):
        first_id = sessions_state.register_session(self.account, self.folder, None)
        second_id = sessions_state.register_session(self.account, self.folder, None)

        self.assertNotEqual(first_id, second_id)
        self.assertEqual(set(self.read_sessions()), {first_id, second_id})

    def test_entries_are_loaded_with_their_paths(self):
        entry_id = sessions_state.register_session(self.account, self.folder, self.worktree)
        sessions_state.record_session_id(entry_id, "session-1")

        self.assertEqual(
            sessions_state.load_entries(),
            [
                sessions_state.SessionEntry(
                    entry_id,
                    "a1b2c3d4",
                    self.folder,
                    self.worktree.path,
                    "session-1",
                    os.getpid(),
                    processes.read_start_time(os.getpid()),
                )
            ],
        )

    def test_no_file_means_no_entries(self):
        self.assertEqual(sessions_state.load_entries(), [])

    def test_concurrent_registrations_are_all_kept(self):
        entry_ids = []

        def register():
            entry_ids.append(sessions_state.register_session(self.account, self.folder, None))

        threads = [threading.Thread(target=register) for _ in range(20)]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        self.assertEqual(set(self.read_sessions()), set(entry_ids))
        self.assertEqual(len(entry_ids), 20)


class ConversationTest(SessionsStateTestCase):
    def test_hook_records_the_conversation(self):
        self.write_entry("e1", "a1b2c3d4", self.root, is_running=True)

        sessions_state.record_session_id("e1", "session-1")

        self.assertEqual(self.read_sessions()["e1"]["session_id"], "session-1")

    def test_clear_or_resume_replaces_the_conversation(self):
        self.write_entry("e1", "a1b2c3d4", self.root, session_id="session-1", is_running=True)

        sessions_state.record_session_id("e1", "session-2")

        self.assertEqual(self.read_sessions()["e1"]["session_id"], "session-2")

    def test_unknown_entry_is_not_created(self):
        self.write_entry("e1", "a1b2c3d4", self.root, is_running=True)

        sessions_state.record_session_id("unknown", "session-1")

        self.assertEqual(set(self.read_sessions()), {"e1"})


class RemovalTest(SessionsStateTestCase):
    def setUp(self):
        super().setUp()

        for entry_id in ("e1", "e2", "e3"):
            self.write_entry(entry_id, "a1b2c3d4", self.root)

    def test_unregister_removes_only_its_entry(self):
        sessions_state.unregister_session("e2")

        self.assertEqual(set(self.read_sessions()), {"e1", "e3"})

    def test_forget_removes_several_entries(self):
        sessions_state.forget_sessions(["e1", "e3"])

        self.assertEqual(set(self.read_sessions()), {"e2"})

    def test_removing_a_missing_entry_does_nothing(self):
        sessions_state.forget_sessions(["unknown"])
        sessions_state.unregister_session("unknown")

        self.assertEqual(set(self.read_sessions()), {"e1", "e2", "e3"})


class ClaimTest(SessionsStateTestCase):
    def test_claimed_entries_get_the_current_launcher(self):
        self.write_entry("e1", "a1b2c3d4", self.root)
        self.write_entry("e2", "a1b2c3d4", self.root)

        sessions_state.claim_sessions(["e1"])

        sessions = self.read_sessions()
        self.assertEqual(sessions["e1"]["launcher_started_at"], processes.read_start_time(os.getpid()))
        self.assertEqual(sessions["e2"]["launcher_started_at"], CLOSED_LAUNCHER_STARTED_AT)
