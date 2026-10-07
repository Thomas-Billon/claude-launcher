"""
Text questions asked under the launcher header: Y/N questions, commit messages and account names.

The answer is typed on an input line: Left/Right, Home/End to move, Backspace/Delete
to erase, Enter to confirm. Esc cancels when the question allows it, and Ctrl+C
raises KeyboardInterrupt to quit the launcher.
"""

from launcher.keyboard import TextKey, read_text_key
from launcher.terminal_ui import (
    CYAN,
    GREEN,
    WHITE,
    build_header,
    colorize,
    draw,
    get_screen_size,
    hide_cursor,
    move_cursor,
    show_cursor,
    truncate,
)

INPUT_PREFIX = "  > "


class LineEditor:
    """Text of the input line and position of the cursor in it."""

    def __init__(self, text):
        self.characters = list(text)
        self.cursor = len(self.characters)

    @property
    def text(self):
        return "".join(self.characters)

    def handle_key(self, key):
        if key == TextKey.LEFT:
            self.cursor = max(0, self.cursor - 1)
        elif key == TextKey.RIGHT:
            self.cursor = min(len(self.characters), self.cursor + 1)
        elif key == TextKey.HOME:
            self.cursor = 0
        elif key == TextKey.END:
            self.cursor = len(self.characters)
        elif key == TextKey.BACKSPACE and self.cursor > 0:
            self.cursor -= 1
            del self.characters[self.cursor]
        elif key == TextKey.DELETE and self.cursor < len(self.characters):
            del self.characters[self.cursor]
        elif len(key) == 1 and key.isprintable():
            self.characters.insert(self.cursor, key)
            self.cursor += 1


def render_question(header_lines, question, editor):
    max_length, _ = get_screen_size()
    header = build_header(max_length, header_lines)
    visible_width = max(max_length - len(INPUT_PREFIX), 1)
    # INFO: A text longer than the line scrolls horizontally, so the cursor always stays visible
    offset = max(0, editor.cursor - visible_width + 1)
    visible_text = editor.text[offset : offset + visible_width]

    draw(
        header
        + [
            colorize(truncate(f"  {question}", max_length), CYAN),
            colorize(INPUT_PREFIX, GREEN) + colorize(visible_text, WHITE),
        ]
    )
    move_cursor(len(header) + 2, len(INPUT_PREFIX) + editor.cursor - offset + 1)


def ask_text(header_lines, question, initial_text="", can_cancel=True):
    """Returns the typed text, or None when cancelled with Esc."""
    editor = LineEditor(initial_text)
    show_cursor()

    try:
        while True:
            render_question(header_lines, question, editor)
            key = read_text_key()

            if key == TextKey.CTRL_C:
                raise KeyboardInterrupt
            elif key == TextKey.ENTER:
                return editor.text
            elif key == TextKey.ESC and can_cancel:
                return None

            editor.handle_key(key)
    finally:
        hide_cursor()


def ask_required_text(header_lines, question, initial_text=""):
    """Returns the stripped text, or None when cancelled with Esc. An empty text is asked again."""
    while True:
        text = ask_text(header_lines, f"{question} (Enter: Confirm   Esc: Cancel)", initial_text)

        if text is None:
            return None

        if text.strip():
            return text.strip()


def ask_yes_no(header_lines, question):
    # INFO: Same rule as install.ps1: the answer is confirmed with Enter, and asked again until it is Y or N
    while True:
        answer = ask_text(header_lines, f"{question} (Y/N)", can_cancel=False).strip().upper()

        if answer in ("Y", "N"):
            return answer == "Y"


def ask_commit_message(header_lines, default_message):
    return ask_required_text(header_lines, "Commit message", default_message)


def ask_account_name(header_lines, current_name=""):
    return ask_required_text(header_lines, "Account name, e.g. Personal or Work", current_name)
