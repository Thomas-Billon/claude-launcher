import unittest

from launcher.keyboard import Key
from launcher.terminal_ui import ANSI_PATTERN, DARK_GRAY, SEPARATOR, ListSelection, SectionTitle

FIRST_TITLE = SectionTitle("First")
SECOND_TITLE = SectionTitle("Second")


def strip_colors(line):
    return ANSI_PATTERN.sub("", line)


class SectionTitleTest(unittest.TestCase):
    def setUp(self):
        self.items = [FIRST_TITLE, "alpha", SEPARATOR, SECOND_TITLE, "beta"]

    def test_title_is_never_selected_by_default(self):
        self.assertEqual(ListSelection(self.items).selected, "alpha")
        self.assertEqual(ListSelection(self.items, selected_index=3).selected, "alpha")

    def test_up_and_down_skip_titles_and_wrap(self):
        selection = ListSelection(self.items)

        selection.handle_key(Key.DOWN)
        self.assertEqual(selection.selected, "beta")

        selection.handle_key(Key.DOWN)
        self.assertEqual(selection.selected, "alpha")

        selection.handle_key(Key.UP)
        self.assertEqual(selection.selected, "beta")

    def test_list_of_titles_only_has_no_selection(self):
        self.assertIsNone(ListSelection([FIRST_TITLE, SECOND_TITLE]).selected)

    def test_title_is_rendered_gray_without_cursor(self):
        lines = ListSelection(self.items, str).render(20, 80)

        self.assertEqual([strip_colors(line).strip() for line in lines], ["First", "> alpha", "", "Second", "beta"])
        self.assertIn(DARK_GRAY, lines[0])
        self.assertIn(DARK_GRAY, lines[3])
