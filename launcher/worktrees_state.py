"""
State the launcher keeps per repo in ~/.claude-worktrees/worktrees_state.json:
the id of its worktrees folder and its favorite branches. The worktrees and their origin live in git.

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


def load_favorite_branches(repo):
    return get_repo_state(load_state(), repo).get("favorite_branches", [])


def toggle_favorite_branch(repo, branch):
    """Adds the branch to the favorites of the repo or removes it, returns True when it is now a favorite."""
    state = load_state()
    repo_state = get_repo_state(state, repo)
    favorites = repo_state.get("favorite_branches", [])
    remaining = [favorite for favorite in favorites if favorite != branch]
    is_favorite = len(remaining) == len(favorites)

    if is_favorite:
        remaining.append(branch)

    repo_state["favorite_branches"] = remaining
    save_state(state)

    return is_favorite
