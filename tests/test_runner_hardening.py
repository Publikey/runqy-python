"""Tests for Phase 1 runner.py hardening fixes.

Covers:
  - _safe_write: normal output, non-serializable fallback, BrokenPipeError
  - run(): @load failure sends {"status":"error"}, invalid JSON input handling
  - run_once(): @load failure sends {"status":"error"}

Uses unittest + unittest.mock with io.StringIO for stdin/stdout redirection.
"""

import io
import json
import sys
import unittest
from unittest import mock

# We need to be able to reset the decorator global state between tests,
# so import the decorator module directly.
import runqy_python.decorator as decorator
import runqy_python.runner as runner


class SafeWriteTestCase(unittest.TestCase):
    """Tests for runner._safe_write."""

    def test_normal_dict_outputs_json(self):
        """_safe_write with a normal dict should write valid JSON + newline to stdout."""
        fake_stdout = io.StringIO()
        with mock.patch.object(sys, "stdout", fake_stdout):
            runner._safe_write({"task_id": "t1", "result": {"ok": True}, "error": None, "retry": False})

        output = fake_stdout.getvalue()
        # Should end with a newline
        self.assertTrue(output.endswith("\n"), "Output should end with a newline")

        # Should be valid JSON
        parsed = json.loads(output.strip())
        self.assertEqual(parsed["task_id"], "t1")
        self.assertEqual(parsed["result"], {"ok": True})
        self.assertIsNone(parsed["error"])
        self.assertFalse(parsed["retry"])

    def test_non_serializable_data_outputs_error_fallback(self):
        """_safe_write with non-serializable data (e.g., a set) should output
        a fallback error response instead of crashing."""
        fake_stdout = io.StringIO()
        non_serializable = {
            "task_id": "t-bad",
            "result": {"items": {1, 2, 3}},  # sets are not JSON-serializable
            "error": None,
            "retry": False,
        }
        with mock.patch.object(sys, "stdout", fake_stdout):
            # Should NOT raise
            runner._safe_write(non_serializable)

        output = fake_stdout.getvalue()
        parsed = json.loads(output.strip())

        # Fallback should contain the task_id from the original data
        self.assertEqual(parsed["task_id"], "t-bad")
        # result should be None in the fallback
        self.assertIsNone(parsed["result"])
        # error should mention "not JSON-serializable"
        self.assertIn("not JSON-serializable", parsed["error"])
        self.assertFalse(parsed["retry"])

    def test_non_serializable_without_task_id_uses_unknown(self):
        """_safe_write with non-serializable data and no task_id should default to 'unknown'."""
        fake_stdout = io.StringIO()
        # No task_id key at all
        non_serializable = {"result": object()}
        with mock.patch.object(sys, "stdout", fake_stdout):
            runner._safe_write(non_serializable)

        output = fake_stdout.getvalue()
        parsed = json.loads(output.strip())
        self.assertEqual(parsed["task_id"], "unknown")
        self.assertIn("not JSON-serializable", parsed["error"])

    def test_non_dict_non_serializable_uses_unknown(self):
        """_safe_write with a non-dict, non-serializable value should use 'unknown' task_id."""
        fake_stdout = io.StringIO()
        # Pass a non-dict that is also not serializable
        with mock.patch.object(sys, "stdout", fake_stdout):
            runner._safe_write(object())

        output = fake_stdout.getvalue()
        parsed = json.loads(output.strip())
        self.assertEqual(parsed["task_id"], "unknown")
        self.assertIn("not JSON-serializable", parsed["error"])

    def test_broken_pipe_exits_cleanly(self):
        """_safe_write should call sys.exit(1) on BrokenPipeError."""
        broken_stdout = mock.MagicMock()
        broken_stdout.write.side_effect = BrokenPipeError("pipe closed")
        with mock.patch.object(sys, "stdout", broken_stdout):
            with self.assertRaises(SystemExit) as ctx:
                runner._safe_write({"status": "ready"})
            self.assertEqual(ctx.exception.code, 1)


