"""
Conversation history of Claude Code, kept per account in <account dir>/projects/<encoded folder path>/.
"""

import json
import os
import re

from launcher.junctions import create_junction


def encode_path(path):
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def get_history_dir(config_dir, folder):
    return config_dir / "projects" / encode_path(folder)


def link_worktree_history(config_dir, worktree_path, repo):
    """Returns False when the junction could not be created."""
    link = get_history_dir(config_dir, worktree_path)

    if os.path.lexists(link):
        return True

    target = get_history_dir(config_dir, repo)
    target.mkdir(parents=True, exist_ok=True)

    return create_junction(link, target)


def normalize_folder(path):
    return os.path.normcase(os.path.normpath(path))


def read_conversation_folder(conversation):
    """Returns the folder a conversation ran in, from the first line holding a cwd, or None."""
    try:
        with conversation.open(encoding="utf-8") as lines:
            for line in lines:
                try:
                    cwd = json.loads(line).get("cwd")
                except (json.JSONDecodeError, AttributeError):
                    continue

                if cwd:
                    return normalize_folder(cwd)
    except OSError:
        pass

    return None


def find_last_session(config_dir, repo, folder):
    """Returns the session id of the most recent conversation of the repo history run in the folder, or None."""
    history_dir = get_history_dir(config_dir, repo)

    if not history_dir.is_dir():
        return None

    wanted_folder = normalize_folder(folder)
    conversations = sorted(history_dir.glob("*.jsonl"), key=lambda conversation: conversation.stat().st_mtime, reverse=True)

    for conversation in conversations:
        if read_conversation_folder(conversation) == wanted_folder:
            return conversation.stem

    return None


def remove_stale_links(config_dir, repo, registered_paths):
    """Removes the junctions to the repo history whose folder is not a registered path, keeping the history itself."""
    projects_dir = config_dir / "projects"

    if not projects_dir.is_dir():
        return

    repo_history = os.path.realpath(get_history_dir(config_dir, repo))
    registered_names = {encode_path(path) for path in registered_paths}

    for entry in projects_dir.iterdir():
        if os.path.isjunction(entry) and entry.name not in registered_names and os.path.realpath(entry) == repo_history:
            # INFO: rmdir removes the link only, never the history it points to
            os.rmdir(entry)
