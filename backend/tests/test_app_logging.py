"""The app's own log lines reach stderr, where a platform's log stream reads them.

Uvicorn configures only its own loggers, so the lifespan gives the `app` logger
a handler. These tests start from a bare `app` logger and put back whatever an
earlier test's lifespan left there, because a handler added here would write to
this test's captured stderr after the test is over.
"""

import logging

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def app_logger():
    """The `app` logger as a new process has it: no handler, no level of its own."""
    logger = logging.getLogger("app")
    saved_handlers, saved_level = logger.handlers[:], logger.level
    for handler in saved_handlers:
        logger.removeHandler(handler)
    logger.setLevel(logging.NOTSET)
    yield logger
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    for handler in saved_handlers:
        logger.addHandler(handler)
    logger.setLevel(saved_level)


def test_the_lifespan_sends_the_apps_info_lines_to_stderr(app_logger, capsys):
    with TestClient(app):
        logging.getLogger("app.reminders.runner").info("reminders sent: 3")

    assert "INFO [app.reminders.runner] reminders sent: 3" in capsys.readouterr().err


def test_a_second_lifespan_adds_no_second_handler(app_logger):
    with TestClient(app):
        pass
    with TestClient(app):
        pass

    assert len(app_logger.handlers) == 1
    assert app_logger.level == logging.INFO


def test_a_handler_configured_elsewhere_is_left_alone(app_logger):
    """As a uvicorn --log-config that names the `app` logger would leave it."""
    theirs = logging.NullHandler()
    app_logger.addHandler(theirs)
    app_logger.setLevel(logging.WARNING)

    with TestClient(app):
        pass

    assert app_logger.handlers == [theirs]
    assert app_logger.level == logging.WARNING
