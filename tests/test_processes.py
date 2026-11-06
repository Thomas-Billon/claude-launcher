import os
import subprocess
import sys
import time
import unittest

from launcher import processes


def start_ended_process():
    """Returns the id of a process that has already ended."""
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait()

    return process.pid


class StartTimeTest(unittest.TestCase):
    def test_current_process_has_a_start_time_in_the_past(self):
        started_at = processes.read_start_time(os.getpid())

        self.assertIsInstance(started_at, float)
        self.assertLess(started_at, time.time())

    def test_start_time_is_stable(self):
        self.assertEqual(processes.read_start_time(os.getpid()), processes.read_start_time(os.getpid()))

    def test_ended_process_has_no_start_time(self):
        self.assertIsNone(processes.read_start_time(start_ended_process()))


class RunningTest(unittest.TestCase):
    def test_current_process_is_running(self):
        pid = os.getpid()

        self.assertTrue(processes.is_running(pid, processes.read_start_time(pid)))

    def test_reused_id_is_not_the_same_process(self):
        pid = os.getpid()

        self.assertFalse(processes.is_running(pid, processes.read_start_time(pid) - 3600))

    def test_ended_process_is_not_running(self):
        self.assertFalse(processes.is_running(start_ended_process(), time.time()))
