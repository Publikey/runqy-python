"""Runner loop for processing tasks from runqy-worker."""

import sys
import json
import signal
import traceback
from .decorator import get_handler, get_loader, RetryableError

# Flag for graceful shutdown
_shutdown_requested = False


def _shutdown_handler(signum, frame):
    """Handle SIGTERM/SIGINT for graceful shutdown.

    First signal: set flag so the current task can complete before exit.
    Second signal: force exit (in case process is stuck).
    """
    global _shutdown_requested
    if _shutdown_requested:
        # Second signal — force exit
        sys.exit(1)
    _shutdown_requested = True


def _safe_write(data):
    """Safely write JSON data to stdout, handling BrokenPipeError and serialization errors."""
    try:
        text = json.dumps(data)
    except (TypeError, ValueError) as e:
        # Result not JSON-serializable — send error response instead
        fallback = {
            "task_id": data.get("task_id", "unknown") if isinstance(data, dict) else "unknown",
            "result": None,
            "error": f"Result not JSON-serializable: {e}",
            "retry": False,
        }
        text = json.dumps(fallback)

    try:
        sys.stdout.write(text + "\n")
        sys.stdout.flush()
    except BrokenPipeError:
        # Pipe closed by worker — exit cleanly
        sys.exit(1)


def run():
    """Main loop: load, ready signal, read tasks, call handler, write responses.

    This function:
    1. Calls the @load function if registered (for model loading, etc.)
    2. Sends {"status": "ready"} to signal readiness to runqy-worker
    3. Reads JSON task requests from stdin (one per line)
    4. Calls the registered @task handler with the payload (and context if @load was used)
    5. Writes JSON responses to stdout
    """
    # Install signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, _shutdown_handler)
    signal.signal(signal.SIGINT, _shutdown_handler)

    handler = get_handler()
    if handler is None:
        raise RuntimeError("No task handler registered. Use @task decorator.")

    # Run load function if registered (before ready signal)
    loader = get_loader()
    ctx = None
    if loader is not None:
        try:
            ctx = loader()
        except Exception as e:
            _safe_write({"status": "error", "error": f"@load failed: {e}"})
            sys.exit(1)

    # Ready signal
    _safe_write({"status": "ready"})

    # Process tasks from stdin
    for line in sys.stdin:
        if _shutdown_requested:
            break

        line = line.strip()
        if not line:
            continue

        task_id = "unknown"
        try:
            task_data = json.loads(line)
            task_id = task_data.get("task_id", "unknown")
            payload = task_data.get("payload", {})

            # Call handler with or without context
            if ctx is not None:
                result = handler(payload, ctx)
            else:
                result = handler(payload)

            response = {
                "task_id": task_id,
                "result": result,
                "error": None,
                "retry": False
            }
        except json.JSONDecodeError as e:
            response = {
                "task_id": task_id,
                "result": None,
                "error": f"Invalid JSON input: {e}",
                "retry": False
            }
        except RetryableError as e:
            response = {
                "task_id": task_id,
                "result": None,
                "error": str(e),
                "retry": True
            }
        except Exception as e:
            response = {
                "task_id": task_id,
                "result": None,
                "error": traceback.format_exc(),
                "retry": False
            }

        _safe_write(response)


def run_once():
    """Process a single task from stdin and exit.

    Use this for lightweight tasks that don't need to stay loaded in memory.

    Flow:
    1. Calls @load function if registered
    2. Sends {"status": "ready"}
    3. Reads ONE JSON task from stdin
    4. Calls @task handler
    5. Writes response to stdout
    6. Exits
    """
    # Install signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, _shutdown_handler)
    signal.signal(signal.SIGINT, _shutdown_handler)

    handler = get_handler()
    if handler is None:
        raise RuntimeError("No task handler registered. Use @task decorator.")

    # Run load function if registered (before ready signal)
    loader = get_loader()
    ctx = None
    if loader is not None:
        try:
            ctx = loader()
        except Exception as e:
            _safe_write({"status": "error", "error": f"@load failed: {e}"})
            sys.exit(1)

    # Ready signal
    _safe_write({"status": "ready"})

    # Read ONE task
    line = sys.stdin.readline().strip()
    if not line:
        return

    task_id = "unknown"
    try:
        task_data = json.loads(line)
        task_id = task_data.get("task_id", "unknown")
        payload = task_data.get("payload", {})

        # Call handler with or without context
        if ctx is not None:
            result = handler(payload, ctx)
        else:
            result = handler(payload)

        response = {
            "task_id": task_id,
            "result": result,
            "error": None,
            "retry": False
        }
    except json.JSONDecodeError as e:
        response = {
            "task_id": task_id,
            "result": None,
            "error": f"Invalid JSON input: {e}",
            "retry": False
        }
    except RetryableError as e:
        response = {
            "task_id": task_id,
            "result": None,
            "error": str(e),
            "retry": True
        }
    except Exception as e:
        response = {
            "task_id": task_id,
            "result": None,
            "error": traceback.format_exc(),
            "retry": False
        }

    _safe_write(response)
