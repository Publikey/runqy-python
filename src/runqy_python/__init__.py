"""runqy-python: Python SDK for runqy - write distributed task handlers with simple decorators."""

# Task execution (for workers)
from .decorator import task, load, RetryableError
from .runner import run, run_once

# Client (for enqueuing tasks)
from .client import (
    RunqyClient,
    TaskInfo,
    BatchResult,
    RunqyError,
    AuthenticationError,
    TaskNotFoundError,
    enqueue,
    enqueue_batch,
)

__all__ = [
    # Task execution
    "task",
    "load",
    "RetryableError",
    "run",
    "run_once",
    # Client
    "RunqyClient",
    "TaskInfo",
    "BatchResult",
    "RunqyError",
    "AuthenticationError",
    "TaskNotFoundError",
    "enqueue",
    "enqueue_batch",
]

__version__ = "0.2.0"
