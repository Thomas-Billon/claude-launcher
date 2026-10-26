"""
Folder menu: picks the folder where Claude Code is launched, or the default folder of an account.

Subfolders of a directory are listed by name (Up/Down to highlight, Left/Right to
move to the parent/child folder). Typed characters filter the list by folder name,
Backspace erases them and Esc clears the filter. A last entry creates a new folder
in the current directory.

To launch Claude Code, the favorite folders of the account (see launcher_state.py)
are listed on top, Ctrl+F toggles the highlighted folder as a favorite, and Tab
cycles the session mode: a new conversation, the last one continued, or one picked
in Claude Code to resume.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from launcher import launcher_state
from launcher.accounts import account_header_line
from launcher.keyboard import Key, is_typed_character, read_key
from launcher.prompts import ask_folder_name
from launcher.terminal_ui import (
    BACK,
    CYAN,
    DARK_GRAY,
    GREEN,
    MIN_LIST_ROWS,
    QUIT,
    RED,
    SEPARATOR,
    HeaderLine,
    ListSelection,
    Message,
    SectionTitle,
    colorize,
    render_screen,
    truncate,
)

FOLDER_HELP_TEXT = "  Up/Down: Highlight   Left/Right: Navigate   Type: Filter   Ctrl+F: Favorite   Tab: Session   Enter: Launch   Esc: Back   Ctrl+C: Quit"
DEFAULT_FOLDER_HELP_TEXT = "  Up/Down: Highlight   Left/Right: Navigate   Type: Filter   Enter: Set as default   Esc: Back   Ctrl+C: Quit"

ACCESS_DENIED_MESSAGE = Message("Access denied to this folder.", RED)
FOLDER_NOT_FOUND_MESSAGE = Message("Folder not found.", RED)
MISSING_LABEL = "(missing)"
INVALID_NAME_CHARACTERS = '<>:"/\\|?*'


@dataclass(frozen=True)
class FolderEntry:
    path: Path
    label: str
    is_missing: bool = False


@dataclass(frozen=True)
class SessionMode:
    label: str
    claude_arguments: tuple


NEW_FOLDER = FolderEntry(None, "+ New folder")
FAVORITES_TITLE = SectionTitle("★ Favorites")
SUBFOLDERS_TITLE = SectionTitle("Subfolders")

SESSION_MODES = (
    SessionMode("new conversation", ()),
    SessionMode("continue the last conversation", ("--continue",)),
    SessionMode("resume a conversation, picked in Claude Code", ("--resume",)),
)
NEW_SESSION = SESSION_MODES[0]
CONTINUE_SESSION = SESSION_MODES[1]


def session_header_line(session, color):
    return HeaderLine("Session", session.label, color)


def format_folder_label(folder):
    # INFO: The name comes first so that truncating a long label only cuts the parent path
    return f"{folder.name}  ({folder.parent})"


def get_start_dir(account):
    default_dir = launcher_state.load_default_dir(account)

    return default_dir if default_dir is not None and default_dir.is_dir() else Path.home()


def get_subfolder_names(directory):
    """Returns the subfolder names sorted by name, or None when the folder cannot be read."""
    try:
        with os.scandir(directory) as entries:
            names = [entry.name for entry in entries if entry.is_dir()]
    except OSError:
        return None

    return sorted(names, key=str.casefold)


def is_valid_folder_name(name):
    # INFO: Windows silently drops a trailing dot, the created folder would not have the typed name
    return not name.endswith(".") and not any(character in INVALID_NAME_CHARACTERS for character in name)


class FolderMenu:
    """State of the menu between two keys. Each key handler returns the outcome of the menu, or None to go on."""

    def __init__(self, initial_dir, header_lines, account, is_launch, help_text, message=None, selected_path=None, session=NEW_SESSION):
        self.header_lines = header_lines
        self.account = account
        self.is_launch = is_launch
        self.help_text = help_text
        # INFO: Shown until the menu closes, unlike the notice which only lasts until the next key
        self.message = message
        self.notice = None
        self.favorite_folders = launcher_state.load_favorites(account) if is_launch else []
        self.session_index = SESSION_MODES.index(session)
        self.filter_text = ""
        self.current_dir = initial_dir
        self.subfolder_names = []
        self.selection = None
        self.has_subfolders = False

        if not self.open(initial_dir, selected_path):
            self.rebuild()

    @property
    def session(self):
        return SESSION_MODES[self.session_index]

    @property
    def screen_lines(self):
        directory = f"{self.current_dir}   [filter: {self.filter_text}]" if self.filter_text else self.current_dir
        lines = [*self.header_lines, account_header_line(self.account), HeaderLine("Directory", directory, DARK_GRAY)]

        if self.is_launch:
            lines.append(session_header_line(self.session, DARK_GRAY if self.session is NEW_SESSION else CYAN))

        return lines

    def open(self, directory, selected_path=None, highlights_subfolders=False):
        """Lists the subfolders of the directory, returns False when it cannot be read."""
        subfolder_names = get_subfolder_names(directory)

        if subfolder_names is None:
            self.notice = ACCESS_DENIED_MESSAGE

            return False

        self.current_dir = directory
        self.subfolder_names = subfolder_names
        self.filter_text = ""
        self.rebuild(selected_path, highlights_subfolders)

        return True

    def rebuild(self, selected_path=None, highlights_subfolders=False):
        def matches_filter(name):
            return self.filter_text.casefold() in name.casefold()

        favorites = [
            FolderEntry(folder, format_folder_label(folder), not folder.is_dir())
            for folder in self.favorite_folders
            if matches_filter(folder.name)
        ]
        subfolders = [FolderEntry(self.current_dir / name, name) for name in self.subfolder_names if matches_filter(name)]
        favorites_section = [FAVORITES_TITLE, *favorites, SEPARATOR] if favorites else []
        items = [*favorites_section, SUBFOLDERS_TITLE, *subfolders, NEW_FOLDER]
        matching_indexes = [
            index
            for index, item in enumerate(items)
            if selected_path is not None and isinstance(item, FolderEntry) and item.path == selected_path
        ]

        default_index = items.index(SUBFOLDERS_TITLE) + 1 if highlights_subfolders else 0

        self.has_subfolders = bool(subfolders)
        # INFO: A folder both favorite and in the current directory is highlighted among the subfolders, listed last
        self.selection = ListSelection(
            items,
            lambda entry: entry.label,
            matching_indexes[-1] if matching_indexes else default_index,
            lambda entry: MISSING_LABEL if entry.is_missing else None,
        )

    def run(self):
        """Returns the selected folder, BACK on Esc or QUIT on Ctrl+C."""
        while True:
            self.render()
            key = read_key()
            self.notice = None

            if key == Key.CTRL_C:
                return QUIT

            if self.selection.handle_key(key):
                continue

            outcome = self.handle_key(key)

            if outcome is not None:
                return outcome

    def render(self):
        def render_body(available_rows, max_length):
            if self.has_subfolders:
                return self.selection.render(available_rows, max_length)

            text = f'  No subfolders match "{self.filter_text}".' if self.filter_text else "  No subfolders here."
            no_subfolders = colorize(truncate(text, max_length), RED)

            return self.selection.render(max(available_rows - 1, MIN_LIST_ROWS), max_length) + [no_subfolders]

        render_screen(self.screen_lines, render_body, self.help_text, self.notice or self.message)

    def handle_key(self, key):
        selected = self.selection.selected

        if key == Key.LEFT and self.current_dir.parent != self.current_dir:
            # INFO: The folder just left stays highlighted in its parent
            self.open(self.current_dir.parent, self.current_dir)
        elif key == Key.RIGHT and selected is not NEW_FOLDER:
            self.open(selected.path, highlights_subfolders=True)
        elif key == Key.ENTER and selected is NEW_FOLDER:
            self.create_folder()
        elif key == Key.ENTER and selected.is_missing:
            self.notice = FOLDER_NOT_FOUND_MESSAGE
        elif key == Key.ENTER:
            return selected.path
        elif key == Key.CTRL_F and self.is_launch and selected is not NEW_FOLDER:
            self.toggle_favorite(selected.path)
        elif key == Key.TAB and self.is_launch:
            self.session_index = (self.session_index + 1) % len(SESSION_MODES)
        elif key == Key.BACKSPACE and self.filter_text:
            self.set_filter(self.filter_text[:-1])
        elif key == Key.ESC and self.filter_text:
            self.set_filter("")
        elif key == Key.ESC:
            return BACK
        elif is_typed_character(key):
            self.set_filter(self.filter_text + key)

        return None

    def toggle_favorite(self, folder):
        favorite_indexes = self.get_favorite_indexes()
        was_favorite_highlighted = self.selection.selected_index in favorite_indexes
        favorite_position = favorite_indexes.index(self.selection.selected_index) if was_favorite_highlighted else None

        is_favorite = launcher_state.toggle_favorite(self.account, folder)
        self.favorite_folders = launcher_state.load_favorites(self.account)
        self.rebuild(folder)
        self.notice = Message(f"Added {folder} to favorites." if is_favorite else f"Removed {folder} from favorites.", GREEN)

        if was_favorite_highlighted and not is_favorite:
            self.highlight_after_unfavorite(favorite_position)

    def highlight_after_unfavorite(self, favorite_position):
        """Highlights the favorite that took the place of the removed one, else the previous one, else the first subfolder entry."""
        favorite_indexes = self.get_favorite_indexes()

        if favorite_indexes:
            self.selection.selected_index = favorite_indexes[min(favorite_position, len(favorite_indexes) - 1)]
        else:
            self.selection.selected_index = self.selection.items.index(SUBFOLDERS_TITLE) + 1

    def get_favorite_indexes(self):
        """Returns the indexes of the favorite entries, listed before the subfolders title."""
        items = self.selection.items
        subfolders_title_index = items.index(SUBFOLDERS_TITLE)

        return [index for index, item in enumerate(items[:subfolders_title_index]) if isinstance(item, FolderEntry)]

    def set_filter(self, filter_text):
        self.filter_text = filter_text
        self.rebuild()

    def create_folder(self):
        name = ask_folder_name(self.screen_lines, self.filter_text)

        if name is None:
            return

        if not is_valid_folder_name(name):
            self.notice = Message(f'"{name}" is not a valid folder name.', RED)

            return

        folder = self.current_dir / name

        try:
            folder.mkdir()
        except FileExistsError:
            self.notice = Message(f'"{name}" already exists.', RED)

            return
        except OSError:
            self.notice = Message(f'Could not create "{name}".', RED)

            return

        self.open(self.current_dir, folder)
        self.notice = Message(f'Folder "{name}" created.', GREEN)


def prompt_for_folder(initial_dir, header_lines, account, message=None):
    """Picks the default folder of an account. Returns the selected folder, BACK on Esc or QUIT on Ctrl+C."""
    return FolderMenu(initial_dir, header_lines, account, False, DEFAULT_FOLDER_HELP_TEXT, message).run()


def prompt_for_launch_folder(initial_dir, header_lines, account, selected_path=None, session=NEW_SESSION):
    """Returns the selected folder (or BACK on Esc, QUIT on Ctrl+C) and the chosen session mode."""
    menu = FolderMenu(initial_dir, header_lines, account, True, FOLDER_HELP_TEXT, selected_path=selected_path, session=session)

    return menu.run(), menu.session
