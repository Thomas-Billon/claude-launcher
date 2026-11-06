"""
SessionStart hook the launcher declares to Claude Code at each launch (see accounts.py): records the id of the current
conversation in the session entry of the launcher (see sessions_state.py), at startup and after /clear or /resume.

Claude Code passes the hook input as JSON on stdin. The output of a SessionStart hook is added to the conversation:
this script never prints anything, and always exits with 0 so that Claude Code never shows a hook error.
"""

import json
import os
import sys

from launcher.sessions_state import ENTRY_VARIABLE, record_session_id


def main():
    try:
        entry_id = os.environ.get(ENTRY_VARIABLE)
        session_id = json.load(sys.stdin).get("session_id")

        if entry_id and session_id:
            record_session_id(entry_id, session_id)
    except Exception:
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
