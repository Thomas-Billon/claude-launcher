"""
Worktree menu: picks where Claude Code is launched in a git repo, its main folder or one of its worktrees (see worktrees.py).

The list holds the main folder entry, the worktrees of the repo, then a new worktree entry.
The worktrees whose origin branch was merged and deleted on the remote are marked as merged.
Tab cycles the session mode, as in the folder menu.

A new worktree is named, then started from a branch of the repo picked in a list: the favorite
branches of the repo are on top, Ctrl+F toggles the highlighted branch as a favorite, typed
characters filter the list, Backspace erases them and Esc clears the filter.
"""

from launcher import history, worktrees, worktrees_state
from launcher.accounts import account_header_line
from launcher.folder_menu import NEW_SESSION, SESSION_MODES, session_header_line
from launcher.keyboard import Key, is_typed_character, read_key, read_key_unless
from launcher.prompts import ask_worktree_name
from launcher.terminal_ui import (
    BACK,
    CYAN,
    DARK_GRAY,
    GREEN,
    QUIT,
    RED,
    SEPARATOR,
    HeaderLine,
    ListSelection,
    Message,
    SectionTitle,
    render_screen,
)

WORKTREE_HELP_TEXT = "  Up/Down: Highlight   Tab: Session   Enter: Launch   Esc: Back   Ctrl+C: Quit"
BRANCH_PICKER_HELP_TEXT = "  Up/Down: Highlight   Type: Filter   Ctrl+F: Favorite   Enter: Select   Esc: Back   Ctrl+C: Quit"

BRANCH_PICKER_MESSAGE = Message("Origin branch of the new worktree.", CYAN)

# INFO: Entries of the list besides the worktrees, NO_WORKTREE is also the outcome of the menu for the main folder
ADD_WORKTREE = object()
NO_WORKTREE = object()

FAVORITES_TITLE = SectionTitle("★ Favorites")
BRANCHES_TITLE = SectionTitle("Branches")


def format_origin(worktree):
    """Returns the origin of the worktree followed by its merged marker, None without origin."""
    if worktree.origin_branch is None:
        return None

    return f"{worktree.origin_branch} · merged" if worktree.is_merged else worktree.origin_branch


def worktree_header_line(worktree, color):
    origin = format_origin(worktree)

    return HeaderLine("Worktree", worktree.name if origin is None else f"{worktree.name}  (from {origin})", color)


def entry_label(entry):
    if entry is ADD_WORKTREE:
        return "+ Worktree"

    return "No worktree" if entry is NO_WORKTREE else entry.name


def entry_secondary_label(entry):
    if not isinstance(entry, worktrees.Worktree) or entry.origin_branch is None:
        return None

    return f"from {format_origin(entry)}"


class BranchPicker:
    """Picks the origin branch of a new worktree. Each key handler returns the outcome of the picker, or None to go on."""

    def __init__(self, repo, header_lines, fetch_process):
        self.repo = repo
        self.header_lines = header_lines
        self.fetch_process = fetch_process
        self.is_fetch_pending = fetch_process.poll() is None
        self.notice = None
        self.filter_text = ""
        self.branches = []
        self.favorite_branches = []
        self.selection = None
        self.load_branches()
        self.rebuild()

    @property
    def screen_lines(self):
        if not self.filter_text:
            return self.header_lines

        return [*self.header_lines, HeaderLine("Filter", self.filter_text, DARK_GRAY)]

    def load_branches(self):
        self.branches = worktrees.list_branches(self.repo)
        self.load_favorites()

    def has_fetch_ended(self):
        """Returns whether the fetch started with the worktree menu has ended since the branches were listed."""
        return self.is_fetch_pending and self.fetch_process.poll() is not None

    def refresh_after_fetch(self):
        """Lists again the branches, with those the fetch added or deleted, keeping the highlighted branch."""
        self.is_fetch_pending = False
        selected = self.selection.selected
        self.load_branches()
        self.rebuild(selected)

    def load_favorites(self):
        # INFO: A favorite deleted since is hidden, but stays saved
        self.favorite_branches = sorted(
            (branch for branch in worktrees_state.load_favorite_branches(self.repo) if worktrees.is_existing_branch(self.repo, branch)),
            key=str.casefold,
        )

    def rebuild(self, selected_branch=None):
        def matches_filter(branch):
            return self.filter_text.casefold() in branch.casefold()

        favorites = [branch for branch in self.favorite_branches if matches_filter(branch)]
        branches = [branch for branch in self.branches if matches_filter(branch)]
        favorites_section = [FAVORITES_TITLE, *favorites, SEPARATOR] if favorites else []
        items = [*favorites_section, BRANCHES_TITLE, *branches]
        matching_indexes = [index for index, item in enumerate(items) if item == selected_branch] if selected_branch is not None else []

        # INFO: A branch both favorite and listed is highlighted among the branches, listed last
        self.selection = ListSelection(items, selected_index=matching_indexes[-1] if matching_indexes else 0)

    def handle_key(self, key):
        """Returns the picked branch, BACK on Esc with an empty filter, or None to go on."""
        selected = self.selection.selected

        if key == Key.ENTER and selected is not None:
            return selected

        if key == Key.CTRL_F and selected is not None:
            self.toggle_favorite(selected)
        elif key == Key.BACKSPACE and self.filter_text:
            self.set_filter(self.filter_text[:-1])
        elif key == Key.ESC and self.filter_text:
            self.set_filter("")
        elif key == Key.ESC:
            return BACK
        elif is_typed_character(key):
            self.set_filter(self.filter_text + key)

        return None

    def toggle_favorite(self, branch):
        is_favorite = worktrees_state.toggle_favorite_branch(self.repo, branch)
        self.load_favorites()
        self.rebuild(branch)
        self.notice = Message(f"Added {branch} to favorites." if is_favorite else f"Removed {branch} from favorites.", GREEN)

    def set_filter(self, filter_text):
        self.filter_text = filter_text
        self.rebuild()


