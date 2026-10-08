"""
Interactive launcher that starts Claude Code with a chosen account in a chosen project directory.

Steps, each one adding its line to the header (modules in the launcher folder):
1. Repo syncs (repo_sync.py): the launcher repo, then the shared skills repo, are
   synced with their remote. When new launcher commits are pulled, the launcher
   restarts itself to run them.
2. Account (account_menu.py). Claude Code asks for the login of a logged out
   account itself, after which an account already in the list is reported.
3. Folder (folder_menu.py) where `claude` is launched, and session mode.

The -a argument skips the account menu, and the folder menu too along with -d.
Otherwise the folder list starts from the -d argument, else from the default
folder of the account (launcher_state.py), else from the user's home directory.
Arguments after -- are passed to Claude Code.
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
from launcher.folder_menu import NEW_SESSION, get_start_dir, prompt_for_launch_folder, session_header_line
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
    set_title,
    show_cursor,
)

# INFO: Set for the restarted launcher, which shows the launcher line of the previous run instead of syncing again
RESTART_HEADER_VARIABLE = "CLAUDE_LAUNCHER_RESTART_HEADER"

# INFO: When needs_restart is set, header_lines only holds the launcher line, passed on to the restarted launcher
SyncResult = namedtuple("SyncResult", "header_lines needs_restart")


def split_claude_arguments(command_line):
    """Splits the command line at the first --, returns the launcher arguments and the Claude Code arguments."""
    if "--" not in command_line:
        return command_line, []

    separator_index = command_line.index("--")

    return command_line[:separator_index], command_line[separator_index + 1 :]


def parse_arguments():
    launcher_arguments, claude_arguments = split_claude_arguments(sys.argv[1:])
    parser = argparse.ArgumentParser(
        description="Pick a Claude account and a project folder, then launch Claude Code.",
        epilog="Arguments after -- are passed to Claude Code, e.g. -- --model opus",
    )
    parser.add_argument(
        "-a",
        "--account",
        help="Account to launch with, by name, email or id: skips the account menu, and the folder menu too with -d",
    )
    parser.add_argument(
        "-d",
        "--directory",
        help="Folder to launch Claude Code in with -a, else directory to start the folder menu from"
        " (default: the account default folder, then the home directory)",
    )
    arguments = parser.parse_args(launcher_arguments)
    arguments.claude_arguments = claude_arguments

    return arguments


def check_prerequisites(argument_dir):
    """Returns the error to show, or None when the launcher can run."""
    if argument_dir is not None and not argument_dir.is_dir():
        return f'Directory not found: "{argument_dir}".'

    if accounts.find_claude_executable() is None:
        return "Claude Code CLI (claude) not found in PATH."

    return None


def find_argument_account(account_query):
    """Returns the account matching the -a argument (None without it), and the error to show when none matches."""
    if account_query is None:
        return None, None

    matches = accounts.find_accounts(account_query)

    if len(matches) == 1:
        return matches[0], None

    if matches:
        return None, f'Several accounts match "{account_query}", use the account name or id.'

    names = ", ".join(account.display_name for account in accounts.load_accounts()) or "none yet"

    return None, f'No account matches "{account_query}". Accounts: {names}.'


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


def run_menus(argument_dir, argument_account, header_lines):
    """Runs the menus, each one adding its line to the header. Returns the chosen account, folder and session mode,
    or None values on Ctrl+C."""
    account = argument_account
    # INFO: -a only skips the account menu once, Esc in the folder menu still goes back to it
    is_account_chosen = account is not None

    while True:
        if not is_account_chosen:
            # INFO: Coming back from the folder list keeps the account that was just chosen highlighted
            account = prompt_for_account(header_lines, account.account_id if account else None)

            if account is QUIT:
                return None, None, None

        is_account_chosen = False
        start_dir = argument_dir or get_start_dir(account)
        selected_path, session = prompt_for_launch_folder(start_dir, header_lines, account)

        if selected_path is QUIT:
            return None, None, None

        if selected_path is not BACK:
            return account, selected_path, session


def pick_launch_target(argument_dir, argument_account, header_lines):
    """Returns the account, folder and session mode to launch, chosen without any menu with both -a and -d."""
    if argument_account is not None and argument_dir is not None:
        account, folder, session = argument_account, argument_dir, NEW_SESSION
    else:
        account, folder, session = run_menus(argument_dir, argument_account, header_lines)

        if account is None:
            return None, None, None

    launcher_state.record_launch(account, folder)
    lines = [*header_lines, accounts.account_header_line(account), HeaderLine("Directory", folder, GREEN)]

    if session is not NEW_SESSION:
        lines.append(session_header_line(session, GREEN))

    render_screen(lines)

    return account, folder, session


def cancel():
    clear_screen()
    print(colorize("Cancelled.", YELLOW))

    return 0


def launch_claude_code(account, folder, claude_arguments):
    """Returns the exit code of Claude Code."""
    failed_links = accounts.prepare_account_dir(account.config_dir)

    if failed_links:
        print(colorize(f"  Warning: could not link shared {', '.join(failed_links)} from ~/.claude", YELLOW))

    print(colorize("  Opening Claude Code…", CYAN))
    print()

    # INFO: A drive root has no name
    set_title(f"Claude Code · {account.display_name} · {folder.name or folder}")
    os.chdir(folder)

    return subprocess.run(accounts.build_launch_command(claude_arguments), env=accounts.build_environment(account)).returncode


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
    argument_account = None

    if error is None:
        argument_account, error = find_argument_account(arguments.account)

    if error is not None:
        print(colorize(error, RED))

        return 1

    set_title("Claude Code Launcher")
    clear_screen()
    hide_cursor()

    try:
        sync_result = sync_repos()

        if sync_result.needs_restart:
            return restart(sync_result.header_lines)

        account, folder, session = pick_launch_target(argument_dir, argument_account, sync_result.header_lines)
    except KeyboardInterrupt:
        # INFO: Raised by Ctrl+C in a question of the repo syncs or of the account menu
        account, folder, session = None, None, None
    finally:
        show_cursor()

    if account is None:
        return cancel()

    exit_code = launch_claude_code(account, folder, [*session.claude_arguments, *arguments.claude_arguments])
    report_duplicate(account)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
