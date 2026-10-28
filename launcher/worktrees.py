"""
Git worktrees where Claude Code works beside the main folder of a repo, without touching it.

Every worktree of a repo lives in ~/.claude-worktrees/<id>/<name>/, the id being generated
once per repo (see worktrees_state.py), and works on its own temp/<name> branch created from
a branch of the repo, which becomes its upstream: the origin of a worktree is read from git, as
the worktrees themselves. Finishing or deleting a worktree is done outside the launcher, which
never pushes anything.
"""

import secrets
from dataclasses import dataclass
from pathlib import Path

from launcher import git_repo, worktrees_state
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
    repo: Path
    origin_branch: str | None = None
    is_merged: bool = False

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


def remote_branch_exists(repo, branch):
    return succeeds(repo, "rev-parse", "--verify", "--quiet", f"{REMOTE_BRANCHES_PREFIX}{branch}")


def strip_remote(branch):
    """Returns the branch without its remote name (origin/stage becomes stage)."""
    return branch.split("/", 1)[-1]


def is_valid_branch_name(repo, branch):
    return succeeds(repo, "check-ref-format", "--branch", branch)


def list_branches(repo):
    """Returns the local branches, then the remote ones (e.g. origin/stage) that have no local branch, temp/* excluded."""
    local_branches = [branch for branch in list_refs(repo, LOCAL_BRANCHES_PREFIX) if not branch.startswith(TEMP_BRANCH_PREFIX)]
    # INFO: origin/HEAD only points to the default branch of the remote
    remote_branches = [
        branch
        for branch in list_refs(repo, REMOTE_BRANCHES_PREFIX)
        if not branch.endswith("/HEAD")
        and not strip_remote(branch).startswith(TEMP_BRANCH_PREFIX)
        and strip_remote(branch) not in local_branches
    ]

    return sorted(local_branches, key=str.casefold) + sorted(remote_branches, key=str.casefold)


def find_repo_dir(repo):
    """Returns the folder of the worktrees of the repo, or None before its first worktree."""
    repo_id = worktrees_state.load_repo_id(repo)

    return WORKTREES_DIR / repo_id if repo_id is not None else None


def generate_repo_id():
    while True:
        repo_id = secrets.token_hex(4)

        if not (WORKTREES_DIR / repo_id).exists():
            return repo_id


def validate_worktree_name(repo, name):
    """Returns the error to show, or None when a worktree can be created with this name."""
    if " " in name or not is_valid_folder_name(name) or not is_valid_branch_name(repo, f"{TEMP_BRANCH_PREFIX}{name}"):
        return f'"{name}" is not a valid worktree name.'

    repo_dir = find_repo_dir(repo)

    if branch_exists(repo, f"{TEMP_BRANCH_PREFIX}{name}") or (repo_dir is not None and (repo_dir / name).exists()):
        return f'"{name}" already exists.'

    return None


def create_worktree(repo, name, origin_branch):
    """Returns the created worktree, or None when git fails."""
    if not branch_exists(repo, origin_branch) and remote_branch_exists(repo, origin_branch):
        # INFO: The worktree starts from a local branch, which follows the remote one
        local_branch = strip_remote(origin_branch)

        if not branch_exists(repo, local_branch) and not succeeds(repo, "branch", "--quiet", "--track", local_branch, origin_branch):
            return None

        origin_branch = local_branch

    repo_id = worktrees_state.load_repo_id(repo)
    is_new_repo = repo_id is None

    if is_new_repo:
        repo_id = generate_repo_id()

    worktree = Worktree(name, WORKTREES_DIR / repo_id / name, repo, origin_branch)

    if not succeeds(repo, "worktree", "add", "--quiet", "--track", "-b", worktree.branch, str(worktree.path), origin_branch):
        return None

    if is_new_repo:
        worktrees_state.save_repo_id(repo, repo_id)

    return worktree


def list_registered_worktrees(repo):
    """Returns the folder and local branch (None when detached) of each worktree git knows, the main folder included."""
    result = run_git(repo, "worktree", "list", "--porcelain")
    registered = []

    for line in result.stdout.splitlines() if result.returncode == 0 else []:
        if line.startswith("worktree "):
            registered.append((Path(line.removeprefix("worktree ")).resolve(), None))
        elif line.startswith("branch " + LOCAL_BRANCHES_PREFIX) and registered:
            registered[-1] = (registered[-1][0], line.removeprefix("branch " + LOCAL_BRANCHES_PREFIX))

    return registered


def list_registered_paths(repo):
    """Returns the folders of the worktrees git knows for the repo, the main folder included."""
    return {path for path, _ in list_registered_worktrees(repo)}


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


def is_existing_branch(repo, branch):
    """Returns whether the branch exists, as a local branch or as a remote one (e.g. origin/stage)."""
    return branch_exists(repo, branch) or remote_branch_exists(repo, branch)


def start_fetch_prune(repo):
    """Starts git fetch --prune in the background, so that the next listing sees the branches deleted on the remote.
    Returns its process."""
    return git_repo.start_git(repo, "fetch", "--prune", "--quiet")


def read_origin(repo, branch):
    """Returns the local branch the branch tracks, or None without upstream."""
    result = run_git(repo, "rev-parse", "--abbrev-ref", f"{branch}@{{upstream}}")

    return result.stdout.strip() if result.returncode == 0 else None


def is_gone(repo, branch):
    """Returns whether the branch tracks a remote branch that no longer exists."""
    result = run_git(repo, "for-each-ref", "--format=%(upstream:track)", f"{LOCAL_BRANCHES_PREFIX}{branch}")

    return result.returncode == 0 and result.stdout.strip() == "[gone]"


def load_worktrees(repo):
    """Returns the worktrees of the repo sorted by name, after forgetting those git no longer knows.
    A worktree is merged when the remote branch of its origin was deleted, as of the last fetch."""
    succeeds(repo, "worktree", "prune")
    registered = list_registered_worktrees(repo)
    repo_dir = find_repo_dir(repo)
    remove_orphan_folders(repo_dir, {path for path, _ in registered})
    worktrees = []

    for path, branch in registered:
        if repo_dir is None or path.parent != repo_dir.resolve() or branch != f"{TEMP_BRANCH_PREFIX}{path.name}":
            continue

        origin_branch = read_origin(repo, branch)
        is_merged = origin_branch is not None and is_gone(repo, origin_branch)
        worktrees.append(Worktree(path.name, repo_dir / path.name, repo, origin_branch, is_merged))

    return sorted(worktrees, key=lambda worktree: worktree.name.casefold())
