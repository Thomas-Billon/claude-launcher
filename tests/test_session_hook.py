import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from launcher.paths import SESSION_HOOK_SCRIPT
from launcher.sessions_state import ENTRY_VARIABLE


class SessionHookTest(unittest.TestCase):
    """Runs the hook script as Claude Code does, with a temporary home directory."""

    def setUp(self):
        temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(temp_dir.cleanup)
        self.home = Path(temp_dir.name).resolve()
        self.sessions_state_file = self.home / ".claude-accounts" / "sessions_state.json"
        self.sessions_state_file.parent.mkdir()
        entry = {
            "account_id": "a1b2c3d4",
            "folder": str(self.home),
            "worktree": None,
            "session_id": None,
            "launcher_pid": os.getpid(),
            "launcher_started_at": 0.0,
        }
        self.sessions_state_file.write_text(json.dumps({"sessions": {"e1": entry}}), encoding="utf-8")

    def run_hook(self, hook_input, entry_id="e1"):
        environment = {**os.environ, "USERPROFILE": str(self.home), "HOME": str(self.home)}
        environment.pop(ENTRY_VARIABLE, None)

        if entry_id is not None:
            environment[ENTRY_VARIABLE] = entry_id

        return subprocess.run(
            [sys.executable, str(SESSION_HOOK_SCRIPT)],
            input=hook_input,
            env=environment,
            cwd=self.home,
            capture_output=True,
            text=True,
        )

    def recorded_session_id(self):
        return json.loads(self.sessions_state_file.read_text(encoding="utf-8"))["sessions"]["e1"]["session_id"]

    def test_startup_records_the_conversation(self):
        result = self.run_hook(json.dumps({"session_id": "session-1", "source": "startup"}))

        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.recorded_session_id(), "session-1")

    def test_clear_and_resume_record_the_new_conversation(self):
        for source, session_id in (("clear", "session-2"), ("resume", "session-3")):
            self.run_hook(json.dumps({"session_id": session_id, "source": source}))

            self.assertEqual(self.recorded_session_id(), session_id)

    def test_hook_prints_nothing(self):
        result = self.run_hook(json.dumps({"session_id": "session-1", "source": "startup"}))

        self.assertEqual(result.stdout, "")

    def test_session_not_launched_by_the_launcher_is_ignored(self):
        result = self.run_hook(json.dumps({"session_id": "session-1", "source": "startup"}), entry_id=None)

        self.assertEqual(result.returncode, 0)
        self.assertIsNone(self.recorded_session_id())

    def test_invalid_input_never_fails_claude_code(self):
        for hook_input in ("", "not json", json.dumps({"source": "startup"})):
            result = self.run_hook(hook_input)

            self.assertEqual(result.returncode, 0, hook_input)
            self.assertEqual(result.stdout, "", hook_input)
            self.assertIsNone(self.recorded_session_id())
