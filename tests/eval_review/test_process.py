import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "SHARED" / "runtime"))

from hb_eval_review import process
from hb_eval_review.process import run_isolated_process, run_read_only_process
from hb_eval_review.snapshot import compute_source_snapshot


class ProcessTests(unittest.TestCase):
    def test_success_captures_output(self):
        with tempfile.TemporaryDirectory() as td:
            result = run_read_only_process(
                [sys.executable, "-c", "print('OK')"], Path(td), timeout_seconds=2
            )
        self.assertEqual("PASS", result["status"])
        self.assertEqual("OK", result["stdout"].strip())

    def test_timeout_is_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            result = run_read_only_process(
                [sys.executable, "-c", "import time; time.sleep(2)"], Path(td), timeout_seconds=0.05
            )
        self.assertEqual("BLOCKED", result["status"])
        self.assertEqual("PROCESS_TIMEOUT", result["error_code"])

    def test_nonzero_is_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            result = run_read_only_process(
                [sys.executable, "-c", "raise SystemExit(7)"], Path(td), timeout_seconds=2
            )
        self.assertEqual("BLOCKED", result["status"])
        self.assertEqual("PROCESS_NONZERO", result["error_code"])

    def test_raw_stdout_is_returned_and_diagnostics_are_redacted(self):
        script = (
            "import json;"
            "print(json.dumps({'structured_output':{'summary':'found password=hunter2'}}))"
        )
        with tempfile.TemporaryDirectory() as td:
            result = run_read_only_process(
                [sys.executable, "-c", script], Path(td), timeout_seconds=5
            )
        self.assertEqual("PASS", result["status"])
        parsed = json.loads(result["stdout"])
        self.assertEqual("found password=hunter2", parsed["structured_output"]["summary"])
        self.assertNotIn("hunter2", result["diagnostics"]["stdout_tail"])
        self.assertIn("[REDACTED]", result["diagnostics"]["stdout_tail"])

    def test_unrelated_secret_environment_is_not_inherited(self):
        old = os.environ.get("DATABASE_PASSWORD")
        os.environ["DATABASE_PASSWORD"] = "must-not-leak"
        try:
            with tempfile.TemporaryDirectory() as td:
                result = run_read_only_process(
                    [sys.executable, "-c", "import os; print(os.getenv('DATABASE_PASSWORD','ABSENT'))"],
                    Path(td), timeout_seconds=2
                )
            self.assertEqual("ABSENT", result["stdout"].strip())
        finally:
            if old is None:
                os.environ.pop("DATABASE_PASSWORD", None)
            else:
                os.environ["DATABASE_PASSWORD"] = old


PACKET = {"packet_id": "p1", "source_snapshot_id": "s1", "evidence_bundle_id": "e1"}


