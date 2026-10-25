"""
Account menu: picks the Claude account (see accounts.py) Claude Code is launched with.

The menu has two modes, each with its own keys:
- account list: Up/Down to highlight, Enter to use the account, Right to open its
  options. A last entry adds a new account, named by the user: Claude Code itself
  asks for its login when launched;
- options of the highlighted account, in a right column: use, rename, default
  folder, delete. Left/Esc closes them.
"""

from launcher import accounts, launcher_state
from launcher.folder_menu import get_start_dir, prompt_for_folder
from launcher.keyboard import Key, read_key
from launcher.prompts import ask_account_name
from launcher.terminal_ui import (
    BACK,
    COLUMN_SEPARATOR,
    CYAN,
    DARK_GRAY,
    GREEN,
    QUIT,
    RED,
    HeaderLine,
    ListSelection,
    Message,
    join_columns,
    render_screen,
)

ACCOUNT_LIST_HELP_TEXT = "  Up/Down: Highlight   Right: Options   Enter: Select   Esc/Ctrl+C: Quit"
OPTIONS_HELP_TEXT = "  Up/Down: Highlight   Left/Esc: Back   Enter: Confirm   Ctrl+C: Quit"

ADD_ACCOUNT_LABEL = "+ Add account"
USE_ACCOUNT = "Use account"
RENAME_ACCOUNT = "Rename account"
SET_DEFAULT_FOLDER = "Set default folder"
DELETE_ACCOUNT = "Delete account"
CANCEL = "Cancel"
CONFIRM_DELETE = "Confirm delete"
ACCOUNT_OPTIONS = [USE_ACCOUNT, RENAME_ACCOUNT, SET_DEFAULT_FOLDER, DELETE_ACCOUNT]
# INFO: Cancel comes first so that a double Enter never deletes an account
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


class AccountMenu:
    """State of the menu between two keys. Each key handler returns the outcome of the menu, or None to go on."""

    def __init__(self, header_lines, selected_id):
        self.header_lines = header_lines
        self.account_list = []
        self.account_selection = None
        # INFO: Right column listing the account options, None while closed
        self.side_selection = None
        self.message = None
        self.reload_accounts(selected_id)

    @property
    def account(self):
        return self.account_selection.selected

    @property
    def help_text(self):
        return ACCOUNT_LIST_HELP_TEXT if self.side_selection is None else OPTIONS_HELP_TEXT

    def reload_accounts(self, selected_id=None):
        self.account_list = accounts.load_accounts()
        self.account_selection = build_account_selection(self.account_list, selected_id)

    def run(self):
        """Returns the chosen account, or QUIT."""
        while True:
            self.render()
            key = read_key()
            self.message = None

            if key == Key.CTRL_C:
                return QUIT

            if self.side_selection is None:
                outcome = self.handle_account_list_key(key)
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

        if key == Key.ESC:
            return QUIT

        if key == Key.RIGHT and self.account is not None:
            self.side_selection = build_options_selection()
        elif key == Key.ENTER and self.account is None:
            self.add_account()
        elif key == Key.ENTER:
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

        if key in (Key.LEFT, Key.ESC):
            self.side_selection = None

            return None

        if key != Key.ENTER:
            return None

        actions = {
            USE_ACCOUNT: self.use_account,
            RENAME_ACCOUNT: self.rename_account,
            SET_DEFAULT_FOLDER: self.set_default_folder,
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
            Message("Choose the default folder of this account.", CYAN),
        )

        if selected_path is QUIT:
            return QUIT

        if selected_path is not BACK:
            launcher_state.save_default_dir(account, selected_path)
            self.message = Message(f"Default folder set to {selected_path}", GREEN)

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
        self.side_selection = build_options_selection(DELETE_ACCOUNT)

        return None


def prompt_for_account(header_lines, selected_id=None):
    """Returns the chosen account, or QUIT."""
    render_screen([*header_lines, HeaderLine("Account", "loading…", DARK_GRAY)])

    return AccountMenu(header_lines, selected_id).run()
