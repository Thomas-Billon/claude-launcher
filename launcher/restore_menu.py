"""
Restore menu, shown before the account menu when sessions left open at the previous close can be restored
(see session_restore.py).

The menu has two screens:
- choice between restoring the sessions and starting a new session. Esc quits;
- list of the sessions, all checked: Space checks or unchecks the highlighted one, Enter restores the checked ones,
  Esc goes back to the choice.
"""

from launcher.keyboard import Key, read_key
from launcher.terminal_ui import QUIT, ListSelection, pluralize, render_screen

CHOICE_HELP_TEXT = "  Up/Down: Highlight   Enter: Select   Esc/Ctrl+C: Quit"
SESSION_LIST_HELP_TEXT = "  Up/Down: Highlight   Space: Check   Enter: Restore   Esc: Back   Ctrl+C: Quit"

START_NEW_SESSION = "Start new session"
LAST_MESSAGE_FORMAT = "%Y-%m-%d %H:%M"


def restore_label(session_count):
    """Returns `Restore 1 session` or `Restore N sessions`."""
    return f"Restore {pluralize(session_count, 'session')}"


def last_message_label(session):
    return session.last_message_at.strftime(LAST_MESSAGE_FORMAT)


class RestoreMenu:
    """State of the menu between two keys. Each key handler returns the outcome of the menu, or None to go on."""

    def __init__(self, header_lines, sessions):
        self.header_lines = header_lines
        self.sessions = sessions
        self.choice_selection = ListSelection([restore_label(len(sessions)), START_NEW_SESSION])
        # INFO: List of the sessions, None while the choice screen shows
        self.session_selection = None
        self.checked_entry_ids = set()

    def session_label(self, session):
        return f"[x] {session.label}" if session.entry_id in self.checked_entry_ids else f"[ ] {session.label}"

    def open_session_list(self):
        self.checked_entry_ids = {session.entry_id for session in self.sessions}
        self.session_selection = ListSelection(self.sessions, self.session_label, secondary_label=last_message_label)

    def run(self):
        """Returns the checked sessions in list order, an empty list to start a new session, or QUIT."""
        while True:
            if self.session_selection is None:
                render_screen(self.header_lines, self.choice_selection.render, CHOICE_HELP_TEXT)
            else:
                render_screen(self.header_lines, self.session_selection.render, SESSION_LIST_HELP_TEXT)

            key = read_key()

            if key == Key.CTRL_C:
                return QUIT

            if self.session_selection is None:
                outcome = self.handle_choice_key(key)
            else:
                outcome = self.handle_session_list_key(key)

            if outcome is not None:
                return outcome

    def handle_choice_key(self, key):
        if self.choice_selection.handle_key(key):
            return None

        if key == Key.ESC:
            return QUIT

        if key == Key.ENTER and self.choice_selection.selected == START_NEW_SESSION:
            return []

        if key == Key.ENTER:
            self.open_session_list()

        return None

    def handle_session_list_key(self, key):
        if self.session_selection.handle_key(key):
            return None

        if key == Key.ESC:
            self.session_selection = None
        elif key == Key.SPACE:
            self.toggle_session(self.session_selection.selected)
        elif key == Key.ENTER:
            return [session for session in self.sessions if session.entry_id in self.checked_entry_ids]

        return None

    def toggle_session(self, session):
        self.checked_entry_ids ^= {session.entry_id}


def prompt_for_restore(header_lines, sessions):
    """Returns the sessions to restore in list order, an empty list to start a new session, or QUIT."""
    return RestoreMenu(header_lines, sessions).run()
