"""
Repo syncs run on startup, before the menus: the launcher repo, then the shared
skills repo set in config.json (written by install.ps1), each with its header line.

Each repo is fetched, then every action is asked first (Y/N). The launcher repo
is only pulled, the skills repo is fully synced:
1. uncommitted changes are listed, committed (message editable), then pushed;
2. new remote commits are pulled;
3. commits of its base repo (upstream remote) are merged, committed (message
   editable) and pushed;
4. local commits not on the remote yet are pushed, asked first unless a push was
   already confirmed in step 1 or 3.

After a pull or a merge, the install.ps1 of the skills repo, if any, is run so
skills and the global CLAUDE.md are up to date before Claude Code starts. A
failure never blocks the launch: it is only reported on the repo line.
"""

import json
import subprocess
from pathlib import Path

from launcher import git_repo
from launcher.paths import CONFIG_FILE, LAUNCHER_REPO
from launcher.prompts import ask_commit_message, ask_yes_no
from launcher.terminal_ui import DARK_GRAY, GREEN, YELLOW, HeaderLine, render_screen

INSTALL_WARNINGS_MARKER = "__INSTALL_WARNINGS__"

LAUNCHER_LABEL = "Launcher"
SKILLS_LABEL = "Skills"
SKILLS_COMMIT_MESSAGE = "Updated skills"
BASE_MERGE_MESSAGE = "Merged base repo updates"


def pluralize(count, noun):
    return f"{count} {noun}{'s' if count > 1 else ''}"


def describe_new_commits(behind, base_behind):
    if not base_behind:
        return pluralize(behind, "new commit")

    if not behind:
        return f"{pluralize(base_behind, 'new commit')} on the base repo"

    return f"{pluralize(behind, 'new commit')} on your repo, {base_behind} on the base repo"


def load_skills_repo():
    try:
        skills_repo = json.loads(CONFIG_FILE.read_text(encoding="utf-8")).get("skills_repo")
    except (OSError, json.JSONDecodeError, AttributeError):
        return None

    return Path(skills_repo) if isinstance(skills_repo, str) and skills_repo else None


def build_install_command(install_script):
    # INFO: Warnings are read from the warning stream rather than the output text, which PowerShell localizes
    escaped_path = str(install_script).replace("'", "''")
    script = (
        f"$warnings = & '{escaped_path}' 3>&1 | Where-Object {{ $_ -is [System.Management.Automation.WarningRecord] }}; "
        "if ($LASTEXITCODE) { exit $LASTEXITCODE }; "
        f"if ($warnings) {{ Write-Output '{INSTALL_WARNINGS_MARKER}' }}"
    )

    return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script]


