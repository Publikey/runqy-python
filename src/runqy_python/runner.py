"""Runner loop for processing tasks from runqy-worker."""

import sys
import json
from .decorator import get_handler, get_loader


def run():
    """Main loop: load, ready signal, read tasks, call handler, write responses.

    This function:
    1. Calls the @load function if registered (for model loading, etc.)
    2. Sends {"status": "ready"} to signal readiness to runqy-worker
    3. Reads JSON task requests from stdin (one per line)
    4. Calls the registered @task handler with the payload (and context if @load was used)
    5. Writes JSON responses to stdout
    """
    handler = get_handler()
    if handler is None:
        raise RuntimeError("No task handler registered. Use @task decorator.")

    # Run load function if registered (before ready signal)
    loader = get_loader()
    ctx = None
    if loader is not None:
        ctx = loader()

    # Ready signal
    print(json.dumps({"status": "ready"}))
    sys.stdout.flush()

    # Process tasks from stdin
    for line in sys.stdin:
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
        except Exception as e:
            response = {
                "task_id": task_id,
                "result": None,
                "error": str(e),
                "retry": False
            }

        print(json.dumps(response))
        sys.stdout.flush()


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
    handler = get_handler()
    if handler is None:
        raise RuntimeError("No task handler registered. Use @task decorator.")

    # Run load function if registered (before ready signal)
    loader = get_loader()
    ctx = None
    if loader is not None:
        ctx = loader()

    # Ready signal
    print(json.dumps({"status": "ready"}))
    sys.stdout.flush()

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
    except Exception as e:
        response = {
            "task_id": task_id,
            "result": None,
            "error": str(e),
            "retry": False
        }

    print(json.dumps(response))
    sys.stdout.flush()