class DescendantReapTests(unittest.TestCase):
    """A provider that exits cleanly must not leave a worker writing after sealing."""

    def spawn_background_writer(self, base, detach=""):
        """A child that exits 0 after a background worker has published its own pid."""
        pid_file = base / "worker.pid"
        late = base / "late.txt"
        # stdio is detached so the worker does not hold the parent's pipes open;
        # that is what makes the child able to exit 0 while the worker keeps running.
        script = (
            '{detach}sh -c \'echo $$ > "{pid}"; sleep 30; echo LATE > "{late}"\''
            ' >/dev/null 2>&1 </dev/null &\n'
            'until [ -s "{pid}" ]; do :; done\n'
            'exit 0\n'
        ).format(detach=detach, pid=pid_file, late=late)
        result = run_read_only_process(["/bin/sh", "-c", script], base, timeout_seconds=15)
        return result, int(pid_file.read_text().strip()), late

    def assert_gone(self, pid):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.02)
        self.fail("descendant {} was still alive after the stage returned".format(pid))

    def test_a_background_worker_is_reaped_on_a_normal_exit(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            result, pid, late = self.spawn_background_writer(base)
            self.assertEqual("PASS", result["status"])
            self.assert_gone(pid)
            self.assertFalse(late.exists())

    def test_the_reap_reports_that_no_descendant_survived(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            result, _pid, _late = self.spawn_background_writer(base)
        self.assertFalse(result["descendants_alive"])

    def test_containment_is_declared_as_process_group_only(self):
        # Honest scope: macOS has no cgroup, so a descendant that leaves the group
        # with setsid is out of reach. The runtime says so instead of claiming more.
        with tempfile.TemporaryDirectory() as td:
            result = run_read_only_process(
                [sys.executable, "-c", "print('OK')"], Path(td), timeout_seconds=5
            )
        self.assertEqual("process-group-only", result["descendant_containment"])
        self.assertEqual("process-group-only", process.DESCENDANT_CONTAINMENT)


@unittest.skipUnless(sys.platform == "darwin" and Path("/usr/bin/sandbox-exec").exists(), "macOS sandbox required")
class DescendantEnvelopeTests(unittest.TestCase):
    def test_a_surviving_descendant_blocks_the_envelope(self):
        stub = {
            "status": "PASS", "error_code": None, "exit_code": 0,
            "stdout": "{}", "stderr": "", "diagnostics": {},
            "descendants_alive": True,
            "descendant_containment": process.DESCENDANT_CONTAINMENT,
        }
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            (base / "repository").mkdir()
            with patch.object(process, "run_read_only_process", lambda *a, **k: dict(stub)):
                result = run_isolated_process(
                    ["/bin/echo", "x"], base / "repository", base / "out",
                    PACKET, "evaluate", "claude", 5, {},
                )
        self.assertEqual("BLOCKED", result["envelope"]["status"])
        self.assertEqual("PROVIDER_DESCENDANTS_ALIVE", result["envelope"]["error_code"])


class OutputFailureContainmentTests(unittest.TestCase):
    """commands/evaluate.md: normal exit, timeout, or exception — the group is reaped.

    The promise is unconditional, so these fixtures make the collection itself fail and
    then ask whether the in-group worker is still alive.
    """

    def child_with_worker(self, base, tail):
        """A child that publishes an in-group worker's pid, then runs `tail`.

        The worker detaches its own stdio, so it never holds the parent's pipes: the
        child can exit while the worker keeps running, which is the whole point.
        """
        pid_file = base / "worker.pid"
        late = base / "late.txt"
        script = (
            'sh -c \'echo $$ > "{pid}"; sleep 30; echo LATE > "{late}"\''
            ' >/dev/null 2>&1 </dev/null &\n'
            'until [ -s "{pid}" ]; do :; done\n'
            '{tail}\n'
        ).format(pid=pid_file, late=late, tail=tail)
        return ["/bin/sh", "-c", script], pid_file, late

    def assert_gone(self, pid):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.02)
        os.kill(pid, signal.SIGKILL)
        self.fail("descendant {} was still alive after the stage returned".format(pid))

    def test_non_utf8_child_output_is_a_blocked_result_not_a_traceback(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            command, _pid_file, _late = self.child_with_worker(
                base, "printf '\\377\\376'; exit 0"
            )
            result = run_read_only_process(command, base, timeout_seconds=15)
        self.assertEqual("BLOCKED", result["status"])
        self.assertEqual("PROCESS_OUTPUT_UNDECODABLE", result["error_code"])

    def test_an_in_group_worker_is_reaped_when_the_output_cannot_be_decoded(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            command, pid_file, late = self.child_with_worker(
                base, "printf '\\377\\376'; exit 0"
            )
            run_read_only_process(command, base, timeout_seconds=15)
            worker = int(pid_file.read_text().strip())
            self.assert_gone(worker)
            self.assertFalse(late.exists())

    def test_undecodable_output_is_still_reported_with_replacement_characters(self):
        with tempfile.TemporaryDirectory() as td:
            result = run_read_only_process(
                ["/bin/sh", "-c", "printf 'head\\377tail'; exit 0"], Path(td), timeout_seconds=10
            )
        self.assertIn("head", result["diagnostics"]["stdout_tail"])
        self.assertIn("tail", result["diagnostics"]["stdout_tail"])
        self.assertIn("\ufffd", result["stdout"])

    def test_an_in_group_worker_is_reaped_when_collecting_the_output_raises(self):
        state = []

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            command, pid_file, late = self.child_with_worker(base, "sleep 20")

            def failing(_self_process, *_args, **_kwargs):
                # Barrier, not a sleep: the worker is provably running before the
                # collection is made to fail, so the reap has something to catch.
                deadline = time.monotonic() + 10
                while not (pid_file.exists() and pid_file.read_text().strip()):
                    if time.monotonic() >= deadline:
                        self.fail("the in-group worker never published its pid")
                    time.sleep(0.01)
                state.append(True)
                raise OSError(5, "Input/output error")

            with patch.object(subprocess.Popen, "communicate", failing):
                result = run_read_only_process(command, base, timeout_seconds=15)
            worker = int(pid_file.read_text().strip())
            self.assertTrue(state)
            self.assertEqual("BLOCKED", result["status"])
            self.assertEqual("PROCESS_OUTPUT_UNAVAILABLE", result["error_code"])
            self.assert_gone(worker)
            self.assertFalse(late.exists())

    def test_the_group_is_reaped_even_when_the_result_is_never_assembled(self):
        # The promise is about *every* path, so this one fails past the point where
        # `_collect_output` turns a failure into a result: the exception is allowed to
        # propagate, and the worker still has to be gone when it does.
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            command, pid_file, late = self.child_with_worker(base, "exit 0")

            def explode(_raw):
                raise MemoryError("no room to decode")

            with patch.object(process, "_decode_stream", explode):
                with self.assertRaises(MemoryError):
                    run_read_only_process(command, base, timeout_seconds=15)
            worker = int(pid_file.read_text().strip())
            self.assert_gone(worker)
            self.assertFalse(late.exists())

    def test_a_collection_failure_still_collects_the_child_itself(self):
        instances = []
        real_init = subprocess.Popen.__init__

        def capture(self_process, *args, **kwargs):
            real_init(self_process, *args, **kwargs)
            instances.append(self_process)

        def failing(_self_process, *_args, **_kwargs):
            raise OSError(5, "Input/output error")

        with tempfile.TemporaryDirectory() as td:
            with patch.object(subprocess.Popen, "__init__", capture), patch.object(
                subprocess.Popen, "communicate", failing
            ):
                run_read_only_process(
                    [sys.executable, "-c", "pass"], Path(td), timeout_seconds=5
                )
        # returncode is set only by a wait the parent actually made: on the failure path
        # the child would otherwise be left for the interpreter to reap whenever.
        self.assertEqual(1, len(instances))
        self.assertIsNotNone(instances[0].returncode)

    def test_a_collection_failure_keeps_only_the_exception_class_name(self):
        def failing(self_process, *args, **kwargs):
            raise OSError(5, "secret-bearing detail hunter2")

        with tempfile.TemporaryDirectory() as td:
            with patch.object(subprocess.Popen, "communicate", failing):
                result = run_read_only_process(
                    [sys.executable, "-c", "pass"], Path(td), timeout_seconds=5
                )
        self.assertEqual(["COLLECT_OSERROR"], result["signal_errors"])
        self.assertNotIn("hunter2", json.dumps(result, ensure_ascii=False))


class TimeoutSignalGuardTests(unittest.TestCase):
    """security F4: a kernel that refuses the group signal is a fact, not a traceback."""

    def owned_children(self):
        """Capture every child this test starts and take responsibility for it.

        A fixture that makes the kernel refuse *every* signal strands a real process
        group on purpose: the runtime has no way left to reach it, which is the whole
        point of the case. So the test owns it. Only the group this test created is
        signalled — never a pattern match over the machine's processes — and the leader
        is waited on, so no zombie and no ResourceWarning outlives the test.

        The child is started with start_new_session=True, so its pid is its own group
        id and `sh` plus anything it forked go down together. Killing the recorded `$$`
        alone would leave `sleep` behind, reparented to init.
        """
        instances = []
        real_init = subprocess.Popen.__init__

        def capture(self_process, *args, **kwargs):
            real_init(self_process, *args, **kwargs)
            instances.append(self_process)

        def release():
            for popen in instances:
                if popen.pid <= 1 or popen.pid == os.getpgid(0):
                    continue
                try:
                    os.killpg(popen.pid, signal.SIGKILL)
                except OSError:
                    pass
                try:
                    popen.wait(timeout=5)
                except (subprocess.TimeoutExpired, OSError):
                    pass

        # Registered before the patch is entered, so it runs after every signal patch
        # this test installed has already been restored.
        self.addCleanup(release)
        return patch.object(subprocess.Popen, "__init__", capture), instances

    def test_a_refused_group_signal_is_recorded_rather_than_raised(self):
        cases = {
            "permission": (PermissionError(1, "Operation not permitted"), "KILLPG_PERMISSIONERROR"),
            "lookup": (ProcessLookupError(3, "No such process"), "KILLPG_PROCESSLOOKUPERROR"),
            "other": (OSError(22, "Invalid argument"), "KILLPG_OSERROR"),
        }
        for name, (error, code) in cases.items():
            with self.subTest(case=name):
                errors = []

                def refuse(_pgid, _number):
                    raise error

                with patch.object(process.os, "killpg", refuse):
                    process._signal_group(4242, signal.SIGTERM, errors)
                self.assertEqual([code], errors)

    def test_a_timeout_whose_group_signal_is_refused_still_yields_a_timeout_envelope(self):
        def refuse(_pgid, _number):
            raise PermissionError(1, "Operation not permitted")

        capture, children = self.owned_children()
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            started = time.monotonic()
            with capture, patch.object(process.os, "killpg", refuse):
                # Two commands, so the shell forks `sleep` instead of exec-ing it:
                # the stranded group has a second member, and only a group-wide
                # cleanup reaches it.
                result = run_read_only_process(
                    ["/bin/sh", "-c", "true; sleep 30"], base, timeout_seconds=0.5
                )
            elapsed = time.monotonic() - started
        self.assertEqual("BLOCKED", result["status"])
        self.assertEqual("PROCESS_TIMEOUT", result["error_code"])
        self.assertIn("KILLPG_PERMISSIONERROR", result["signal_errors"])
        self.assertLess(elapsed, 15)
        self.assertEqual(1, len(children))

    def test_a_drain_that_raises_still_yields_a_timeout_envelope(self):
        # An exception raised inside the TimeoutExpired handler is not caught by the
        # handler beside it, so the drain carries its own guard.
        def explode(*_args, **_kwargs):
            raise OSError(5, "Input/output error")

        with tempfile.TemporaryDirectory() as td:
            with patch.object(process, "_drain_after_timeout", explode):
                result = run_read_only_process(
                    [sys.executable, "-c", "import time; time.sleep(30)"],
                    Path(td), timeout_seconds=0.2,
                )
        self.assertEqual("BLOCKED", result["status"])
        self.assertEqual("PROCESS_TIMEOUT", result["error_code"])
        self.assertEqual(["DRAIN_OSERROR"], result["signal_errors"])

    def test_a_pipe_held_past_the_kill_budget_bounds_the_timeout_path(self):
        recorded = []

        def unsent(pgid, number, errors):
            recorded.append(number)

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            started = time.monotonic()
            with patch.object(process, "_signal_group", unsent):
                result = run_read_only_process(
                    ["/bin/sh", "-c", "sleep 30"], base, timeout_seconds=0.5
                )
            elapsed = time.monotonic() - started
        self.assertEqual([signal.SIGTERM, signal.SIGKILL], recorded)
        self.assertEqual("BLOCKED", result["status"])
        self.assertEqual("PROCESS_TIMEOUT", result["error_code"])
        self.assertIn("OUTPUT_NOT_DRAINED", result["signal_errors"])
        self.assertLess(elapsed, 15)


if __name__ == "__main__":
    unittest.main()
