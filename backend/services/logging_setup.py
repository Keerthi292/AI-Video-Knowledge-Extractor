import logging


def configure_app_logging(*logger_names: str) -> None:
    """Our own loggers (stage timings, which Gemini model answered) log at
    INFO; give them a handler so those lines appear next to uvicorn's output.
    Safe to call more than once."""
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s:     [%(name)s] %(message)s"))
    for name in ("services", *logger_names):
        app_logger = logging.getLogger(name)
        if app_logger.handlers:
            continue
        app_logger.setLevel(logging.INFO)
        app_logger.addHandler(handler)
        app_logger.propagate = False
