"""
Console rendering and keyboard helpers shared by the launcher menus.
"""

import msvcrt
import os
import re
import shutil
import sys

KEY_UP = b"H"
KEY_DOWN = b"P"
KEY_LEFT = b"K"
KEY_RIGHT = b"M"
KEY_ENTER = b"\r"
KEY_ESC = b"\x1b"
KEY_CTRL_C = b"\x03"
ARROW_PREFIX = b"\xe0"

RESET = "\033[0m"
CYAN = "\033[96m"
DARK_CYAN = "\033[36m"
DARK_GRAY = "\033[90m"
GREEN = "\033[92m"
WHITE = "\033[97m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLACK_ON_GREEN = "\033[30;102m"

CURSOR_HOME = "\033[H"
CLEAR_LINE_END = "\033[K"
CLEAR_SCREEN_END = "\033[J"
HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"

ANSI_PATTERN = re.compile(r"\033\[[0-9;?]*[A-Za-z]")
MIN_LIST_ROWS = 3
COLUMN_SEPARATOR = " │ "
# INFO: List item rendered as an empty row and skipped by Up/Down, to split a list into groups
SEPARATOR = object()


def colorize(text, color):
    return f"{color}{text}{RESET}"


def truncate(text, max_length):
    if len(text) <= max_length:
        return text

    return text[: max_length - 1] + "…"


def visible_length(text):
    return len(ANSI_PATTERN.sub("", text))


def pad(text, width):
    return text + " " * max(0, width - visible_length(text))


def get_screen_size():
    width, height = shutil.get_terminal_size()

    # INFO: The last column is left empty so the console never wraps a line, which would break the row count
    return width - 1, height


def read_key():
    first_byte = msvcrt.getch()

    if first_byte == ARROW_PREFIX:
        return msvcrt.getch()

    return first_byte


def clear_screen():
    os.system("cls")


def hide_cursor():
    sys.stdout.write(HIDE_CURSOR)
    sys.stdout.flush()


def show_cursor():
    sys.stdout.write(SHOW_CURSOR)
    sys.stdout.flush()


def draw(lines):
    # INFO: The frame overwrites the previous one in place instead of clearing the screen first, which avoids flicker
    sys.stdout.write(CURSOR_HOME + "\n".join(line + CLEAR_LINE_END for line in lines) + CLEAR_SCREEN_END)
    sys.stdout.flush()


def build_header(max_length, details):
    lines = [
        "",
        colorize(truncate("  Claude Code Launcher", max_length), CYAN),
        colorize(truncate(f"  {'=' * 40}", max_length), DARK_CYAN),
    ]

    for label, value, color in details:
        lines.append(colorize(truncate(f"  {label:<9} : {value}", max_length), color))

    lines.append("")

    return lines


def build_footer(max_length, help_text, message=None):
    message_line = ""

    if message is not None:
        message_text, message_color = message
        message_line = colorize(truncate(f"  {message_text}", max_length), message_color)

    # INFO: The message row is always reserved so the help line never moves when a message appears or disappears
    return ["", message_line, "", colorize(truncate(help_text, max_length), DARK_GRAY)]


def join_columns(left_lines, right_lines, left_width):
    rows = max(len(left_lines), len(right_lines))
    left_lines = left_lines + [""] * (rows - len(left_lines))
    right_lines = right_lines + [""] * (rows - len(right_lines))

    return [
        pad(left, left_width) + colorize(COLUMN_SEPARATOR, DARK_GRAY) + right
        for left, right in zip(left_lines, right_lines)
    ]


def get_scroll_offset(scroll_offset, selected_index, visible_rows, item_count):
    if selected_index < scroll_offset:
        scroll_offset = selected_index
    elif selected_index >= scroll_offset + visible_rows:
        scroll_offset = selected_index - visible_rows + 1

    return max(0, min(scroll_offset, item_count - visible_rows))


class ListSelection:
    """Highlighted item of a vertical list, moved with Up/Down and rendered with scrolling."""

    def __init__(self, items, label=str, selected_index=0):
        self.items = items
        self.label = label
        self.selectable_indexes = [index for index, item in enumerate(items) if item is not SEPARATOR]
        self.selected_index = selected_index if selected_index in self.selectable_indexes else self._first_selectable()
        self.scroll_offset = 0

    def _first_selectable(self):
        return self.selectable_indexes[0] if self.selectable_indexes else 0

    @property
    def selected(self):
        return self.items[self.selected_index] if self.selectable_indexes else None

    def handle_key(self, key):
        if not self.selectable_indexes or key not in (KEY_UP, KEY_DOWN):
            return False

        step = -1 if key == KEY_UP else 1
        position = self.selectable_indexes.index(self.selected_index)
        self.selected_index = self.selectable_indexes[(position + step) % len(self.selectable_indexes)]

        return True

    def render(self, available_rows, max_length, has_cursor=True):
        if not self.items:
            return []

        item_count = len(self.items)
        is_scrollable = item_count > available_rows
        # INFO: When scrolling, two rows are reserved for the "more" indicators above and below the list
        visible_rows = available_rows - 2 if is_scrollable else item_count
        self.scroll_offset = get_scroll_offset(self.scroll_offset, self.selected_index, visible_rows, item_count)
        hidden_below = item_count - self.scroll_offset - visible_rows
        lines = []

        if is_scrollable:
            lines.append(colorize(f"  ↑ {self.scroll_offset} more", DARK_GRAY) if self.scroll_offset > 0 else "")

        for index in range(self.scroll_offset, self.scroll_offset + visible_rows):
            if self.items[index] is SEPARATOR:
                lines.append("")

                continue

            name = truncate(self.label(self.items[index]), max_length - 4)

            if index != self.selected_index:
                lines.append(colorize(f"    {name}", WHITE))
            elif has_cursor:
                lines.append(colorize("  > ", GREEN) + colorize(name, BLACK_ON_GREEN))
            else:
                lines.append("    " + colorize(name, BLACK_ON_GREEN))

        if is_scrollable:
            lines.append(colorize(f"  ↓ {hidden_below} more", DARK_GRAY) if hidden_below > 0 else "")

        return lines
