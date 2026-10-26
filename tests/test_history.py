import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from launcher import history, junctions


def make_junction(link, target):
    link.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True, capture_output=True)


def write_conversation(history_dir, session_id, cwd, age_seconds, has_summary_first=False):
    """Writes a conversation file as Claude Code does, one JSON object per line, dated age_seconds ago."""
    history_dir.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps({"type": "summary", "summary": "Earlier work"})] if has_summary_first else []
    lines.append(json.dumps({"type": "user", "cwd": str(cwd), "sessionId": session_id}))
    conversation = history_dir / f"{session_id}.jsonl"
    conversation.write_text("\n".join(lines) + "\n", encoding="utf-8")
    timestamp = time.time() - age_seconds
    os.utime(conversation, (timestamp, timestamp))


class HistoryTestCase(unittest.TestCase):
    def setUp(self):
        temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(temp_dir.cleanup)
        self.root = Path(temp_dir.name).resolve()
        self.config_dir = self.root / "account"
        self.projects_dir = self.config_dir / "projects"
        self.repo = self.root / "Projets" / "shope"
        self.worktree_path = self.root / "worktrees" / "a1b2c3d4" / "export-pdf"
        self.repo_history = self.projects_dir / history.encode_path(self.repo)
        self.worktree_history = self.projects_dir / history.encode_path(self.worktree_path)


class EncodingTest(HistoryTestCase):
    def test_every_character_but_ascii_letters_and_digits_becomes_a_dash(self):
        self.assertEqual(
            history.encode_path(Path("C:/Users/Thomas/.claude-worktrees/eacb054f/dev-13")),
            "C--Users-Thomas--claude-worktrees-eacb054f-dev-13",
        )
        self.assertEqual(history.encode_path(Path("C:/Projets/Perso/claude_launcher")), "C--Projets-Perso-claude-launcher")
        self.assertEqual(history.encode_path(Path("D:/Café 2")), "D--Caf--2")

    def test_history_dir_is_in_the_projects_folder_of_the_account(self):
        self.assertEqual(history.get_history_dir(self.config_dir, self.repo), self.projects_dir / history.encode_path(self.repo))


class JunctionTest(HistoryTestCase):
    def test_junction_is_created(self):
        target = self.root / "target"
        target.mkdir()
        link = self.root / "link"

        self.assertTrue(junctions.create_junction(link, target))
        self.assertTrue(os.path.isjunction(link))
        self.assertEqual(Path(os.path.realpath(link)), target)

    def test_existing_link_is_a_failure(self):
        target = self.root / "target"
        target.mkdir()
        link = self.root / "link"
        link.mkdir()

        self.assertFalse(junctions.create_junction(link, target))
        self.assertFalse(os.path.isjunction(link))


class LinkTest(HistoryTestCase):
    def test_worktree_history_becomes_a_junction_to_the_repo_history(self):
        self.assertTrue(history.link_worktree_history(self.config_dir, self.worktree_path, self.repo))

        self.assertTrue(self.repo_history.is_dir())
        self.assertTrue(os.path.isjunction(self.worktree_history))
        self.assertEqual(Path(os.path.realpath(self.worktree_history)), Path(os.path.realpath(self.repo_history)))

    def test_existing_repo_history_is_kept(self):
        write_conversation(self.repo_history, "main-session", self.repo, 10)

        history.link_worktree_history(self.config_dir, self.worktree_path, self.repo)

        self.assertTrue((self.repo_history / "main-session.jsonl").is_file())
        self.assertTrue((self.worktree_history / "main-session.jsonl").is_file())

    def test_conversation_of_the_worktree_lands_in_the_repo_history(self):
        history.link_worktree_history(self.config_dir, self.worktree_path, self.repo)
        write_conversation(self.worktree_history, "worktree-session", self.worktree_path, 0)

        self.assertTrue((self.repo_history / "worktree-session.jsonl").is_file())

    def test_existing_junction_is_kept(self):
        history.link_worktree_history(self.config_dir, self.worktree_path, self.repo)

        self.assertTrue(history.link_worktree_history(self.config_dir, self.worktree_path, self.repo))
        self.assertTrue(os.path.isjunction(self.worktree_history))

    def test_real_history_folder_is_left_untouched(self):
        write_conversation(self.worktree_history, "old-session", self.worktree_path, 10)

        history.link_worktree_history(self.config_dir, self.worktree_path, self.repo)

        self.assertFalse(os.path.isjunction(self.worktree_history))
        self.assertTrue((self.worktree_history / "old-session.jsonl").is_file())
        self.assertFalse((self.repo_history / "old-session.jsonl").exists())


