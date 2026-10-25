"""
Git worktrees where Claude Code works beside the main folder of a repo, without touching it.

Every worktree of a repo lives in ~/.claude-worktrees/<id>/<name>/, the id being generated
once per repo (see worktrees_state.py), and works on its own temp/<name> branch created from
a branch of the repo, usually one of its base branches. Finishing or deleting a worktree is
done outside the launcher, which never pushes anything.
"""

import secrets
from dataclasses import dataclass
from pathlib import Path

from launcher import worktrees_state
from launcher.folder_menu import is_valid_folder_name
from launcher.git_repo import run_git, succeeds
from launcher.paths import WORKTREES_DIR

TEMP_BRANCH_PREFIX = "temp/"
LOCAL_BRANCHES_PREFIX = "refs/heads/"
REMOTE_BRANCHES_PREFIX = "refs/remotes/"


@dataclass(frozen=True)
class Worktree:
    name: str
    path: Path
    source_branch: str

    @property
    def branch(self):
        return f"{TEMP_BRANCH_PREFIX}{self.name}"


def find_repo_root(folder):
    """Returns the root folder of the repo holding the folder, or None outside a repo."""
    result = run_git(folder, "rev-parse", "--show-toplevel")

    return Path(result.stdout.strip()).resolve() if result.returncode == 0 else None


def list_refs(repo, prefix):
    result = run_git(repo, "for-each-ref", "--format=%(refname)", prefix)

    return [line.removeprefix(prefix) for line in result.stdout.splitlines()] if result.returncode == 0 else []


def branch_exists(repo, branch):
    return succeeds(repo, "rev-parse", "--verify", "--quiet", f"{LOCAL_BRANCHES_PREFIX}{branch}")


def is_valid_branch_name(repo, branch):
    return succeeds(repo, "check-ref-format", "--branch", branch)


def list_branches(repo):
    """Returns the local branches, then the remote ones (e.g. origin/stage) that have no local branch."""
    local_branches = [branch for branch in list_refs(repo, LOCAL_BRANCHES_PREFIX) if not branch.startswith(TEMP_BRANCH_PREFIX)]
    # INFO: origin/HEAD only points to the default branch of the remote
    remote_branches = [
        branch
        for branch in list_refs(repo, REMOTE_BRANCHES_PREFIX)
        if not branch.endswith("/HEAD") and branch.split("/", 1)[-1] not in local_branches
    ]

    return sorted(local_branches, key=str.casefold) + sorted(remote_branches, key=str.casefold)


def find_repo_dir(repo):
    """Returns the folder of the worktrees of the repo, or None before its first worktree."""
    repo_id = worktrees_state.load_repo_id(repo)

    return WORKTREES_DIR / repo_id if repo_id is not None else None


def get_repo_dir(repo):
    repo_dir = find_repo_dir(repo)

    if repo_dir is not None:
        return repo_dir

    while True:
        repo_id = secrets.token_hex(4)

        if not (WORKTREES_DIR / repo_id).exists():
            break

    worktrees_state.save_repo_id(repo, repo_id)

    return WORKTREES_DIR / repo_id


def validate_worktree_name(repo, name):
    """Returns the error to show, or None when a worktree can be created with this name."""
    if " " in name or not is_valid_folder_name(name) or not is_valid_branch_name(repo, f"{TEMP_BRANCH_PREFIX}{name}"):
        return f'"{name}" is not a valid worktree name.'

    repo_dir = find_repo_dir(repo)

    if branch_exists(repo, f"{TEMP_BRANCH_PREFIX}{name}") or (repo_dir is not None and (repo_dir / name).exists()):
        return f'"{name}" already exists.'

    return None


def create_worktree(repo, name, source_branch):
    """Returns the created worktree, or None when git fails."""
    is_remote = not branch_exists(repo, source_branch) and succeeds(
        repo, "rev-parse", "--verify", "--quiet", f"{REMOTE_BRANCHES_PREFIX}{source_branch}"
    )

    if is_remote:
        # INFO: The worktree starts from a local branch, which follows the remote one. A base branch saved
        # while it was only on the remote keeps its remote name, its local branch is reused once created
        local_branch = source_branch.split("/", 1)[-1]

        if not branch_exists(repo, local_branch) and not succeeds(repo, "branch", "--quiet", "--track", local_branch, source_branch):
            return None

        source_branch = local_branch

    worktree = Worktree(name, get_repo_dir(repo) / name, source_branch)

    if not succeeds(repo, "worktree", "add", "--quiet", "-b", worktree.branch, str(worktree.path), source_branch):
        return None

    worktrees_state.save_worktree(repo, name, source_branch)

    return worktree


def list_registered_paths(repo):
    """Returns the folders of the worktrees git knows for the repo, the main folder included."""
    result = run_git(repo, "worktree", "list", "--porcelain")
    lines = result.stdout.splitlines() if result.returncode == 0 else []

    return {Path(line.removeprefix("worktree ")).resolve() for line in lines if line.startswith("worktree ")}


def remove_orphan_folders(repo_dir, registered_paths):
    """Deletes the empty folders of the worktrees folder of the repo that git no longer knows, such as those left by a
    worktree removed from a Claude Code session still running in it. A non-empty folder is never touched."""
    if repo_dir is None or not repo_dir.is_dir():
        return

    for folder in repo_dir.iterdir():
        if folder.is_dir() and folder.resolve() not in registered_paths and not any(folder.iterdir()):
            try:
                folder.rmdir()
            except OSError:
                # INFO: A process still running in the folder prevents its removal
                pass


def load_worktrees(repo):
    """Returns the worktrees of the repo sorted by name, after forgetting those git no longer knows."""
    succeeds(repo, "worktree", "prune")
    registered_paths = list_registered_paths(repo)
    repo_dir = find_repo_dir(repo)
    remove_orphan_folders(repo_dir, registered_paths)
    worktrees = []

    for name, source_branch in worktrees_state.load_worktree_sources(repo).items():
        worktree = Worktree(name, repo_dir / name, source_branch) if repo_dir is not None else None

        if worktree is not None and worktree.path.resolve() in registered_paths:
            worktrees.append(worktree)
        else:
            worktrees_state.forget_worktree(repo, name)

    return sorted(worktrees, key=lambda worktree: worktree.name.casefold())
