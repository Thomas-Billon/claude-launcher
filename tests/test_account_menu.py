import unittest

from launcher import account_menu


class AccountOptionsTest(unittest.TestCase):
    def test_history_options_are_removed(self):
        self.assertEqual(
            account_menu.ACCOUNT_OPTIONS,
            [account_menu.USE_ACCOUNT, account_menu.RENAME_ACCOUNT, account_menu.SET_DEFAULT_FOLDER, account_menu.DELETE_ACCOUNT],
        )

        for name in ("REMOVE_FROM_HISTORY", "CLEAR_HISTORY", "CLEAR_OPTIONS", "CONFIRM_CLEAR", "HISTORY_HELP_TEXT"):
            self.assertFalse(hasattr(account_menu, name), name)