class LastSessionTest(HistoryTestCase):
    def test_most_recent_conversation_of_the_folder_is_found(self):
        write_conversation(self.repo_history, "worktree-old", self.worktree_path, 300)
        write_conversation(self.repo_history, "worktree-recent", self.worktree_path, 200)
        write_conversation(self.repo_history, "main-latest", self.repo, 100)

        self.assertEqual(history.find_last_session(self.config_dir, self.repo, self.worktree_path), "worktree-recent")
        self.assertEqual(history.find_last_session(self.config_dir, self.repo, self.repo), "main-latest")

    def test_cwd_is_read_past_the_lines_without_it(self):
        write_conversation(self.repo_history, "summarized", self.worktree_path, 100, has_summary_first=True)

        self.assertEqual(history.find_last_session(self.config_dir, self.repo, self.worktree_path), "summarized")

    def test_invalid_lines_are_skipped(self):
        write_conversation(self.repo_history, "valid", self.worktree_path, 200)
        self.repo_history.joinpath("broken.jsonl").write_text("{not json\n", encoding="utf-8")

        self.assertEqual(history.find_last_session(self.config_dir, self.repo, self.worktree_path), "valid")

    def test_no_conversation_of_the_folder_gives_none(self):
        write_conversation(self.repo_history, "main-only", self.repo, 100)

        self.assertIsNone(history.find_last_session(self.config_dir, self.repo, self.worktree_path))

    def test_missing_history_gives_none(self):
        self.assertIsNone(history.find_last_session(self.config_dir, self.repo, self.worktree_path))


class StaleLinkTest(HistoryTestCase):
    def test_links_of_worktrees_git_no_longer_knows_are_removed(self):
        write_conversation(self.repo_history, "kept-session", self.repo, 10)
        removed_path = self.worktree_path.parent / "removed"
        removed_link = self.projects_dir / history.encode_path(removed_path)
        make_junction(self.worktree_history, self.repo_history)
        make_junction(removed_link, self.repo_history)

        history.remove_stale_links(self.config_dir, self.repo, {self.repo, self.worktree_path})

        self.assertFalse(os.path.lexists(removed_link))
        self.assertTrue(os.path.isjunction(self.worktree_history))
        self.assertTrue((self.repo_history / "kept-session.jsonl").is_file())

    def test_links_to_another_history_and_real_folders_are_kept(self):
        self.repo_history.mkdir(parents=True)
        other_history = self.projects_dir / history.encode_path(self.root / "Projets" / "other")
        other_history.mkdir(parents=True)
        other_link = self.projects_dir / history.encode_path(self.root / "worktrees" / "e5f6a7b8" / "other-wt")
        make_junction(other_link, other_history)
        real_folder = self.projects_dir / history.encode_path(self.worktree_path.parent / "real")
        real_folder.mkdir()

        history.remove_stale_links(self.config_dir, self.repo, {self.repo})

        self.assertTrue(os.path.isjunction(other_link))
        self.assertTrue(real_folder.is_dir())
        self.assertTrue(self.repo_history.is_dir())

    def test_missing_projects_folder_is_ignored(self):
        history.remove_stale_links(self.config_dir, self.repo, {self.repo})
