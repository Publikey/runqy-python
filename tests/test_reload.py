"""Tests for the @reload decorator and the config_reload control action."""

import io
import json
import sys
import unittest
from unittest import mock

import runqy_python.decorator as decorator
import runqy_python.runner as runner


def run_with_input(lines):
    """Run runner.run() on the given stdin lines; return the parsed stdout lines."""
    fake_stdin = io.StringIO("".join(json.dumps(l) + "\n" for l in lines))
    fake_stdout = io.StringIO()
    with mock.patch.object(sys, "stdin", fake_stdin), \
         mock.patch.object(sys, "stdout", fake_stdout), \
         mock.patch("runqy_python.runner._protect_stdout"), \
         mock.patch("runqy_python.runner.signal.signal"):
        runner.run()
    return [json.loads(l) for l in fake_stdout.getvalue().splitlines() if l.strip()]


class ReloadTestCase(unittest.TestCase):
    def setUp(self):
        decorator._reset()
        runner._shutdown_requested = False
        runner._protocol_stdout = None

    def tearDown(self):
        decorator._reset()
        runner._shutdown_requested = False
        runner._protocol_stdout = None

    def test_ready_signal_announces_reload(self):
        @decorator.task
        def handler(payload):
            return {}

        out = run_with_input([])
        self.assertEqual(out[0], {"status": "ready"})

        decorator._reset()

        @decorator.task
        def handler2(payload):
            return {}

        @decorator.reload
        def refresh(ctx):
            return None

        out = run_with_input([])
        self.assertEqual(out[0], {"status": "ready", "capabilities": ["reload"]})

    def test_reload_replaces_context_between_tasks(self):
        @decorator.load
        def setup():
            return {"version": 1}

        @decorator.task
        def handler(payload, ctx):
            return {"version": ctx["version"]}

        @decorator.reload
        def refresh(ctx):
            return {"version": ctx["version"] + 1}

        out = run_with_input([
            {"task_id": "t1", "payload": {}},
            {"task_id": "control-1", "control": "reload"},
            {"task_id": "t2", "payload": {}},
        ])
        self.assertEqual(out[1]["result"], {"version": 1})
        self.assertEqual(out[2], {"task_id": "control-1", "result": {"reloaded": True}, "error": None, "retry": False})
        self.assertEqual(out[3]["result"], {"version": 2})

    def test_reload_failure_keeps_context(self):
        @decorator.load
        def setup():
            return {"version": 1}

        @decorator.task
        def handler(payload, ctx):
            return {"version": ctx["version"]}

        @decorator.reload
        def refresh(ctx):
            raise RuntimeError("models.yml unreachable")

        out = run_with_input([
            {"task_id": "control-1", "control": "reload"},
            {"task_id": "t1", "payload": {}},
        ])
        self.assertIn("models.yml unreachable", out[1]["error"])
        self.assertEqual(out[2]["result"], {"version": 1})

    def test_reload_without_load_keeps_single_argument_handler(self):
        calls = []

        @decorator.task
        def handler(payload):
            return {"ok": True}

        @decorator.reload
        def refresh(ctx):
            calls.append(ctx)
            return {"ignored": True}

        out = run_with_input([
            {"task_id": "control-1", "control": "reload"},
            {"task_id": "t1", "payload": {}},
        ])
        self.assertEqual(calls, [None])
        self.assertEqual(out[2]["result"], {"ok": True})

    def test_unknown_control_action_is_an_error(self):
        @decorator.task
        def handler(payload):
            return {}

        out = run_with_input([{"task_id": "control-1", "control": "reload"}])
        self.assertIn("unsupported control action", out[1]["error"])

    def test_reload_registered_once(self):
        @decorator.reload
        def a(ctx):
            return None

        with self.assertRaises(RuntimeError):
            @decorator.reload
            def b(ctx):
                return None


if __name__ == "__main__":
    unittest.main()
