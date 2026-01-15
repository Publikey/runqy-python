"""Task decorators for registering handler and load functions."""

_registered_handler = None
_registered_loader = None


def task(func):
    """Decorator to register a function as the task handler.

    Usage:
        @task
        def process(payload: dict) -> dict:
            return {"result": "..."}

        # With context from @load:
        @task
        def process(payload: dict, ctx: dict) -> dict:
            return ctx["model"].predict(payload)
    """
    global _registered_handler
    _registered_handler = func
    return func


def load(func):
    """Decorator to register a function that runs once at startup.

    The load function is called before the ready signal is sent.
    Its return value is passed as the second argument (ctx) to the task handler.

    Usage:
        @load
        def setup():
            model = load_heavy_model()
            return {"model": model}

        @task
        def process(payload: dict, ctx: dict) -> dict:
            return ctx["model"].predict(payload)
    """
    global _registered_loader
    _registered_loader = func
    return func


def get_handler():
    """Get the registered task handler."""
    return _registered_handler


def get_loader():
    """Get the registered load function."""
    return _registered_loader
