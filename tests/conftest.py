"""Shared pytest configuration.

Gates integration tests behind --run-integration so the default `pytest` run
stays fast and doesn't require a live Ollama. CI / local sanity checks opt in
explicitly: `pytest --run-integration`.
"""

from __future__ import annotations

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="Run integration tests (require a live Ollama with the configured model pulled).",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-integration"):
        return
    skip_integration = pytest.mark.skip(
        reason="integration test — pass --run-integration to enable"
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)
