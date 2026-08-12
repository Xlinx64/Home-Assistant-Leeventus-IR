"""Fixtures for Leeventus IR integration tests."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parents[3]))


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None):
    """Enable loading this repository's custom integration in Home Assistant."""


@pytest.fixture(autouse=True)
def mock_infrared_entity_discovery():
    """Expose deterministic native infrared entities to config-flow tests."""
    with (
        patch(
            "custom_components.leeventus_ir.config_flow.infrared.async_get_emitters",
            return_value=["infrared.test_emitter"],
        ),
        patch(
            "custom_components.leeventus_ir.config_flow.infrared.async_get_receivers",
            return_value=["infrared.test_receiver"],
        ),
    ):
        yield
