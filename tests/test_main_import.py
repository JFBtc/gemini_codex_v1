"""Smoke tests to ensure entrypoints import without errors."""

import pytest


# Skip these smoke tests when interactive-brokers dependency is unavailable.
pytest.importorskip("ib_insync")


def test_main_import():
    """Verify that the application entrypoint can be imported."""

    __import__("main")


def test_controller_import():
    """The BotController should be available for UI usage."""

    module = __import__("engine.controller", fromlist=["BotController"])
    assert hasattr(module, "BotController")