class RunLoadFailureTestCase(unittest.TestCase):
    """Tests for run() handling a failing @load function."""

    def setUp(self):
        # Reset global decorator state before each test
        decorator._registered_handler = None
        decorator._registered_loader = None
        # Reset shutdown flag
        runner._shutdown_requested = False

    def tearDown(self):
        decorator._registered_handler = None
        decorator._registered_loader = None
        runner._shutdown_requested = False

    def test_run_load_failure_sends_error_status(self):
        """run() should send {"status":"error"} and exit(1) when @load raises."""

        @decorator.task
        def my_handler(payload):
            return {"done": True}

        @decorator.load
        def my_loader():
            raise RuntimeError("model download failed")

        fake_stdout = io.StringIO()

        with mock.patch.object(sys, "stdout", fake_stdout), \
             mock.patch("runqy_python.runner.signal.signal"):
            with self.assertRaises(SystemExit) as ctx:
                runner.run()

            self.assertEqual(ctx.exception.code, 1)

        # Parse the output line
        output = fake_stdout.getvalue().strip()
        parsed = json.loads(output)

        self.assertEqual(parsed["status"], "error")
        self.assertIn("@load failed", parsed["error"])
        self.assertIn("model download failed", parsed["error"])

    def test_run_without_loader_sends_ready(self):
        """run() with no @load should send {"status":"ready"} and proceed normally."""

        @decorator.task
        def my_handler(payload):
            return {"echo": payload}

        task_input = json.dumps({"task_id": "t1", "payload": {"msg": "hello"}}) + "\n"
        fake_stdin = io.StringIO(task_input)
        fake_stdout = io.StringIO()

        with mock.patch.object(sys, "stdin", fake_stdin), \
             mock.patch.object(sys, "stdout", fake_stdout), \
             mock.patch("runqy_python.runner.signal.signal"):
            runner.run()

        lines = fake_stdout.getvalue().strip().split("\n")
        # First line: ready signal
        ready = json.loads(lines[0])
        self.assertEqual(ready["status"], "ready")

        # Second line: task response
        resp = json.loads(lines[1])
        self.assertEqual(resp["task_id"], "t1")
        self.assertEqual(resp["result"], {"echo": {"msg": "hello"}})
        self.assertIsNone(resp["error"])

    def test_run_no_handler_raises(self):
        """run() should raise RuntimeError if no @task handler is registered."""
        with mock.patch("runqy_python.runner.signal.signal"):
            with self.assertRaises(RuntimeError) as ctx:
                runner.run()
            self.assertIn("No task handler registered", str(ctx.exception))


class RunInvalidJsonTestCase(unittest.TestCase):
    """Tests for run() handling invalid JSON input."""

    def setUp(self):
        decorator._registered_handler = None
        decorator._registered_loader = None
        runner._shutdown_requested = False

    def tearDown(self):
        decorator._registered_handler = None
        decorator._registered_loader = None
        runner._shutdown_requested = False

    def test_invalid_json_sends_error_response(self):
        """run() should send an error response with 'Invalid JSON input' for malformed input."""

        @decorator.task
        def my_handler(payload):
            return {"done": True}

        # First line is invalid JSON, no more lines after
        fake_stdin = io.StringIO("this is not json\n")
        fake_stdout = io.StringIO()

        with mock.patch.object(sys, "stdin", fake_stdin), \
             mock.patch.object(sys, "stdout", fake_stdout), \
             mock.patch("runqy_python.runner.signal.signal"):
            runner.run()

        lines = fake_stdout.getvalue().strip().split("\n")
        # First line: ready signal
        ready = json.loads(lines[0])
        self.assertEqual(ready["status"], "ready")

        # Second line: error response for invalid JSON
        resp = json.loads(lines[1])
        self.assertEqual(resp["task_id"], "unknown")
        self.assertIsNone(resp["result"])
        self.assertIn("Invalid JSON input", resp["error"])
        self.assertFalse(resp["retry"])

    def test_invalid_json_does_not_crash_and_continues(self):
        """run() should handle invalid JSON and then continue processing valid tasks."""

        @decorator.task
        def my_handler(payload):
            return {"value": payload.get("x", 0) * 2}

        # First line is invalid, second is valid
        lines_in = "NOT_JSON\n" + json.dumps({"task_id": "t2", "payload": {"x": 5}}) + "\n"
        fake_stdin = io.StringIO(lines_in)
        fake_stdout = io.StringIO()

        with mock.patch.object(sys, "stdin", fake_stdin), \
             mock.patch.object(sys, "stdout", fake_stdout), \
             mock.patch("runqy_python.runner.signal.signal"):
            runner.run()

        lines = fake_stdout.getvalue().strip().split("\n")
        self.assertEqual(len(lines), 3)  # ready + error + success

        # Line 0: ready
        self.assertEqual(json.loads(lines[0])["status"], "ready")
        # Line 1: error for invalid JSON
        self.assertIn("Invalid JSON input", json.loads(lines[1])["error"])
        # Line 2: successful task response
        resp = json.loads(lines[2])
        self.assertEqual(resp["task_id"], "t2")
        self.assertEqual(resp["result"], {"value": 10})
        self.assertIsNone(resp["error"])

    def test_empty_lines_are_skipped(self):
        """run() should skip empty lines without producing output."""

        @decorator.task
        def my_handler(payload):
            return {"ok": True}

        # Only empty/whitespace lines, then a valid task
        lines_in = "\n   \n" + json.dumps({"task_id": "t3", "payload": {}}) + "\n"
        fake_stdin = io.StringIO(lines_in)
        fake_stdout = io.StringIO()

        with mock.patch.object(sys, "stdin", fake_stdin), \
             mock.patch.object(sys, "stdout", fake_stdout), \
             mock.patch("runqy_python.runner.signal.signal"):
            runner.run()

        lines = fake_stdout.getvalue().strip().split("\n")
        # Should only have ready + one task response (empty lines skipped)
        self.assertEqual(len(lines), 2)
        self.assertEqual(json.loads(lines[0])["status"], "ready")
        self.assertEqual(json.loads(lines[1])["task_id"], "t3")


