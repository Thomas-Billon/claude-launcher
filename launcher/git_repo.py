"""
Git commands run by the launcher on its own repo and on the shared skills repo.

A command that fails returns False (or None for a count) instead of raising:
the caller reports it on the header line and the launch goes on.
"""

import os
import subprocess

FETCH_TIMEOUT_SECONDS = 10
# INFO: Longer than a fetch, since pull, merge and push only run once the user has asked for them
SYNC_TIMEOUT_SECONDS = 60
UPSTREAM_BRANCH = "@{u}"
# INFO: Default branch of the upstream remote (the base repo of the skills repo), whatever its name
BASE_BRANCH = "upstream/HEAD"


def run_command(command, cwd, timeout=None):
    # INFO: GIT_TERMINAL_PROMPT=0 makes git fail instead of hanging on a credential prompt
    environment = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}

    return subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=timeout,
    )


def run_git(repo, *arguments, timeout=None):
    return run_command(["git", *arguments], repo, timeout)


def succeeds(repo, *arguments, timeout=None):
    return run_git(repo, *arguments, timeout=timeout).returncode == 0


def is_repo(repo):
    return (repo / ".git").exists()


def fetch(repo):
    return succeeds(repo, "fetch", "--quiet", timeout=FETCH_TIMEOUT_SECONDS)


def has_base(repo):
    return succeeds(repo, "remote", "get-url", "upstream")


def fetch_base(repo):
    if not succeeds(repo, "fetch", "upstream", "--quiet", timeout=FETCH_TIMEOUT_SECONDS):
        return False

    if succeeds(repo, "rev-parse", "--verify", "--quiet", BASE_BRANCH):
        return True

    # INFO: upstream/HEAD only exists once resolved, set-head asks the remote for its default branch
    return succeeds(repo, "remote", "set-head", "upstream", "--auto", timeout=FETCH_TIMEOUT_SECONDS)


def count_commits(repo, revision_range):
    result = run_git(repo, "rev-list", "--count", revision_range)

    return int(result.stdout.strip()) if result.returncode == 0 else None


def count_changed_files(repo):
    result = run_git(repo, "status", "--porcelain")

    return len(result.stdout.splitlines()) if result.returncode == 0 else 0


def commit_all(repo, message):
    return succeeds(repo, "add", "--all") and succeeds(repo, "commit", "--quiet", "--message", message)


def pull(repo):
    # INFO: Unpushed local commits are replayed on top of the remote ones (merges kept) instead of adding a merge commit,
    # and uncommitted changes are set aside meanwhile
    if succeeds(repo, "pull", "--rebase=merges", "--autostash", "--quiet", timeout=SYNC_TIMEOUT_SECONDS):
        return True

    run_git(repo, "rebase", "--abort")

    return False


def merge_base(repo, message):
    # INFO: A repo created from a GitHub template shares no history with its base until its first merge
    arguments = ["merge", BASE_BRANCH, "--allow-unrelated-histories", "--autostash", "--quiet", "--message", message]

    if succeeds(repo, *arguments, timeout=SYNC_TIMEOUT_SECONDS):
        return True

    run_git(repo, "merge", "--abort")

    return False


def push(repo):
    return succeeds(repo, "push", "--quiet", timeout=SYNC_TIMEOUT_SECONDS)