def prompt_for_branch(repo, header_lines, fetch_process):
    """Returns the picked branch, BACK on Esc or QUIT on Ctrl+C."""
    picker = BranchPicker(repo, header_lines, fetch_process)

    while True:
        render_screen(picker.screen_lines, picker.selection.render, BRANCH_PICKER_HELP_TEXT, picker.notice or BRANCH_PICKER_MESSAGE)
        key = read_key_unless(picker.has_fetch_ended)

        if key is None:
            picker.refresh_after_fetch()

            continue

        picker.notice = None

        if key == Key.CTRL_C:
            return QUIT

        if picker.selection.handle_key(key):
            continue

        outcome = picker.handle_key(key)

        if outcome is not None:
            return outcome


class WorktreeMenu:
    """State of the menu between two keys. Each key handler returns the outcome of the menu, or None to go on."""

    def __init__(self, repo, folder, header_lines, account, session):
        self.repo = repo
        self.folder = folder
        self.header_lines = header_lines
        self.account = account
        self.session_index = SESSION_MODES.index(session)
        self.message = None

        worktree_list = worktrees.load_worktrees(repo)
        # INFO: A fetch takes seconds on some remotes, the merged markers it changes show at the next opening
        self.fetch_process = worktrees.start_fetch_prune(repo)
        history.remove_stale_links(account.config_dir, repo, worktrees.list_registered_paths(repo))
        items = [NO_WORKTREE, *([SEPARATOR, *worktree_list] if worktree_list else []), SEPARATOR, ADD_WORKTREE]
        # INFO: No worktree is highlighted first, so that a double Enter launches in the main folder as before worktrees
        self.selection = ListSelection(items, entry_label, 0, entry_secondary_label)

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

    def run(self):
        """Returns the chosen worktree, NO_WORKTREE for the main folder, BACK on Esc or QUIT on Ctrl+C."""
        while True:
            render_screen(self.screen_lines, self.selection.render, WORKTREE_HELP_TEXT, self.message)
            key = read_key()
            self.message = None

            if key == Key.CTRL_C:
                return QUIT

            outcome = self.handle_list_key(key)

            if outcome is not None:
                return outcome

    def handle_list_key(self, key):
        if self.selection.handle_key(key):
            return None

        entry = self.entry

        if key == Key.ESC:
            return BACK

        if key == Key.TAB:
            self.session_index = (self.session_index + 1) % len(SESSION_MODES)
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

    def add_worktree(self):
        """Returns the created worktree, QUIT on Ctrl+C, or None to stay in the menu."""
        name = self.ask_valid_worktree_name()

        if name is None:
            return None

        origin_branch = prompt_for_branch(self.repo, self.screen_lines, self.fetch_process)

        if origin_branch is QUIT:
            return QUIT

        if origin_branch is BACK:
            return None

        worktree = worktrees.create_worktree(self.repo, name, origin_branch)

        if worktree is None:
            self.message = Message("Could not create the worktree.", RED)

        return worktree


def prompt_for_worktree(repo, folder, header_lines, account, session):
    """Returns the chosen worktree (NO_WORKTREE for the main folder, BACK on Esc, QUIT on Ctrl+C) and the session mode."""
    menu = WorktreeMenu(repo, folder, header_lines, account, session)

    return menu.run(), menu.session
