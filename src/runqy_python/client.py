"""Client for enqueuing tasks to runqy server."""

import json
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Any, Dict, Optional


class RunqyError(Exception):
    """Base exception for runqy client errors."""
    pass


class AuthenticationError(RunqyError):
    """Raised when API key is invalid or missing."""
    pass


class TaskNotFoundError(RunqyError):
    """Raised when a task is not found."""
    pass


@dataclass
class TaskInfo:
    """Task information returned from server.

    Attributes:
        task_id: Unique identifier for the task
        queue: Queue name the task was submitted to
        state: Task state (pending, active, completed, etc.)
        result: Task result data (if completed)
        error: Error message (if failed)
        payload: Original task payload
    """
    task_id: str
    queue: str
    state: str
    result: Optional[Any] = None
    error: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None


class RunqyClient:
    """Client for interacting with runqy server.

    Example:
        client = RunqyClient("http://localhost:3000", api_key="your-api-key")

        # Enqueue a task
        task = client.enqueue("inference_default", {"input": "hello"})
        print(f"Task ID: {task.task_id}")

        # Check result
        result = client.get_task(task.task_id)
        print(f"State: {result.state}, Result: {result.result}")
    """

    def __init__(self, server_url: str, api_key: str, timeout: int = 30):
        """Initialize the client.

        Args:
            server_url: Base URL of the runqy server (e.g., "http://localhost:3000")
            api_key: API key for authentication
            timeout: Default request timeout in seconds
        """
        self.server_url = server_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def _request(
        self,
        method: str,
        path: str,
        data: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """Make an HTTP request to the server.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: API path (e.g., "/queue/add")
            data: Request body data (for POST)
            timeout: Request timeout in seconds

        Returns:
            Parsed JSON response

        Raises:
            AuthenticationError: If API key is invalid
            RunqyError: For other HTTP errors
        """
        url = f"{self.server_url}{path}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        body = None
        if data is not None:
            body = json.dumps(data).encode("utf-8")

        req = urllib.request.Request(url, data=body, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
                response_data = resp.read().decode("utf-8")
                return json.loads(response_data) if response_data else {}
        except urllib.error.HTTPError as e:
            response_body = e.read().decode("utf-8") if e.fp else ""

            if e.code == 401:
                raise AuthenticationError(f"Authentication failed: {response_body}")
            elif e.code == 404:
                raise TaskNotFoundError(f"Task not found: {response_body}")
            else:
                raise RunqyError(f"HTTP {e.code}: {response_body}")
        except urllib.error.URLError as e:
            raise RunqyError(f"Connection error: {e.reason}")

    def enqueue(
        self,
        queue: str,
        payload: Dict[str, Any],
        timeout: int = 300
    ) -> TaskInfo:
        """Enqueue a task to a queue.

        Args:
            queue: Queue name (e.g., "inference_default")
            payload: Task payload data
            timeout: Task execution timeout in seconds (default: 300)

        Returns:
            TaskInfo with task_id and initial state

        Raises:
            AuthenticationError: If API key is invalid
            RunqyError: For other errors

        Example:
            task = client.enqueue("inference_default", {"input": "hello"})
            print(f"Enqueued task: {task.task_id}")
        """
        data = {
            "queue": queue,
            "timeout": timeout,
            "data": payload,
        }

        response = self._request("POST", "/queue/add", data)

        info = response.get("info", {})
        return TaskInfo(
            task_id=info.get("id", ""),
            queue=info.get("queue", queue),
            state=info.get("state", "pending"),
            payload=payload,
        )

    def get_task(self, task_id: str) -> TaskInfo:
        """Get task status and result.

        Args:
            task_id: Task ID returned from enqueue()

        Returns:
            TaskInfo with current state and result (if completed)

        Raises:
            TaskNotFoundError: If task doesn't exist
            RunqyError: For other errors

        Example:
            result = client.get_task(task.task_id)
            if result.state == "completed":
                print(f"Result: {result.result}")
        """
        response = self._request("GET", f"/queue/{task_id}")

        info = response.get("Info", response.get("info", {}))

        # Parse result if it's a string (JSON)
        result = info.get("Result", info.get("result"))
        if isinstance(result, str) and result:
            try:
                result = json.loads(result)
            except json.JSONDecodeError:
                pass  # Keep as string if not valid JSON

        # Parse payload if it's a string (JSON)
        payload = info.get("Payload", info.get("payload"))
        if isinstance(payload, str) and payload:
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                pass  # Keep as string if not valid JSON

        return TaskInfo(
            task_id=info.get("ID", info.get("id", task_id)),
            queue=info.get("Queue", info.get("queue", "")),
            state=info.get("State", info.get("state", "")),
            result=result,
            error=info.get("LastErr", info.get("last_err")),
            payload=payload,
        )


def enqueue(
    queue: str,
    payload: Dict[str, Any],
    server_url: str,
    api_key: str,
    timeout: int = 300
) -> TaskInfo:
    """Quick enqueue without creating a client instance.

    Args:
        queue: Queue name (e.g., "inference_default")
        payload: Task payload data
        server_url: Base URL of the runqy server
        api_key: API key for authentication
        timeout: Task execution timeout in seconds (default: 300)

    Returns:
        TaskInfo with task_id and initial state

    Example:
        from runqy_python import enqueue

        task = enqueue(
            "inference_default",
            {"input": "hello"},
            server_url="http://localhost:3000",
            api_key="your-api-key"
        )
        print(f"Task ID: {task.task_id}")
    """
    return RunqyClient(server_url, api_key).enqueue(queue, payload, timeout)
