"""Tests for RunqyClient."""

import json
import unittest
from unittest import mock
from urllib.error import HTTPError

from runqy_python.client import (
    AuthenticationError,
    BatchResult,
    RunqyClient,
    RunqyError,
    TaskInfo,
    TaskNotFoundError,
)


class TestRunqyClientInit(unittest.TestCase):
    def test_stores_url_and_key(self):
        client = RunqyClient("http://localhost:3000", api_key="my-key")
        self.assertEqual(client.server_url, "http://localhost:3000")
        self.assertEqual(client.api_key, "my-key")
        self.assertEqual(client.timeout, 30)

    def test_strips_trailing_slash(self):
        client = RunqyClient("http://localhost:3000/", api_key="key")
        self.assertEqual(client.server_url, "http://localhost:3000")

    def test_custom_timeout(self):
        client = RunqyClient("http://localhost:3000", api_key="key", timeout=60)
        self.assertEqual(client.timeout, 60)


class TestRunqyClientEnqueue(unittest.TestCase):
    def setUp(self):
        self.client = RunqyClient("http://localhost:3000", api_key="test-key")

    @mock.patch("runqy_python.client.urllib.request.urlopen")
    def test_enqueue_success(self, mock_urlopen):
        response_data = json.dumps({
            "info": {
                "id": "task-123",
                "queue": "inference.default",
                "state": "pending",
            }
        }).encode("utf-8")

        mock_response = mock.MagicMock()
        mock_response.read.return_value = response_data
        mock_response.__enter__ = mock.MagicMock(return_value=mock_response)
        mock_response.__exit__ = mock.MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = self.client.enqueue("inference.default", {"msg": "hello"})

        self.assertIsInstance(result, TaskInfo)
        self.assertEqual(result.task_id, "task-123")
        self.assertEqual(result.queue, "inference.default")
        self.assertEqual(result.state, "pending")

        # Verify the request was made correctly
        call_args = mock_urlopen.call_args
        req = call_args[0][0]
        self.assertTrue(req.full_url.endswith("/queue/add"))
        self.assertEqual(req.get_header("Authorization"), "Bearer test-key")
        self.assertEqual(req.get_header("Content-type"), "application/json")

        body = json.loads(req.data.decode("utf-8"))
        self.assertEqual(body["queue"], "inference.default")
        self.assertEqual(body["data"], {"msg": "hello"})
        self.assertEqual(body["timeout"], 300)

    @mock.patch("runqy_python.client.urllib.request.urlopen")
    def test_enqueue_auth_error(self, mock_urlopen):
        mock_urlopen.side_effect = HTTPError(
            url="http://localhost:3000/queue/add",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=mock.MagicMock(read=mock.MagicMock(return_value=b"invalid api key")),
        )

        with self.assertRaises(AuthenticationError):
            self.client.enqueue("inference.default", {"msg": "hello"})

    @mock.patch("runqy_python.client.urllib.request.urlopen")
    def test_enqueue_server_error(self, mock_urlopen):
        mock_urlopen.side_effect = HTTPError(
            url="http://localhost:3000/queue/add",
            code=500,
            msg="Internal Server Error",
            hdrs=None,
            fp=mock.MagicMock(read=mock.MagicMock(return_value=b"internal error")),
        )

        with self.assertRaises(RunqyError):
            self.client.enqueue("inference.default", {"msg": "hello"})

    @mock.patch("runqy_python.client.urllib.request.urlopen")
    def test_enqueue_not_found(self, mock_urlopen):
        mock_urlopen.side_effect = HTTPError(
            url="http://localhost:3000/queue/add",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=mock.MagicMock(read=mock.MagicMock(return_value=b"queue not found")),
        )

        with self.assertRaises(TaskNotFoundError):
            self.client.enqueue("nonexistent", {"msg": "hello"})


class TestRunqyClientEnqueueBatch(unittest.TestCase):
    def setUp(self):
        self.client = RunqyClient("http://localhost:3000", api_key="test-key")

    @mock.patch("runqy_python.client.urllib.request.urlopen")
    def test_enqueue_batch_success(self, mock_urlopen):
        response_data = json.dumps({
            "enqueued": 2,
            "failed": 0,
            "task_ids": ["t1", "t2"],
            "errors": [],
        }).encode("utf-8")

        mock_response = mock.MagicMock()
        mock_response.read.return_value = response_data
        mock_response.__enter__ = mock.MagicMock(return_value=mock_response)
        mock_response.__exit__ = mock.MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = self.client.enqueue_batch(
            "inference.default",
            [{"input": "a"}, {"input": "b"}],
        )

        self.assertIsInstance(result, BatchResult)
        self.assertEqual(result.enqueued, 2)
        self.assertEqual(result.failed, 0)
        self.assertEqual(result.task_ids, ["t1", "t2"])
        self.assertEqual(result.errors, [])

        # Verify request body structure
        call_args = mock_urlopen.call_args
        req = call_args[0][0]
        body = json.loads(req.data.decode("utf-8"))
        self.assertEqual(body["queue"], "inference.default")
        self.assertEqual(len(body["jobs"]), 2)
        self.assertEqual(body["jobs"][0]["data"], {"input": "a"})


class TestRunqyClientGetTask(unittest.TestCase):
    def setUp(self):
        self.client = RunqyClient("http://localhost:3000", api_key="test-key")

    @mock.patch("runqy_python.client.urllib.request.urlopen")
    def test_get_task_completed(self, mock_urlopen):
        response_data = json.dumps({
            "info": {
                "id": "task-456",
                "queue": "inference.default",
                "state": "completed",
                "result": json.dumps({"output": "done"}),
                "payload": json.dumps({"input": "test"}),
            }
        }).encode("utf-8")

        mock_response = mock.MagicMock()
        mock_response.read.return_value = response_data
        mock_response.__enter__ = mock.MagicMock(return_value=mock_response)
        mock_response.__exit__ = mock.MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = self.client.get_task("task-456")

        self.assertEqual(result.task_id, "task-456")
        self.assertEqual(result.state, "completed")
        self.assertEqual(result.result, {"output": "done"})
        self.assertEqual(result.payload, {"input": "test"})

    @mock.patch("runqy_python.client.urllib.request.urlopen")
    def test_get_task_not_found(self, mock_urlopen):
        mock_urlopen.side_effect = HTTPError(
            url="http://localhost:3000/queue/task-999",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=mock.MagicMock(read=mock.MagicMock(return_value=b"not found")),
        )

        with self.assertRaises(TaskNotFoundError):
            self.client.get_task("task-999")


class TestModuleLevelFunctions(unittest.TestCase):
    @mock.patch("runqy_python.client.urllib.request.urlopen")
    def test_module_enqueue(self, mock_urlopen):
        from runqy_python.client import enqueue

        response_data = json.dumps({
            "info": {"id": "t1", "queue": "q", "state": "pending"}
        }).encode("utf-8")

        mock_response = mock.MagicMock()
        mock_response.read.return_value = response_data
        mock_response.__enter__ = mock.MagicMock(return_value=mock_response)
        mock_response.__exit__ = mock.MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = enqueue(
            "q", {"key": "val"},
            server_url="http://localhost:3000",
            api_key="key",
        )
        self.assertIsInstance(result, TaskInfo)
        self.assertEqual(result.task_id, "t1")


if __name__ == "__main__":
    unittest.main()
