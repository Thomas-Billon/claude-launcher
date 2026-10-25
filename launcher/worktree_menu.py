"""
Worktree menu: picks where Claude Code is launched in a git repo, its main folder or one of its worktrees (see worktrees.py).

The list holds a new worktree entry, the main folder entry, then the worktrees of the repo.
Right opens the options of the new worktree entry in a right column: editing the base
branches of the repo, or a worktree started from any branch of the repo, remote ones
included, without saving it as a base branch. Left/Esc closes them. Tab cycles the
session mode, as in the folder menu.

A new worktree is named, then started from one of the base branches of the repo, picked
in a list unless there is only one. The first time, the base branches are checked in the
list of all the branches of the repo.
"""

from launcher import worktrees, worktrees_state
from launcher.account_menu import OPTIONS_HELP_TEXT
from launcher.accounts import account_header_line
from launcher.folder_menu import NEW_SESSION, SESSION_MODES, session_header_line
from launcher.keyboard import Key, read_key
from launcher.prompts import ask_worktree_name
from launcher.terminal_ui import (
    BACK,
    COLUMN_SEPARATOR,
    CYAN,
    DARK_GRAY,
    GREEN,
    QUIT,
    RED,
    SEPARATOR,
    HeaderLine,
    ListSelection,
    Message,
    join_columns,
    render_screen,
)

WORKTREE_HELP_TEXT = "  Up/Down: Highlight   Right: Options   Tab: Session   Enter: Launch   Esc: Back   Ctrl+C: Quit"
BASE_BRANCHES_HELP_TEXT = "  Up/Down: Highlight   Space: Check   Enter: Save   Esc: Cancel   Ctrl+C: Quit"
BRANCH_PICKER_HELP_TEXT = "  Up/Down: Highlight   Enter: Select   Esc: Back   Ctrl+C: Quit"

BASE_BRANCHES_MESSAGE = Message("Choose the base branches of this folder.", CYAN)
BRANCH_PICKER_MESSAGE = Message("Source branch of the new worktree.", CYAN)

# INFO: Entries of the list besides the worktrees, NO_WORKTREE is also the outcome of the menu for the main folder
ADD_WORKTREE = object()
NO_WORKTREE = object()

EDIT_BASE_BRANCHES = "Edit base branches"
WORKTREE_FROM_BRANCH = "Worktree from branch"
ADD_WORKTREE_OPTIONS = [EDIT_BASE_BRANCHES, WORKTREE_FROM_BRANCH]


def worktree_header_line(worktree, color):
    return HeaderLine("Worktree", f"{worktree.name}  (from {worktree.source_branch})", color)


def entry_label(entry):
    if entry is ADD_WORKTREE:
        return "+ Worktree"

    return "No worktree" if entry is NO_WORKTREE else entry.name


def entry_secondary_label(entry):
    return f"from {entry.source_branch}" if isinstance(entry, worktrees.Worktree) else None


def prompt_for_base_branches(repo, header_lines):
    """Checks and saves the base branches of the repo. Returns them, None on Esc or QUIT on Ctrl+C."""
    branches = worktrees.list_branches(repo)
    # INFO: A saved branch deleted since is dropped
    checked = set(worktrees_state.load_base_branches(repo)) & set(branches)
    selection = ListSelection(branches, lambda branch: f"[{'x' if branch in checked else ' '}] {branch}")
    notice = None

    while True:
        render_screen(header_lines, selection.render, BASE_BRANCHES_HELP_TEXT, notice or BASE_BRANCHES_MESSAGE)
        key = read_key()
        notice = None

        if key == Key.CTRL_C:
            return QUIT

        if selection.handle_key(key):
            continue

        if key == Key.SPACE and selection.selected is not None:
            checked ^= {selection.selected}
        elif key == Key.ENTER and not checked:
            notice = Message("Choose at least one base branch.", RED)
        elif key == Key.ENTER:
            base_branches = [branch for branch in branches if branch in checked]
            worktrees_state.save_base_branches(repo, base_branches)

            return base_branches
        elif key == Key.ESC:
            return None


def prompt_for_branch(branches, header_lines):
    """Returns the picked branch, BACK on Esc or QUIT on Ctrl+C."""
    selection = ListSelection(branches)

    while True:
        render_screen(header_lines, selection.render, BRANCH_PICKER_HELP_TEXT, BRANCH_PICKER_MESSAGE)
        key = read_key()

        if key == Key.CTRL_C:
            return QUIT

        if selection.handle_key(key):
            continue

        if key == Key.ENTER:
            return selection.selected

        if key == Key.ESC:
            return BACK


