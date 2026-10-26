"""
Throwaway git repos for the tests, built with the git CLI in a temporary folder.
"""

import subprocess


def run(repo, *arguments):
    subprocess.run(["git", *arguments], cwd=repo, check=True, capture_output=True)


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


def read(repo, *arguments):
    """Returns the trimmed output of a git command, or None when it fails."""
    result = subprocess.run(["git", *arguments], cwd=repo, capture_output=True, text=True)

    return result.stdout.strip() if result.returncode == 0 else None


def read_upstream(repo, branch):
    return read(repo, "rev-parse", "--abbrev-ref", f"{branch}@{{upstream}}")


def clone(source, destination):
    run(source.parent, "clone", "--quiet", str(source), str(destination))
    configure_identity(destination)

    return destination
