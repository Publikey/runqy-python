<p align="center">
  <img src="assets/logo.svg" alt="runqy logo" width="80" height="80">
</p>

<h1 align="center">runqy-python</h1>

<p align="center">
  Python SDK for <a href="https://runqy.com">runqy</a> - write distributed task handlers with simple decorators.
  <br>
  <a href="https://docs.runqy.com"><strong>Documentation</strong></a> · <a href="https://runqy.com"><strong>Website</strong></a>
</p>

## Installation

```bash
pip install runqy-python
```

## Task Handlers

Create tasks that run on [runqy-worker](https://github.com/publikey/runqy-worker) using simple decorators:

### Simple Task

```python
from runqy_python import task, run

@task
def process(payload: dict) -> dict:
    return {"message": "Hello!", "received": payload}

if __name__ == "__main__":
    run()
```

### With Model Loading

For ML inference tasks, use `@load` to load models once at startup:

```python
from runqy_python import task, load, run

@load
def setup():
    """Runs once before ready signal. Return value is passed to @task as ctx."""
    model = load_heavy_model()  # Load weights, etc.
    return {"model": model}

@task
def process(payload: dict, ctx: dict) -> dict:
    """Process tasks using the loaded model."""
    prediction = ctx["model"].predict(payload["input"])
    return {"prediction": prediction}

if __name__ == "__main__":
    run()
```

### One-Shot Tasks

For lightweight tasks that don't need to stay loaded in memory, use `run_once()`:

```python
from runqy_python import task, run_once

@task
def process(payload: dict) -> dict:
    return {"result": payload["x"] * 2}

if __name__ == "__main__":
    run_once()  # Process one task and exit
```

| Function | Behavior | Use case |
|----------|----------|----------|
| `run()` | Loops forever, handles many tasks | ML inference (expensive load) |
| `run_once()` | Handles ONE task, exits | Lightweight tasks |

## Protocol

The SDK handles the runqy-worker stdin/stdout JSON protocol:

1. **Load phase**: Calls `@load` function (if registered)
2. **Ready signal**: Sends `{"status": "ready"}` after load completes
3. **Task input**: Reads JSON from stdin: `{"task_id": "...", "payload": {...}}`
4. **Response**: Writes JSON to stdout: `{"task_id": "...", "result": {...}, "error": null, "retry": false}`

## Client (Optional)

The SDK also includes a client for enqueuing tasks to a runqy server:

```python
from runqy_python import RunqyClient

client = RunqyClient("http://localhost:3000", api_key="your-api-key")

# Enqueue a task
task = client.enqueue("inference.default", {"input": "hello"})
print(f"Task ID: {task.task_id}")

# Check result
result = client.get_task(task.task_id)
print(f"State: {result.state}, Result: {result.result}")
```

Or use the convenience function:

```python
from runqy_python import enqueue

task = enqueue(
    "inference.default",
    {"input": "hello"},
    server_url="http://localhost:3000",
    api_key="your-api-key"
)
```

### Client API

**RunqyClient(server_url, api_key, timeout=30)**
- `server_url`: Base URL of the runqy server
- `api_key`: API key for authentication
- `timeout`: Default request timeout in seconds

**client.enqueue(queue, payload, timeout=300)**
- `queue`: Queue name (e.g., `"inference.default"`)
- `payload`: Task payload as a dict
- `timeout`: Task execution timeout in seconds
- Returns: `TaskInfo` with `task_id`, `queue`, `state`

**client.get_task(task_id)**
- `task_id`: Task ID from enqueue
- Returns: `TaskInfo` with `task_id`, `queue`, `state`, `result`, `error`

### Exceptions

- `RunqyError`: Base exception for all client errors
- `AuthenticationError`: Invalid or missing API key
- `TaskNotFoundError`: Task ID doesn't exist

## Development

```bash
# Install in editable mode
pip install -e .

# Test task execution
echo '{"task_id":"t1","payload":{"foo":"bar"}}' | python your_model.py

# Test client import
python -c "from runqy_python import RunqyClient; print('OK')"
```
