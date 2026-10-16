"""Task decorators for registering handler and load functions."""

_registered_handler = None
_registered_loader = None
_registered_reloader = None


class RetryableError(Exception):
    """Raise this from a @task handler to signal that the task should be retried.

    Usage:
        from runqy_python import task, RetryableError

        @task
        def process(payload):
            try:
                result = call_external_api(payload)
            except TimeoutError:
                raise RetryableError("API timed out, please retry")
            return result
    """
    pass


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
    if _registered_handler is not None:
        raise RuntimeError(
            f"@task handler already registered ({_registered_handler.__name__}). "
            "Only one @task handler is allowed per process."
        )
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
    if _registered_loader is not None:
        raise RuntimeError(
            f"@load handler already registered ({_registered_loader.__name__}). "
            "Only one @load handler is allowed per process."
        )
    _registered_loader = func
    return func


def reload(func):
    """Decorator to register a function that reloads configuration without a restart.

    Triggered by the worker's ``config_reload`` control command (``runqy control
    config-reload``). It runs between tasks, receives the current context (the @load
    return value, or None) and may return a new context; returning None keeps the
    current one (without @load, the return value is ignored). An exception is reported back as the command's error and the process
    keeps running with its previous context.

    Usage:
        @reload
        def refresh(ctx):
            ctx["models"] = fetch_models_yml()
            return ctx
    """
    global _registered_reloader
    if _registered_reloader is not None:
        raise RuntimeError(
            f"@reload handler already registered ({_registered_reloader.__name__}). "
            "Only one @reload handler is allowed per process."
        )
    _registered_reloader = func
    return func


def get_handler():
    """Get the registered task handler."""
    return _registered_handler


def get_loader():
    """Get the registered load function."""
    return _registered_loader


def get_reloader():
    """Get the registered reload function."""
    return _registered_reloader


def _reset():
    """Reset registered handler and loader. For testing only."""
    global _registered_handler, _registered_loader, _registered_reloader
    _registered_handler = None
    _registered_loader = None
    _registered_reloader = None