class RunOnceLoadFailureTestCase(unittest.TestCase):
    """Tests for run_once() handling a failing @load function."""

    def setUp(self):
        decorator._registered_handler = None
        decorator._registered_loader = None
        runner._shutdown_requested = False

    def tearDown(self):
        decorator._registered_handler = None
        decorator._registered_loader = None
        runner._shutdown_requested = False

    def test_run_once_load_failure_sends_error_status(self):
        """run_once() should send {"status":"error"} and exit(1) when @load raises."""

        @decorator.task
        def my_handler(payload):
            return {"done": True}

        @decorator.load
        def my_loader():
            raise ValueError("bad config")

        fake_stdout = io.StringIO()

        with mock.patch.object(sys, "stdout", fake_stdout), \
             mock.patch("runqy_python.runner.signal.signal"):
            with self.assertRaises(SystemExit) as ctx:
                runner.run_once()

            self.assertEqual(ctx.exception.code, 1)

        output = fake_stdout.getvalue().strip()
        parsed = json.loads(output)

        self.assertEqual(parsed["status"], "error")
        self.assertIn("@load failed", parsed["error"])
        self.assertIn("bad config", parsed["error"])

    def test_run_once_processes_single_task(self):
        """run_once() should process exactly one task and return."""

        @decorator.task
        def my_handler(payload):
            return {"doubled": payload.get("n", 0) * 2}

        task_input = json.dumps({"task_id": "once-1", "payload": {"n": 7}}) + "\n"
        fake_stdin = io.StringIO(task_input)
        fake_stdout = io.StringIO()

        with mock.patch.object(sys, "stdin", fake_stdin), \
             mock.patch.object(sys, "stdout", fake_stdout), \
             mock.patch("runqy_python.runner.signal.signal"):
            runner.run_once()

        lines = fake_stdout.getvalue().strip().split("\n")
        self.assertEqual(len(lines), 2)  # ready + response

        ready = json.loads(lines[0])
        self.assertEqual(ready["status"], "ready")

        resp = json.loads(lines[1])
        self.assertEqual(resp["task_id"], "once-1")
        self.assertEqual(resp["result"], {"doubled": 14})
        self.assertIsNone(resp["error"])

    def test_run_once_invalid_json_sends_error(self):
        """run_once() should handle invalid JSON input gracefully."""

        @decorator.task
        def my_handler(payload):
            return {"ok": True}

        fake_stdin = io.StringIO("{broken json\n")
        fake_stdout = io.StringIO()

        with mock.patch.object(sys, "stdin", fake_stdin), \
             mock.patch.object(sys, "stdout", fake_stdout), \
             mock.patch("runqy_python.runner.signal.signal"):
            runner.run_once()

        lines = fake_stdout.getvalue().strip().split("\n")
        self.assertEqual(len(lines), 2)  # ready + error

        ready = json.loads(lines[0])
        self.assertEqual(ready["status"], "ready")

        resp = json.loads(lines[1])
        self.assertEqual(resp["task_id"], "unknown")
        self.assertIn("Invalid JSON input", resp["error"])
        self.assertFalse(resp["retry"])

    def test_run_once_no_handler_raises(self):
        """run_once() should raise RuntimeError if no @task handler is registered."""
        with mock.patch("runqy_python.runner.signal.signal"):
            with self.assertRaises(RuntimeError) as ctx:
                runner.run_once()
            self.assertIn("No task handler registered", str(ctx.exception))

    def test_run_once_empty_input_returns_without_error(self):
        """run_once() should return cleanly when stdin is empty (no task to process)."""

        @decorator.task
        def my_handler(payload):
            return {"ok": True}

        fake_stdin = io.StringIO("")
        fake_stdout = io.StringIO()

        with mock.patch.object(sys, "stdin", fake_stdin), \
             mock.patch.object(sys, "stdout", fake_stdout), \
             mock.patch("runqy_python.runner.signal.signal"):
            # Should not raise
            runner.run_once()

        lines = fake_stdout.getvalue().strip().split("\n")
        # Only the ready signal, no task response
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])["status"], "ready")


class ShutdownHandlerTestCase(unittest.TestCase):
    """Tests for _shutdown_handler."""

    def setUp(self):
        runner._shutdown_requested = False

    def tearDown(self):
        runner._shutdown_requested = False

    def test_shutdown_handler_sets_flag_and_exits(self):
        """_shutdown_handler should set _shutdown_requested and call sys.exit(0)."""
        with self.assertRaises(SystemExit) as ctx:
            runner._shutdown_handler(15, None)  # SIGTERM = 15

        self.assertEqual(ctx.exception.code, 0)
        self.assertTrue(runner._shutdown_requested)


if __name__ == "__main__":
    unittest.main()
