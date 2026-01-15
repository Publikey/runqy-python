# runqy-task

Python SDK for creating tasks that run on [runqy-worker](../runqy-worker).

## Installation

```bash
pip install runqy-task
```

## Usage

### Simple Task

```python
from runqy_task import task, run

@task
def process(payload: dict) -> dict:
    return {"message": "Hello!", "received": payload}

if __name__ == "__main__":
    run()
```

### With Model Loading

For ML inference tasks, use `@load` to load models once at startup:

```python
from runqy_task import task, load, run

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

## Protocol

The SDK handles the runqy-worker stdin/stdout JSON protocol:

1. **Load phase**: Calls `@load` function (if registered)
2. **Ready signal**: Sends `{"status": "ready"}` after load completes
3. **Task input**: Reads JSON from stdin: `{"task_id": "...", "payload": {...}}`
4. **Response**: Writes JSON to stdout: `{"task_id": "...", "result": {...}, "error": null, "retry": false}`

## Development

```bash
# Install in editable mode
pip install -e .

# Test
echo '{"task_id":"t1","payload":{"foo":"bar"}}' | python your_model.py
```
