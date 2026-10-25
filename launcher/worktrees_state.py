"""
State the launcher keeps per repo in ~/.claude-worktrees/worktrees_state.json:
the id of its worktrees folder, its base branches, and the source branch of each of its worktrees.

Repos are keyed by the path of their root folder (see worktrees.py).
"""

from launcher.json_store import load_json, save_json
from launcher.paths import WORKTREES_STATE_FILE


def load_state():
    return load_json(WORKTREES_STATE_FILE)


def save_state(state):
    save_json(WORKTREES_STATE_FILE, state)


def get_repo_state(state, repo):
    return state.setdefault("repos", {}).setdefault(str(repo), {})


def load_repo_id(repo):
    return get_repo_state(load_state(), repo).get("id")


def save_repo_id(repo, repo_id):
    state = load_state()
    get_repo_state(state, repo)["id"] = repo_id
    save_state(state)


def load_base_branches(repo):
    return get_repo_state(load_state(), repo).get("base_branches", [])


def save_base_branches(repo, branches):
    state = load_state()
    get_repo_state(state, repo)["base_branches"] = list(branches)
    save_state(state)


def load_worktree_sources(repo):
    """Returns the source branch of each worktree of the repo, keyed by worktree name."""
    worktrees = get_repo_state(load_state(), repo).get("worktrees", {})

    return {name: worktree["source_branch"] for name, worktree in worktrees.items()}


def save_worktree(repo, name, source_branch):
    state = load_state()
    get_repo_state(state, repo).setdefault("worktrees", {})[name] = {"source_branch": source_branch}
    save_state(state)


def forget_worktree(repo, name):
    state = load_state()
    get_repo_state(state, repo).get("worktrees", {}).pop(name, None)
    save_state(state)
