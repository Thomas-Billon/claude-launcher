"""
Interactive launcher that starts Claude Code with a chosen account in a chosen project directory.

Steps, each one adding its line to the header (modules in the launcher folder):
1. Repo syncs (repo_sync.py): the launcher repo, then the shared skills repo, are
   synced with their remote. When new launcher commits are pulled, the launcher
   restarts itself to run them.
2. Account (account_menu.py). Claude Code asks for the login of a logged out
   account itself, after which an account already in the list is reported.
3. Folder (folder_menu.py) where `claude` is launched.

The folder list starts from the -d argument, else from the default folder of
the account (launcher_state.py), else from the user's home directory.
"""

import argparse
import json
import os
import subprocess
import sys
from collections import namedtuple
from pathlib import Path

from launcher import accounts, launcher_state, repo_sync
from launcher.account_menu import prompt_for_account
from launcher.folder_menu import get_start_dir, prompt_for_folder
from launcher.terminal_ui import (
    BACK,
    CYAN,
    GREEN,
    QUIT,
    RED,
    YELLOW,
    HeaderLine,
    clear_screen,
    colorize,
    hide_cursor,
    render_screen,
    show_cursor,
)

# INFO: Set for the restarted launcher, which shows the launcher line of the previous run instead of syncing again
RESTART_HEADER_VARIABLE = "CLAUDE_LAUNCHER_RESTART_HEADER"

# INFO: When needs_restart is set, header_lines only holds the launcher line, passed on to the restarted launcher
SyncResult = namedtuple("SyncResult", "header_lines needs_restart")


def parse_arguments():
    parser = argparse.ArgumentParser(description="Pick a Claude account and a project folder, then launch Claude Code.")
    parser.add_argument(
        "-d",
        "--directory",
        help="Directory to scan for project folders (default: the account default folder, then the home directory)",
    )

    return parser.parse_args()


def check_prerequisites(argument_dir):
    """Returns the error to show, or None when the launcher can run."""
    if argument_dir is not None and not argument_dir.is_dir():
        return f'No folders found in "{argument_dir}".'

    if accounts.find_claude_executable() is None:
        return "Claude Code CLI (claude) not found in PATH."

    return None


def sync_repos():
    # INFO: Removed from the environment so that Claude Code and a later restart do not inherit it
    restart_header = os.environ.pop(RESTART_HEADER_VARIABLE, None)

    if restart_header is not None:
        header_lines = [HeaderLine(*line) for line in json.loads(restart_header)]
    else:
        launcher_line, is_pulled = repo_sync.sync_launcher_repo()

        if is_pulled:
            return SyncResult([launcher_line], needs_restart=True)

        header_lines = [launcher_line] if launcher_line is not None else []

    skills_line = repo_sync.sync_skills_repo(header_lines)

    return SyncResult(header_lines + ([skills_line] if skills_line is not None else []), needs_restart=False)


def restart(header_lines):
    # INFO: The pulled code only runs in a new process, this one waits for it and returns its exit code
    environment = {**os.environ, RESTART_HEADER_VARIABLE: json.dumps(header_lines)}

    return subprocess.run([sys.executable, *sys.argv], env=environment).returncode


def pick_launch_target(argument_dir, header_lines):
    """Runs the menus, each one adding its line to the header, and returns the chosen account and folder."""
    account = None

    while True:
        # INFO: Coming back from the folder list keeps the account that was just chosen highlighted
        account = prompt_for_account(header_lines, account.account_id if account else None)

        if account is QUIT:
            return None, None

        start_dir = argument_dir or get_start_dir(account)
        selected_path = prompt_for_folder(start_dir, header_lines, account, show_recent=True)

        if selected_path is QUIT:
            return None, None

        if selected_path is not BACK:
            break

    launcher_state.record_launch(account, selected_path)
    render_screen([*header_lines, accounts.account_header_line(account), HeaderLine("Directory", selected_path, GREEN)])

    return account, selected_path


def cancel():
    clear_screen()
    print(colorize("Cancelled.", YELLOW))

    return 0


def launch_claude_code(account, folder):
    """Returns the exit code of Claude Code."""
    failed_links = accounts.prepare_account_dir(account.config_dir)

    if failed_links:
        print(colorize(f"  Warning: could not link shared {', '.join(failed_links)} from ~/.claude", YELLOW))

    print(colorize("  Opening Claude Code…", CYAN))
    print()

    os.chdir(folder)

    return subprocess.run(accounts.build_launch_command(), env=accounts.build_environment(account)).returncode


def report_duplicate(account):
    duplicate = accounts.find_duplicate(account)

    if duplicate is None:
        return

    print()
    print(colorize(f'  Warning: this Claude account is also the "{duplicate.label}" account of the launcher,', YELLOW))
    print(colorize("  one of them can be removed with Delete account.", YELLOW))


def main():
    # INFO: Empty system call enables ANSI escape code processing in the Windows console
    os.system("")

    arguments = parse_arguments()
    argument_dir = Path(arguments.directory).resolve() if arguments.directory else None
    error = check_prerequisites(argument_dir)

    if error is not None:
        print(colorize(error, RED))

        return 1

    clear_screen()
    hide_cursor()

    try:
        sync_result = sync_repos()

        if sync_result.needs_restart:
            return restart(sync_result.header_lines)

        account, folder = pick_launch_target(argument_dir, sync_result.header_lines)
    except KeyboardInterrupt:
        # INFO: Raised by Ctrl+C in a question of the repo syncs or of the account menu
        account, folder = None, None
    finally:
        show_cursor()

    if account is None:
        return cancel()

    exit_code = launch_claude_code(account, folder)
    report_duplicate(account)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