class WorktreeMenu:
    """State of the menu between two keys. Each key handler returns the outcome of the menu, or None to go on."""

    def __init__(self, repo, folder, header_lines, account, session):
        self.repo = repo
        self.folder = folder
        self.header_lines = header_lines
        self.account = account
        self.session_index = SESSION_MODES.index(session)
        self.selection = None
        # INFO: Right column of the new worktree options, None while closed
        self.side_selection = None
        self.message = None
        self.reload()

    @property
    def session(self):
        return SESSION_MODES[self.session_index]

    @property
    def entry(self):
        return self.selection.selected

    @property
    def screen_lines(self):
        return [
            *self.header_lines,
            account_header_line(self.account),
            HeaderLine("Directory", self.folder, GREEN),
            session_header_line(self.session, DARK_GRAY if self.session is NEW_SESSION else CYAN),
        ]

    def reload(self, selected_entry=NO_WORKTREE):
        worktree_list = worktrees.load_worktrees(self.repo)
        items = [ADD_WORKTREE, NO_WORKTREE] + ([SEPARATOR] + worktree_list if worktree_list else [])
        selected_index = items.index(selected_entry) if selected_entry in items else items.index(NO_WORKTREE)
        # INFO: No worktree is highlighted first, so that a double Enter launches in the main folder as before worktrees
        self.selection = ListSelection(items, entry_label, selected_index, entry_secondary_label)

    def run(self):
        """Returns the chosen worktree, NO_WORKTREE for the main folder, BACK on Esc or QUIT on Ctrl+C."""
        while True:
            self.render()
            key = read_key()
            self.message = None

            if key == Key.CTRL_C:
                return QUIT

            outcome = self.handle_list_key(key) if self.side_selection is None else self.handle_options_key(key)

            if outcome is not None:
                return outcome

    def render(self):
        def render_body(available_rows, max_length):
            if self.side_selection is None:
                return self.selection.render(available_rows, max_length)

            # INFO: A secondary label is rendered after its label, 2 spaces apart
            longest_label = max(
                len(entry_label(item)) + len(entry_secondary_label(item) or "") + 2
                for item in self.selection.items
                if item is not SEPARATOR
            )
            left_width = min(longest_label + 4, max_length // 2)
            right_width = max_length - left_width - len(COLUMN_SEPARATOR)

            return join_columns(
                self.selection.render(available_rows, left_width, has_cursor=False),
                self.side_selection.render(available_rows, right_width),
                left_width,
            )

        help_text = WORKTREE_HELP_TEXT if self.side_selection is None else OPTIONS_HELP_TEXT
        render_screen(self.screen_lines, render_body, help_text, self.message)

    def handle_list_key(self, key):
        if self.selection.handle_key(key):
            return None

        entry = self.entry

        if key == Key.ESC:
            return BACK

        if key == Key.TAB:
            self.session_index = (self.session_index + 1) % len(SESSION_MODES)
        elif key == Key.RIGHT and entry is ADD_WORKTREE:
            self.side_selection = ListSelection(ADD_WORKTREE_OPTIONS)
        elif key == Key.ENTER and entry is ADD_WORKTREE:
            return self.add_worktree()
        elif key == Key.ENTER:
            return entry

        return None

    def ask_valid_worktree_name(self):
        """Returns the name of the new worktree, None on Esc or on an invalid name (the menu shows why)."""
        name = ask_worktree_name(self.screen_lines)

        if name is None:
            return None

        error = worktrees.validate_worktree_name(self.repo, name)

        if error is not None:
            self.message = Message(error, RED)

            return None

        return name

    def start_worktree(self, name, source_branch):
        """Creates the worktree from the picked source branch. Returns it, QUIT on Ctrl+C, or None to stay in the menu."""
        if source_branch is QUIT:
            return QUIT

        if source_branch is BACK:
            return None

        worktree = worktrees.create_worktree(self.repo, name, source_branch)

        if worktree is None:
            self.message = Message("Could not create the worktree.", RED)

        return worktree

    def add_worktree(self):
        """Returns the created worktree, QUIT on Ctrl+C, or None to stay in the menu."""
        name = self.ask_valid_worktree_name()

        if name is None:
            return None

        base_branches = worktrees_state.load_base_branches(self.repo) or prompt_for_base_branches(self.repo, self.screen_lines)

        if base_branches is None or base_branches is QUIT:
            return base_branches

        source_branch = base_branches[0] if len(base_branches) == 1 else prompt_for_branch(base_branches, self.screen_lines)

        return self.start_worktree(name, source_branch)

    def handle_options_key(self, key):
        if self.side_selection.handle_key(key):
            return None

        if key in (Key.LEFT, Key.ESC):
            self.side_selection = None

            return None

        if key != Key.ENTER:
            return None

        actions = {
            EDIT_BASE_BRANCHES: self.edit_base_branches,
            WORKTREE_FROM_BRANCH: self.add_worktree_from_branch,
        }

        return actions[self.side_selection.selected]()

    def add_worktree_from_branch(self):
        """Creates a worktree started from any branch of the repo, local or remote, without saving it as a base branch.
        Returns the created worktree, QUIT on Ctrl+C, or None to stay in the menu."""
        self.side_selection = None
        name = self.ask_valid_worktree_name()

        if name is None:
            return None

        source_branch = prompt_for_branch(worktrees.list_branches(self.repo), self.screen_lines)

        return self.start_worktree(name, source_branch)

    def edit_base_branches(self):
        self.side_selection = None
        base_branches = prompt_for_base_branches(self.repo, self.screen_lines)

        if base_branches is QUIT:
            return QUIT

        if base_branches is not None:
            self.message = Message("Base branches saved.", GREEN)

        return None


def prompt_for_worktree(repo, folder, header_lines, account, session):
    """Returns the chosen worktree (NO_WORKTREE for the main folder, BACK on Esc, QUIT on Ctrl+C) and the session mode."""
    menu = WorktreeMenu(repo, folder, header_lines, account, session)

    return menu.run(), menu.session
