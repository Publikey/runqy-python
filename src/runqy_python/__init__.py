"""runqy-python: Python SDK for runqy - write distributed task handlers with simple decorators."""

# Task execution (for workers)
from .decorator import task, load
from .runner import run, run_once

# Client (for enqueuing tasks)
from .client import (
    RunqyClient,
    TaskInfo,
    RunqyError,
    AuthenticationError,
    TaskNotFoundError,
    enqueue,
)

__all__ = [
    # Task execution
    "task",
    "load",
    "run",
    "run_once",
    # Client
    "RunqyClient",
    "TaskInfo",
    "RunqyError",
    "AuthenticationError",
    "TaskNotFoundError",
    "enqueue",
]

__version__ = "0.2.0"