class RepoSync:
    """Sync of one repo with its remote, whose outcomes are joined on the repo header line."""

    def __init__(self, repo, label, previous_lines):
        self.repo = repo
        self.label = label
        # INFO: Header lines of the steps run before this one, kept above the repo line while it is synced
        self.previous_lines = previous_lines
        self.outcomes = []
        self.has_warning = False
        self.is_updated = False
        self.is_push_confirmed = False

    @property
    def header_line(self):
        if not self.outcomes:
            return HeaderLine(self.label, "up to date", GREEN)

        return HeaderLine(self.label, ", ".join(self.outcomes), YELLOW if self.has_warning else GREEN)

    def report(self, outcome, is_warning=False):
        self.outcomes.append(outcome)
        self.has_warning = self.has_warning or is_warning

    def show_progress(self, text):
        render_screen([*self.previous_lines, HeaderLine(self.label, text, DARK_GRAY)])

    def ask(self, status, question, details=()):
        return ask_yes_no([*self.previous_lines, HeaderLine(self.label, status, YELLOW)], question, details)

    def ask_message(self, status, default_message):
        return ask_commit_message([*self.previous_lines, HeaderLine(self.label, status, YELLOW)], default_message)

    def run(self, commit_message=None, with_base=False, with_install=False):
        """Without a commit message, the repo is only pulled: nothing is committed nor pushed."""
        try:
            self.sync(commit_message, with_base)

            if with_install and self.is_updated:
                self.run_install_script()
        except subprocess.TimeoutExpired:
            self.report("git timed out", is_warning=True)
        except OSError:
            self.report("git not found", is_warning=True)

    def sync(self, commit_message, with_base):
        self.show_progress("checking updates…")

        if not git_repo.fetch(self.repo):
            self.report("update failed (fetch error)", is_warning=True)

            return

        has_base = with_base and self.fetch_base()

        if commit_message is not None:
            self.commit_changes(commit_message)

        behind = git_repo.count_commits(self.repo, f"HEAD..{git_repo.UPSTREAM_BRANCH}")

        if behind is None:
            self.report("update failed (no upstream branch)", is_warning=True)

            return

        base_behind = self.count_base_commits() if has_base else 0

        # INFO: The remote rejects a push while its commits are not pulled, so a declined or failed pull stops here
        if (behind or base_behind) and not self.pull(behind, base_behind):
            return

        if commit_message is not None:
            self.push()

    def fetch_base(self):
        """Returns whether the repo has a base repo (upstream remote) that could be fetched."""
        if not git_repo.has_base(self.repo):
            return False

        if not git_repo.fetch_base(self.repo):
            self.report("base check failed", is_warning=True)

            return False

        return True

    def count_base_commits(self):
        base_behind = git_repo.count_commits(self.repo, f"HEAD..{git_repo.BASE_BRANCH}")

        if base_behind is None:
            self.report("base check failed", is_warning=True)

            return 0

        return base_behind

    def commit_changes(self, commit_message):
        changed_files = git_repo.list_changed_files(self.repo)

        if not changed_files:
            return

        status = pluralize(len(changed_files), "changed file")
        message = self.ask(status, "Commit & push?", changed_files) and self.ask_message(status, commit_message)

        if not message:
            self.report(f"{status} not committed", is_warning=True)
        elif not git_repo.commit_all(self.repo, message):
            self.report("commit failed", is_warning=True)
        else:
            self.is_push_confirmed = True

    def pull(self, behind, base_behind):
        """Returns whether the remote commits are pulled, so local commits can be pushed."""
        status = describe_new_commits(behind, base_behind)

        if not self.ask(status, "Pull?"):
            self.report(f"{status} skipped", is_warning=True)

            return not behind

        if behind:
            self.show_progress("pulling…")

            if not git_repo.pull(self.repo):
                self.report("pull failed, sync by hand", is_warning=True)

                return False

            self.report(f"pulled {pluralize(behind, 'new commit')}")
            self.is_updated = True

        if base_behind:
            self.merge_base(base_behind)

        return True

    def merge_base(self, base_behind):
        status = f"{pluralize(base_behind, 'base commit')} to merge"
        message = self.ask(status, "Merge, commit & push?") and self.ask_message(status, BASE_MERGE_MESSAGE)

        if not message:
            self.report(f"{pluralize(base_behind, 'base commit')} not merged", is_warning=True)

            return

        self.show_progress("merging…")

        if not git_repo.merge_base(self.repo, message):
            self.report("base merge failed, merge by hand", is_warning=True)

            return

        self.report(f"merged {pluralize(base_behind, 'base commit')}")
        self.is_updated = True
        self.is_push_confirmed = True

    def push(self):
        ahead = git_repo.count_commits(self.repo, f"{git_repo.UPSTREAM_BRANCH}..HEAD")

        if not ahead:
            return

        status = f"{pluralize(ahead, 'local commit')} not pushed"

        if not self.is_push_confirmed and not self.ask(status, "Push?"):
            self.report(status, is_warning=True)

            return

        self.show_progress("pushing…")

        if git_repo.push(self.repo):
            self.report(f"pushed {pluralize(ahead, 'commit')}")
        else:
            self.report(f"push failed, {pluralize(ahead, 'commit')} not pushed", is_warning=True)

    def run_install_script(self):
        install_script = self.repo / "install.ps1"

        if not install_script.is_file():
            return

        self.show_progress("running install.ps1…")
        install = git_repo.run_command(build_install_command(install_script), self.repo)

        if install.returncode != 0:
            self.report("install.ps1 failed", is_warning=True)
        elif INSTALL_WARNINGS_MARKER in install.stdout:
            self.report("install.ps1 reported warnings", is_warning=True)


def sync_launcher_repo():
    """Returns the launcher line (None when the launcher is not a git repo) and whether new commits were pulled."""
    if not git_repo.is_repo(LAUNCHER_REPO):
        return None, False

    sync = RepoSync(LAUNCHER_REPO, LAUNCHER_LABEL, [])
    sync.run()

    return sync.header_line, sync.is_updated


def sync_skills_repo(previous_lines):
    """Returns the skills line, or None when no shared skills repo is configured."""
    skills_repo = load_skills_repo()

    if skills_repo is None:
        return None

    if not git_repo.is_repo(skills_repo):
        return HeaderLine(SKILLS_LABEL, "configured repo not found", YELLOW)

    sync = RepoSync(skills_repo, SKILLS_LABEL, previous_lines)
    sync.run(SKILLS_COMMIT_MESSAGE, with_base=True, with_install=True)

    return sync.header_line
