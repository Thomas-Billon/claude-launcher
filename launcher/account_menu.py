"""
Account menu: picks the Claude account (see accounts.py) Claude Code is launched with.

The menu has three modes, each with its own keys:
- account list: Up/Down to highlight, Enter to use the account, Right to open its
  options. A last entry adds a new account, named by the user: Claude Code itself
  asks for its login when launched;
- options of the highlighted account, in a right column: use, rename, default
  folder, history, delete. Left/Esc closes them;
- history of the account, in the same column: Enter removes a folder from it.
"""

from pathlib import Path

from launcher import accounts, launcher_state
from launcher.folder_menu import DEFAULT_FOLDER_HELP_TEXT, FolderEntry, format_folder_label, get_start_dir, prompt_for_folder
from launcher.keyboard import MenuKey, read_menu_key
from launcher.prompts import ask_account_name
from launcher.terminal_ui import (
    BACK,
    COLUMN_SEPARATOR,
    CYAN,
    DARK_GRAY,
    GREEN,
    QUIT,
    RED,
    YELLOW,
    HeaderLine,
    ListSelection,
    Message,
    join_columns,
    render_screen,
)

ACCOUNT_LIST_HELP_TEXT = "  Up/Down: Highlight   Right: Options   Enter: Select   Esc/Ctrl+C: Quit"
OPTIONS_HELP_TEXT = "  Up/Down: Highlight   Left/Esc: Back   Enter: Confirm   Ctrl+C: Quit"
HISTORY_HELP_TEXT = "  Up/Down: Highlight   Left/Esc: Back   Enter: Remove from history   Ctrl+C: Quit"

ADD_ACCOUNT_LABEL = "+ Add account"
USE_ACCOUNT = "Use account"
RENAME_ACCOUNT = "Rename account"
SET_DEFAULT_FOLDER = "Set default folder"
REMOVE_FROM_HISTORY = "Remove from history"
CLEAR_HISTORY = "Clear history"
DELETE_ACCOUNT = "Delete account"
CANCEL = "Cancel"
CONFIRM_CLEAR = "Confirm clear"
CONFIRM_DELETE = "Confirm delete"
ACCOUNT_OPTIONS = [USE_ACCOUNT, RENAME_ACCOUNT, SET_DEFAULT_FOLDER, REMOVE_FROM_HISTORY, CLEAR_HISTORY, DELETE_ACCOUNT]
# INFO: Cancel comes first so that a double Enter never clears the history or deletes an account
CLEAR_OPTIONS = [CANCEL, CONFIRM_CLEAR]
DELETE_OPTIONS = [CANCEL, CONFIRM_DELETE]


def account_label(item):
    # INFO: None stands for the "Add account" entry, always last
    return ADD_ACCOUNT_LABEL if item is None else item.label


def account_secondary_label(item):
    return None if item is None else item.secondary_label


def build_account_selection(account_list, selected_id):
    selected_index = next(
        (index for index, account in enumerate(account_list) if account.account_id == selected_id),
        0,
    )

    return ListSelection(account_list + [None], account_label, selected_index, account_secondary_label)


def build_options_selection(selected_option=None):
    selected_index = ACCOUNT_OPTIONS.index(selected_option) if selected_option else 0

    return ListSelection(ACCOUNT_OPTIONS, selected_index=selected_index)


def build_history_selection(account, selected_index=0):
    history = launcher_state.load_history(account)
    folders = [Path(folder) for folder in sorted(history, key=history.get, reverse=True)]
    entries = [FolderEntry(folder, format_folder_label(folder)) for folder in folders]

    return ListSelection(entries, lambda entry: entry.label, min(selected_index, len(entries) - 1))


