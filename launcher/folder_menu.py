"""
Folder menu: picks the folder where Claude Code is launched, or the default folder of an account.

Subfolders of a directory are listed (Up/Down to highlight, Left/Right to move to
the parent/child folder). The last launch time per folder is remembered per
account (see launcher_state.py): the most recently opened folders can be listed
on top, and subfolders are sorted most-recently-used first.
"""

from dataclasses import dataclass
from pathlib import Path

from launcher import launcher_state
from launcher.accounts import account_header_line
from launcher.keyboard import MenuKey, read_menu_key
from launcher.terminal_ui import (
    BACK,
    DARK_GRAY,
    MIN_LIST_ROWS,
    QUIT,
    RED,
    SEPARATOR,
    HeaderLine,
    ListSelection,
    colorize,
    render_screen,
    truncate,
)

FOLDER_HELP_TEXT = "  Up/Down: Highlight   Left/Right: Navigate   Enter: Select   Esc: Back   Ctrl+C: Quit"
DEFAULT_FOLDER_HELP_TEXT = "  Up/Down: Highlight   Left/Right: Navigate   Enter: Set as default   Esc: Back   Ctrl+C: Quit"

RECENT_FOLDER_COUNT = 5


@dataclass(frozen=True)
class FolderEntry:
    path: Path
    label: str


def format_folder_label(folder):
    # INFO: The name comes first so that truncating a long label only cuts the parent path
    return f"{folder.name}  ({folder.parent})"


def get_start_dir(account):
    default_dir = launcher_state.load_default_dir(account)

    return default_dir if default_dir is not None and default_dir.is_dir() else Path.home()


def get_subfolder_names(current_dir):
    if not current_dir.is_dir():
        return []

    return [entry.name for entry in current_dir.iterdir() if entry.is_dir()]


def sort_folders_by_history(folder_names, history, current_dir):
    def history_key(name):
        return str(current_dir / name)

    launched = sorted(
        (name for name in folder_names if history_key(name) in history),
        key=lambda name: history[history_key(name)],
        reverse=True,
    )
    never_launched = sorted(name for name in folder_names if history_key(name) not in history)

    return launched + never_launched


def get_recent_folders(history):
    launched = sorted(history, key=history.get, reverse=True)

    return [Path(folder) for folder in launched if Path(folder).is_dir()][:RECENT_FOLDER_COUNT]


def build_folder_entries(directory, history, show_recent):
    subfolders = [
        FolderEntry(directory / name, name)
        for name in sort_folders_by_history(get_subfolder_names(directory), history, directory)
    ]

    if not show_recent:
        return subfolders

    recent = [FolderEntry(folder, format_folder_label(folder)) for folder in get_recent_folders(history)]

    return recent + [SEPARATOR] + subfolders if recent else subfolders


def render_folder_menu(current_dir, selection, has_subfolders, header_lines, account, help_text, message):
    def render_body(available_rows, max_length):
        if has_subfolders:
            return selection.render(available_rows, max_length)

        no_subfolders = colorize(truncate("  No subfolders here.", max_length), RED)

        return selection.render(max(available_rows - 1, MIN_LIST_ROWS), max_length) + [no_subfolders]

    lines = [*header_lines, account_header_line(account), HeaderLine("Directory", current_dir, DARK_GRAY)]
    render_screen(lines, render_body, help_text, message)


def prompt_for_folder(initial_dir, header_lines, account, help_text=FOLDER_HELP_TEXT, message=None, show_recent=False):
    """Returns the selected folder, BACK on Esc or QUIT on Ctrl+C."""
    history = launcher_state.load_history(account)

    def build_folder_selection(directory):
        return ListSelection(build_folder_entries(directory, history, show_recent), lambda entry: entry.label)

    current_dir = initial_dir
    selection = build_folder_selection(current_dir)

    while True:
        has_subfolders = any(entry is not SEPARATOR and entry.path.parent == current_dir for entry in selection.items)
        render_folder_menu(current_dir, selection, has_subfolders, header_lines, account, help_text, message)
        key = read_menu_key()

        if selection.handle_key(key):
            continue

        if key == MenuKey.LEFT and current_dir.parent != current_dir:
            current_dir = current_dir.parent
            selection = build_folder_selection(current_dir)
        elif key == MenuKey.RIGHT and selection.selected is not None:
            current_dir = selection.selected.path
            selection = build_folder_selection(current_dir)
        elif key == MenuKey.ENTER and selection.selected is not None:
            return selection.selected.path
        elif key == MenuKey.ESC:
            return BACK
        elif key == MenuKey.CTRL_C:
            return QUIT
