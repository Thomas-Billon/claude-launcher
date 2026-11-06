import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from launcher import accounts
from launcher.paths import SESSION_HOOK_SCRIPT

LAUNCHER_HOOK_COMMAND = f'"{Path(sys.executable).as_posix()}" "{SESSION_HOOK_SCRIPT.as_posix()}"'
OWN_HOOK = {"matcher": "startup", "hooks": [{"type": "command", "command": "echo own"}]}


class SettingsTestCase(unittest.TestCase):
    def setUp(self):
        temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(temp_dir.cleanup)
        self.shared_settings_file = Path(temp_dir.name) / "settings.json"
        settings_patch = patch("launcher.accounts.SHARED_SETTINGS_FILE", self.shared_settings_file)
        settings_patch.start()
        self.addCleanup(settings_patch.stop)

    def write_shared_settings(self, settings):
        self.shared_settings_file.write_text(json.dumps(settings), encoding="utf-8")

    def session_start_commands(self, settings):
        return [hook["command"] for group in settings["hooks"]["SessionStart"] for hook in group["hooks"]]


class SettingsTest(SettingsTestCase):
    def test_launcher_hook_without_shared_settings(self):
        settings = accounts.build_settings()

        self.assertEqual(self.session_start_commands(settings), [LAUNCHER_HOOK_COMMAND])

    def test_shared_settings_are_kept(self):
        self.write_shared_settings({"model": "opus", "permissions": {"allow": ["Bash(cat:*)"]}})

        settings = accounts.build_settings()

        self.assertEqual(settings["model"], "opus")
        self.assertEqual(settings["permissions"], {"allow": ["Bash(cat:*)"]})
        self.assertEqual(self.session_start_commands(settings), [LAUNCHER_HOOK_COMMAND])

    def test_own_session_start_hooks_run_next_to_the_launcher_hook(self):
        self.write_shared_settings({"hooks": {"SessionStart": [OWN_HOOK], "Stop": [OWN_HOOK]}})

        settings = accounts.build_settings()

        self.assertEqual(self.session_start_commands(settings), ["echo own", LAUNCHER_HOOK_COMMAND])
        self.assertEqual(settings["hooks"]["Stop"], [OWN_HOOK])

    def test_shared_settings_file_is_never_changed(self):
        self.write_shared_settings({"hooks": {"SessionStart": [OWN_HOOK]}})
        content = self.shared_settings_file.read_text(encoding="utf-8")

        accounts.build_settings()

        self.assertEqual(self.shared_settings_file.read_text(encoding="utf-8"), content)


class LaunchCommandTest(SettingsTestCase):
    def test_settings_are_passed_as_json(self):
        self.write_shared_settings({"model": "opus"})

        with patch("launcher.accounts.find_claude_executable", return_value="claude"):
            command = accounts.build_launch_command(["--resume", "session-1"])

        self.assertEqual(command[0], "claude")
        self.assertEqual(command[1], "--settings")
        self.assertEqual(json.loads(command[2]), accounts.build_settings())
        self.assertEqual(command[3:], ["--resume", "session-1"])