class AccountMenu:
    """State of the menu between two keys. Each key handler returns the outcome of the menu, or None to go on."""

    def __init__(self, header_lines, selected_id):
        self.header_lines = header_lines
        self.account_list = []
        self.account_selection = None
        # INFO: Right column, None while closed. It lists either the account options or its history
        self.side_selection = None
        self.is_history_open = False
        self.message = None
        self.reload_accounts(selected_id)

    @property
    def account(self):
        return self.account_selection.selected

    @property
    def help_text(self):
        if self.side_selection is None:
            return ACCOUNT_LIST_HELP_TEXT

        return HISTORY_HELP_TEXT if self.is_history_open else OPTIONS_HELP_TEXT

    def reload_accounts(self, selected_id=None):
        self.account_list = accounts.load_accounts()
        self.account_selection = build_account_selection(self.account_list, selected_id)

    def run(self):
        """Returns the chosen account, or QUIT."""
        while True:
            self.render()
            key = read_menu_key()
            self.message = None

            if key == MenuKey.CTRL_C:
                return QUIT

            if self.side_selection is None:
                outcome = self.handle_account_list_key(key)
            elif self.is_history_open:
                outcome = self.handle_history_key(key)
            else:
                outcome = self.handle_options_key(key)

            if outcome is not None:
                return outcome

    def render(self):
        def render_body(available_rows, max_length):
            if self.side_selection is None:
                return self.account_selection.render(available_rows, max_length)

            # INFO: A secondary label is rendered after its label, 2 spaces apart
            longest_label = max(
                len(account_label(item)) + len(account_secondary_label(item) or "") + 2
                for item in self.account_selection.items
            )
            left_width = min(longest_label + 4, max_length // 2)
            right_width = max_length - left_width - len(COLUMN_SEPARATOR)

            return join_columns(
                self.account_selection.render(available_rows, left_width, has_cursor=False),
                self.side_selection.render(available_rows, right_width),
                left_width,
            )

        render_screen(self.header_lines, render_body, self.help_text, self.message)

    def handle_account_list_key(self, key):
        if self.account_selection.handle_key(key):
            return None

        if key == MenuKey.ESC:
            return QUIT

        if key == MenuKey.RIGHT and self.account is not None:
            self.side_selection = build_options_selection()
        elif key == MenuKey.ENTER and self.account is None:
            self.add_account()
        elif key == MenuKey.ENTER:
            return self.account

        return None

    def add_account(self):
        name = ask_account_name(self.header_lines)

        if name is None:
            return

        account = accounts.create_account(name)
        self.message = Message("Account added, Claude Code will ask for its login on first launch.", GREEN)
        self.reload_accounts(account.account_id)

    def handle_options_key(self, key):
        if self.side_selection.handle_key(key):
            return None

        if key in (MenuKey.LEFT, MenuKey.ESC):
            self.side_selection = None

            return None

        if key != MenuKey.ENTER:
            return None

        actions = {
            USE_ACCOUNT: self.use_account,
            RENAME_ACCOUNT: self.rename_account,
            SET_DEFAULT_FOLDER: self.set_default_folder,
            REMOVE_FROM_HISTORY: self.open_history,
            CLEAR_HISTORY: self.ask_clear_history,
            CONFIRM_CLEAR: self.clear_history,
            DELETE_ACCOUNT: self.ask_delete_account,
            CONFIRM_DELETE: self.delete_account,
            CANCEL: self.cancel_confirmation,
        }

        return actions[self.side_selection.selected]()

    def use_account(self):
        return self.account

    def rename_account(self):
        account = self.account
        name = ask_account_name(self.header_lines, account.name or account.email or "")
        self.side_selection = None

        if name is None:
            return None

        launcher_state.save_name(account, name)
        self.message = Message(f"Account renamed to {name}.", GREEN)
        self.reload_accounts(account.account_id)

        return None

    def set_default_folder(self):
        account = self.account
        self.side_selection = None
        selected_path = prompt_for_folder(
            get_start_dir(account),
            self.header_lines,
            account,
            DEFAULT_FOLDER_HELP_TEXT,
            Message("Choose the default folder of this account.", CYAN),
        )

        if selected_path is QUIT:
            return QUIT

        if selected_path is not BACK:
            launcher_state.save_default_dir(account, selected_path)
            self.message = Message(f"Default folder set to {selected_path}", GREEN)

        return None

    def has_history(self):
        if launcher_state.load_history(self.account):
            return True

        self.message = Message("The history of this account is empty.", YELLOW)

        return False

    def open_history(self):
        if self.has_history():
            self.is_history_open = True
            self.side_selection = build_history_selection(self.account)

        return None

    def ask_clear_history(self):
        if self.has_history():
            self.side_selection = ListSelection(CLEAR_OPTIONS)

        return None

    def clear_history(self):
        launcher_state.clear_history(self.account)
        self.message = Message("History cleared.", GREEN)
        self.side_selection = build_options_selection(CLEAR_HISTORY)

        return None

    def ask_delete_account(self):
        self.side_selection = ListSelection(DELETE_OPTIONS)

        return None

    def delete_account(self):
        self.side_selection = None

        try:
            accounts.delete_account(self.account)
            self.message = Message("Account deleted.", GREEN)
        except OSError:
            self.message = Message("Could not fully delete the account, is Claude Code still running with it?", RED)

        self.reload_accounts()

        return None

    def cancel_confirmation(self):
        cancelled_option = CLEAR_HISTORY if self.side_selection.items is CLEAR_OPTIONS else DELETE_ACCOUNT
        self.side_selection = build_options_selection(cancelled_option)

        return None

    def handle_history_key(self, key):
        if self.side_selection.handle_key(key):
            return None

        if key in (MenuKey.LEFT, MenuKey.ESC):
            self.close_history()
        elif key == MenuKey.ENTER:
            self.remove_from_history()

        return None

    def remove_from_history(self):
        removed_folder = self.side_selection.selected.path
        launcher_state.remove_from_history(self.account, removed_folder)
        self.message = Message(f"Removed {removed_folder} from history.", GREEN)
        self.side_selection = build_history_selection(self.account, self.side_selection.selected_index)

        if self.side_selection.selected is None:
            self.close_history()

    def close_history(self):
        self.is_history_open = False
        self.side_selection = build_options_selection(REMOVE_FROM_HISTORY)


def prompt_for_account(header_lines, selected_id=None):
    """Returns the chosen account, or QUIT."""
    render_screen([*header_lines, HeaderLine("Account", "loading…", DARK_GRAY)])

    return AccountMenu(header_lines, selected_id).run()
