"""
Throwaway git repos for the tests, built with the git CLI in a temporary folder.
"""

import subprocess


def run(repo, *arguments):
    subprocess.run(["git", *arguments], cwd=repo, check=True, capture_output=True)


def git_output(repo, *arguments):
    return subprocess.run(["git", *arguments], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


def branch_exists(repo, branch):
    return subprocess.run(["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"], cwd=repo, capture_output=True).returncode == 0


def configure_identity(repo):
    run(repo, "config", "user.name", "Tests")
    run(repo, "config", "user.email", "tests@example.com")


def make_repo(directory, branches=("dev",)):
    directory.mkdir(parents=True)
    run(directory, "init", "--quiet", "-b", "master")
    configure_identity(directory)
    commit_file(directory, "README.md", "readme")

    for branch in branches:
        run(directory, "branch", branch)

    return directory


def commit_file(repo, name, content):
    (repo / name).write_text(content)
    run(repo, "add", name)
    run(repo, "commit", "--quiet", "--message", f"Updated {name}")


def commit_on_branch(repo, branch, name, content):
    """Commits on a branch that is not checked out, through a throwaway worktree."""
    worktree = repo.parent / f"{repo.name}-commit-{branch.replace('/', '-')}"
    run(repo, "worktree", "add", "--quiet", str(worktree), branch)
    commit_file(worktree, name, content)
    run(repo, "worktree", "remove", str(worktree))
